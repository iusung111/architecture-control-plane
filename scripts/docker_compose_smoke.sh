#!/usr/bin/env bash
set -euo pipefail

COMPOSE_CMD="docker compose"

cleanup() {
  ${COMPOSE_CMD} down -v || true
}
trap cleanup EXIT

${COMPOSE_CMD} up --build -d

python - <<'PY'
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

base_url = "http://localhost:8000"
sink_url = "http://localhost:8081"
prometheus_ready_url = "http://localhost:9090/-/ready"
prometheus_rules_url = "http://localhost:9090/api/v1/rules"
alertmanager_ready_url = "http://localhost:9093/-/ready"
alertmanager_alerts_url = "http://localhost:9093/api/v2/alerts"
grafana_health_url = "http://localhost:3000/api/health"
worker_jobs_metrics_url = "http://localhost:9101/metrics"
worker_outbox_metrics_url = "http://localhost:9102/metrics"
mailpit_messages_url = "http://localhost:8025/api/v1/messages"
alert_email_recipient = "team@example.com"
management_headers = {"X-Management-Key": "local-dev-management-key"}


def _request(url: str, *, headers: dict[str, str] | None = None, method: str = "GET", data: bytes | None = None) -> urllib.request.Request:
    return urllib.request.Request(url, headers=headers or {}, method=method, data=data)


def wait_json(url: str, *, timeout_seconds: int = 180, expected_status: int = 200, headers: dict[str, str] | None = None) -> dict:
    deadline = time.time() + timeout_seconds
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(_request(url, headers=headers), timeout=5) as response:
                if response.status != expected_status:
                    raise RuntimeError(f"unexpected status={response.status} for url={url}")
                return json.load(response)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2)
    raise SystemExit(f"timeout waiting for {url}: {last_error}")


def wait_text(url: str, *, timeout_seconds: int = 180, expected_substring: str | None = None, headers: dict[str, str] | None = None) -> str:
    deadline = time.time() + timeout_seconds
    last_error = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(_request(url, headers=headers), timeout=5) as response:
                payload = response.read().decode("utf-8")
            if expected_substring and expected_substring not in payload:
                raise RuntimeError(f"missing expected substring={expected_substring!r} in url={url}")
            return payload
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(2)
    raise SystemExit(f"timeout waiting for {url}: {last_error}")


def wait_mailpit_message(recipient: str, subject_substring: str, *, timeout_seconds: int = 180) -> dict:
    deadline = time.time() + timeout_seconds
    last_snapshot: object = None
    while time.time() < deadline:
        try:
            payload = wait_json(mailpit_messages_url, timeout_seconds=5)
            messages = payload.get("messages", [])
            last_snapshot = messages
            for message in messages:
                recipients = [item.get("Address") for item in message.get("To", [])]
                if recipient not in recipients:
                    continue
                subject = message.get("Subject", "")
                if subject_substring in subject:
                    return message
        except Exception as exc:  # noqa: BLE001
            last_snapshot = exc
        time.sleep(2)
    raise SystemExit(
        f"timed out waiting for email recipient={recipient} subject~={subject_substring!r}: {last_snapshot}"
    )


wait_json(f"{base_url}/readyz", headers=management_headers)
wait_json(f"{sink_url}/healthz")
wait_json(mailpit_messages_url)
wait_text(alertmanager_ready_url, expected_substring="OK")
grafana_health = wait_json(grafana_health_url)
if grafana_health.get("database") != "ok":
    raise SystemExit(f"grafana health unexpected: {grafana_health}")
wait_text(prometheus_ready_url, expected_substring="Prometheus Server is Ready")
prometheus_rules = wait_json(prometheus_rules_url)
rule_payloads = [
    rule
    for group in prometheus_rules.get("data", {}).get("groups", [])
    for rule in group.get("rules", [])
]
rule_names = {rule.get("name") for rule in rule_payloads}
if "ACPApiAvailabilityErrorBudgetFastBurn" not in rule_names:
    raise SystemExit(f"expected Prometheus alert rules were not loaded: {sorted(rule_names)}")
fast_burn_rule = next(rule for rule in rule_payloads if rule.get("name") == "ACPApiAvailabilityErrorBudgetFastBurn")
if "runbook_url" not in fast_burn_rule.get("annotations", {}):
    raise SystemExit(f"runbook_url annotation missing from Prometheus rule: {fast_burn_rule}")
wait_text(worker_jobs_metrics_url, expected_substring="acp_job_executions_total")
wait_text(worker_outbox_metrics_url, expected_substring="acp_outbox_deliveries_total")
runbook_index = wait_json(f"{base_url}/runbooks", headers=management_headers)
if runbook_index.get("count", 0) < 1:
    raise SystemExit(f"runbook index was empty: {runbook_index}")
runbook_text = wait_text(
    f"{base_url}/runbooks/api-availability-fast-burn",
    expected_substring="API availability fast burn",
    headers=management_headers,
)
if "API availability fast burn" not in runbook_text:
    raise SystemExit("runbook detail endpoint did not return the expected markdown")

starts_at = datetime.now(timezone.utc).replace(microsecond=0)
ends_at = starts_at + timedelta(minutes=30)
injected_alert = [
    {
        "labels": {
            "alertname": "ACPApiAvailabilityErrorBudgetFastBurn",
            "severity": "critical",
            "service": "architecture-control-plane",
            "team": "ops",
            "notify": "email",
        },
        "annotations": {
            "summary": "Smoke email routing test",
            "description": "Verifies Alertmanager routes a critical ACP alert to email and webhook receivers.",
            "runbook_url": "http://localhost:8000/runbooks/api-availability-fast-burn",
        },
        "startsAt": starts_at.isoformat().replace("+00:00", "Z"),
        "endsAt": ends_at.isoformat().replace("+00:00", "Z"),
        "generatorURL": "http://prometheus:9090/graph?g0.expr=vector(1)",
    }
]
inject_request = urllib.request.Request(
    alertmanager_alerts_url,
    data=json.dumps(injected_alert).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(inject_request, timeout=10) as response:
    if response.status not in {200, 202}:
        raise SystemExit(f"unexpected Alertmanager response: {response.status}")

mailpit_message = wait_mailpit_message(alert_email_recipient, "ACPApiAvailabilityErrorBudgetFastBurn")

create_payload = json.dumps(
    {
        "project_id": "smoke-project",
        "user_input": "require approval before completion",
        "metadata": {"requires_human_approval": True, "required_role": "approver"},
    }
).encode("utf-8")
create_request = urllib.request.Request(
    f"{base_url}/v1/cycles",
    data=create_payload,
    headers={
        "Content-Type": "application/json",
        "X-User-Id": "smoke-user",
        "X-User-Role": "approver",
        "Idempotency-Key": "smoke-create-approval-1",
    },
    method="POST",
)
with urllib.request.urlopen(create_request, timeout=10) as response:
    created = json.load(response)
cycle_id = created["data"]["cycle_id"]

approval_id = None
for _ in range(90):
    summary_request = urllib.request.Request(
        f"{base_url}/v1/cycles/{cycle_id}",
        headers={"X-User-Id": "smoke-user", "X-User-Role": "approver"},
        method="GET",
    )
    with urllib.request.urlopen(summary_request, timeout=10) as response:
        summary = json.load(response)
    if summary["data"]["state"] == "human_approval_pending":
        approval_query = urllib.parse.urlencode({"event_type": "approval.requested", "cycle_id": cycle_id})
        approval_events = wait_json(f"{sink_url}/events?{approval_query}")
        if approval_events["count"] < 1:
            raise SystemExit(f"approval.requested was not delivered: {approval_events}")
        approval_id = approval_events["events"][0]["payload"]["approval_id"]
        break
    time.sleep(2)
else:
    raise SystemExit(f"cycle did not reach human_approval_pending: last={summary}")

confirm_payload = json.dumps({"decision": "approved", "comment": "smoke approval"}).encode("utf-8")
confirm_request = urllib.request.Request(
    f"{base_url}/v1/approvals/{approval_id}/confirm",
    data=confirm_payload,
    headers={
        "Content-Type": "application/json",
        "X-User-Id": "smoke-user",
        "X-User-Role": "approver",
        "Idempotency-Key": "smoke-approval-confirm-1",
    },
    method="POST",
)
with urllib.request.urlopen(confirm_request, timeout=10) as response:
    confirm = json.load(response)
if confirm["data"]["approval_state"] != "approved":
    raise SystemExit(f"approval confirm failed: {confirm}")

state = None
for _ in range(120):
    summary_request = urllib.request.Request(
        f"{base_url}/v1/cycles/{cycle_id}",
        headers={"X-User-Id": "smoke-user", "X-User-Role": "approver"},
        method="GET",
    )
    with urllib.request.urlopen(summary_request, timeout=10) as response:
        summary = json.load(response)
    state = summary["data"]["state"]
    if state == "terminalized":
        break
    if state == "terminal_fail":
        raise SystemExit(f"cycle moved to terminal_fail: {summary}")
    time.sleep(2)
else:
    raise SystemExit(f"cycle did not terminalize in time: state={state}")

approved_query = urllib.parse.urlencode({"event_type": "approval.approved", "cycle_id": cycle_id})
completed_query = urllib.parse.urlencode({"event_type": "cycle.completed", "cycle_id": cycle_id})
approved_events = wait_json(f"{sink_url}/events?{approved_query}")
completed_events = wait_json(f"{sink_url}/events?{completed_query}")
if approved_events["count"] < 1:
    raise SystemExit(f"approval.approved was not delivered: {approved_events}")
if completed_events["count"] < 1:
    raise SystemExit(f"cycle.completed was not delivered: {completed_events}")

metrics_snapshot = wait_text(f"{base_url}/metrics", expected_substring="acp_http_requests_total", headers=management_headers)
if "acp_http_requests_total" not in metrics_snapshot:
    raise SystemExit("api metrics endpoint did not expose acp_http_requests_total")
if "acp_slo_events_total" not in metrics_snapshot:
    raise SystemExit("api metrics endpoint did not expose acp_slo_events_total")

result_request = urllib.request.Request(
    f"{base_url}/v1/cycles/{cycle_id}/result",
    headers={"X-User-Id": "smoke-user", "X-User-Role": "approver"},
    method="GET",
)
with urllib.request.urlopen(result_request, timeout=10) as response:
    result_payload = json.load(response)
if result_payload["data"]["final_state"] != "terminalized":
    raise SystemExit(f"unexpected result payload: {result_payload}")

print(
    json.dumps(
        {
            "cycle_id": cycle_id,
            "approval_id": approval_id,
            "final_state": result_payload["data"]["final_state"],
            "delivered_events": ["approval.requested", "approval.approved", "cycle.completed"],
            "alert_email_subject": mailpit_message.get("Subject"),
            "alert_email_to": [item.get("Address") for item in mailpit_message.get("To", [])],
            "grafana": grafana_health,
        },
        ensure_ascii=False,
    )
)
PY
