from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StagingSmokeConfig:
    base_url: str
    management_viewer_key: str
    management_operator_key: str
    management_admin_key: str | None
    backup_drill_idempotency_key: str
    user_id: str
    user_role: str
    tenant_id: str | None
    timeout_seconds: float = 15.0
    refresh_quota_providers: tuple[str, ...] = ()
    verify_metrics: bool = True
    verify_live_routing: bool = False
    live_routing_provider: str | None = None
    trigger_backup_drill_via_api: bool = False
    database_url: str | None = None
    drill_database_url: str | None = None
    drill_target_name: str = "default"
    drill_output_dir: str = "backups/staging-live-smoke"
    drill_label: str = "staging-live-smoke"
    drill_timeout_seconds: float = 900.0


def _env(name: str, *, required: bool = True, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> StagingSmokeConfig:
    refresh_raw = (_env("STAGING_REFRESH_QUOTA_PROVIDERS", required=False, default="") or "").strip()
    refresh_providers = tuple(item.strip() for item in refresh_raw.split(",") if item.strip())
    return StagingSmokeConfig(
        base_url=str(_env("STAGING_BASE_URL")).rstrip("/"),
        management_viewer_key=str(_env("STAGING_MANAGEMENT_VIEWER_KEY")),
        management_operator_key=str(_env("STAGING_MANAGEMENT_OPERATOR_KEY")),
        management_admin_key=_env("STAGING_MANAGEMENT_ADMIN_KEY", required=False),
        backup_drill_idempotency_key=str(_env("STAGING_BACKUP_DRILL_IDEMPOTENCY_KEY", required=False, default=f"staging-backup-drill-{int(time.time())}") or f"staging-backup-drill-{int(time.time())}"),
        user_id=str(_env("STAGING_USER_ID", default="staging-smoke-user")),
        user_role=str(_env("STAGING_USER_ROLE", default="operator")),
        tenant_id=_env("STAGING_TENANT_ID", required=False),
        timeout_seconds=float(_env("STAGING_TIMEOUT_SECONDS", required=False, default="15") or 15),
        refresh_quota_providers=refresh_providers,
        verify_metrics=_env_bool("STAGING_VERIFY_METRICS", True),
        verify_live_routing=_env_bool("STAGING_VERIFY_LIVE_ROUTING", False),
        live_routing_provider=_env("STAGING_LIVE_ROUTING_PROVIDER", required=False),
        trigger_backup_drill_via_api=_env_bool("STAGING_TRIGGER_BACKUP_DRILL_VIA_API", False),
        database_url=_env("STAGING_DATABASE_URL", required=False),
        drill_database_url=_env("STAGING_DRILL_DATABASE_URL", required=False),
        drill_target_name=str(_env("STAGING_DRILL_TARGET_NAME", required=False, default="default") or "default"),
        drill_output_dir=str(_env("STAGING_DRILL_OUTPUT_DIR", required=False, default="backups/staging-live-smoke") or "backups/staging-live-smoke"),
        drill_label=str(_env("STAGING_DRILL_LABEL", required=False, default="staging-live-smoke") or "staging-live-smoke"),
        drill_timeout_seconds=float(_env("STAGING_DRILL_TIMEOUT_SECONDS", required=False, default="900") or 900),
    )



def _request_json(url: str, *, headers: dict[str, str] | None = None, body: dict | None = None, timeout: float = 15.0, method: str | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method or ("GET" if body is None else "POST"))
    if body is not None:
        req.add_header("content-type", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310
        payload = response.read().decode("utf-8")
        return response.status, json.loads(payload)



def _request_text(url: str, *, headers: dict[str, str] | None = None, timeout: float = 15.0):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310
        return response.status, response.read().decode("utf-8")



def _assert(cond: bool, message: str) -> None:
    if not cond:
        raise RuntimeError(message)



def _poll_backup_drill_job(cfg: StagingSmokeConfig, *, admin_headers: dict[str, str], status_url: str) -> dict[str, object]:
    deadline = time.time() + cfg.drill_timeout_seconds
    last_payload: dict[str, object] | None = None
    while time.time() < deadline:
        status, payload = _request_json(f"{cfg.base_url}{status_url}", headers=admin_headers, timeout=cfg.timeout_seconds)
        _assert(status == 200, "staging backup drill status lookup failed")
        last_payload = payload["data"]
        state = str(last_payload.get("state"))
        if state == "succeeded":
            report = last_payload.get("report")
            _assert(isinstance(report, dict), "staging backup drill completed without a report")
            return report
        if state in {"failed", "dead_lettered", "cancelled"}:
            raise RuntimeError(f"staging backup drill job ended in state={state}: {last_payload.get('last_error')}")
        time.sleep(2.0)
    raise RuntimeError(f"staging backup drill job did not complete before timeout: last_payload={last_payload}")


def _run_backup_drill(cfg: StagingSmokeConfig, *, admin_headers: dict[str, str] | None) -> dict[str, object] | None:
    if cfg.trigger_backup_drill_via_api:
        _assert(admin_headers is not None, "STAGING_TRIGGER_BACKUP_DRILL_VIA_API requires STAGING_MANAGEMENT_ADMIN_KEY")
        status, payload = _request_json(
            f"{cfg.base_url}/v1/admin/ops/backups/drill/run",
            headers={**admin_headers, "Idempotency-Key": cfg.backup_drill_idempotency_key},
            body={
                "target_name": cfg.drill_target_name,
                "label": cfg.drill_label,
            },
            timeout=cfg.timeout_seconds,
        )
        _assert(status == 202, "staging backup drill API trigger failed")
        status_url = payload["data"]["status_url"]
        return _poll_backup_drill_job(cfg, admin_headers=admin_headers, status_url=str(status_url))
    if not cfg.database_url or not cfg.drill_database_url:
        return None
    output_dir = Path(cfg.drill_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    cmd = [
        sys.executable,
        "scripts/postgres_backup_restore.py",
        "drill",
        "--source-database-url",
        cfg.database_url,
        "--target-database-url",
        cfg.drill_database_url,
        "--output-dir",
        str(output_dir),
        "--label",
        cfg.drill_label,
    ]
    completed = subprocess.run(  # noqa: S603
        cmd,
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=cfg.drill_timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "staging backup drill failed: "
            f"returncode={completed.returncode} stdout={completed.stdout} stderr={completed.stderr}"
        )
    return json.loads(completed.stdout)



def _verify_live_routing(cfg: StagingSmokeConfig, *, operator_headers: dict[str, str], admin_headers: dict[str, str] | None, providers: list[dict]) -> dict[str, object] | None:
    if not cfg.verify_live_routing:
        return None
    _assert(admin_headers is not None, "STAGING_VERIFY_LIVE_ROUTING requires STAGING_MANAGEMENT_ADMIN_KEY")
    target_provider = cfg.live_routing_provider or next((item["provider"] for item in providers if item.get("configured") and item.get("enabled")), None)
    _assert(bool(target_provider), "no configured provider available for live routing verification")
    project_id = f"staging-live-routing-{int(time.time())}"
    status, _ = _request_json(
        f"{cfg.base_url}/v1/admin/llm/scopes/project/{urllib.parse.quote(project_id)}/providers/{urllib.parse.quote(str(target_provider))}",
        headers=admin_headers,
        body={"enabled_override": True, "allow_work_override": True, "priority_offset": 1000, "daily_request_limit_override": 10},
        timeout=cfg.timeout_seconds,
        method="PUT",
    )
    _assert(status == 200, "staging live routing override write failed")
    status, scoped = _request_json(
        f"{cfg.base_url}/v1/admin/llm/providers?project_id={urllib.parse.quote(project_id)}",
        headers=operator_headers,
        timeout=cfg.timeout_seconds,
    )
    _assert(status == 200, "staging scoped provider list failed")
    scoped_provider = next((item for item in scoped["data"]["providers"] if item["provider"] == target_provider), None)
    _assert(scoped_provider is not None and scoped_provider["effective_scope"] == "project", "project override was not applied to provider status")
    status, preview = _request_json(
        f"{cfg.base_url}/v1/admin/llm/routing/preview",
        headers=operator_headers,
        body={"prompt_type": "review", "complexity": "medium", "review_required": True, "tenant_id": cfg.tenant_id, "project_id": project_id},
        timeout=cfg.timeout_seconds,
    )
    _assert(status == 200, "staging live routing preview failed")
    _assert(preview["data"]["work"]["provider"] == target_provider, "project override did not affect live routing work provider")
    if scoped_provider.get("external_observed_at"):
        _assert(preview["data"]["work"]["remaining_requests"] is not None, "quota snapshot was not reflected in routing decision")
    return {"project_id": project_id, "provider": target_provider, "preview": preview["data"]}


def main() -> int:
    cfg = load_config()
    viewer_headers = {"X-Management-Key": cfg.management_viewer_key}
    operator_headers = {"X-Management-Key": cfg.management_operator_key}
    admin_headers = {"X-Management-Key": cfg.management_admin_key} if cfg.management_admin_key else None
    user_headers = {
        "X-User-Id": cfg.user_id,
        "X-User-Role": cfg.user_role,
        "Idempotency-Key": f"staging-smoke-{int(time.time())}",
    }
    if cfg.tenant_id:
        user_headers["X-Tenant-Id"] = cfg.tenant_id

    status, ready = _request_json(f"{cfg.base_url}/readyz", headers=viewer_headers, timeout=cfg.timeout_seconds)
    _assert(status == 200 and ready["status"] == "ready", "staging /readyz failed")

    status, _ = _request_json(f"{cfg.base_url}/runbooks", headers=viewer_headers, timeout=cfg.timeout_seconds)
    _assert(status == 200, "staging /runbooks failed for viewer key")

    status, providers = _request_json(f"{cfg.base_url}/v1/admin/llm/providers", headers=operator_headers, timeout=cfg.timeout_seconds)
    _assert(status == 200 and providers["data"]["providers"], "staging admin LLM provider list failed")

    status, _ = _request_json(f"{cfg.base_url}/v1/admin/ops/abuse/config", headers=operator_headers, timeout=cfg.timeout_seconds)
    _assert(status == 200, "staging admin ops abuse config failed for operator key")
    status, _ = _request_json(f"{cfg.base_url}/v1/admin/ops/backups/config", headers=operator_headers, timeout=cfg.timeout_seconds)
    _assert(status == 200, "staging admin ops backups config failed for operator key")

    preview_body = {
        "prompt_type": "review",
        "complexity": "medium",
        "review_required": True,
        "tenant_id": cfg.tenant_id,
        "project_id": "staging-smoke-project",
    }
    status, preview = _request_json(
        f"{cfg.base_url}/v1/admin/llm/routing/preview",
        headers=operator_headers,
        body=preview_body,
        timeout=cfg.timeout_seconds,
    )
    _assert(status == 200, "staging admin LLM routing preview failed")
    _assert(preview["data"]["review"]["session_mode"] == "fresh_review_session", "review session policy violated")

    status, audit = _request_json(f"{cfg.base_url}/v1/admin/audit/events", headers=operator_headers, timeout=cfg.timeout_seconds)
    _assert(status == 200 and "events" in audit["data"], "staging admin audit fetch failed for operator key")

    if admin_headers is not None and _env_bool("STAGING_VERIFY_ADMIN_WRITE", False):
        status, current = _request_json(
            f"{cfg.base_url}/v1/admin/llm/providers/gemini",
            headers=admin_headers,
            body={"priority": 200},
            timeout=cfg.timeout_seconds,
            method="PUT",
        )
        _assert(status == 200 and current["data"]["provider"] == "gemini", "staging admin write verification failed")

    refreshed: dict[str, object] = {}
    for provider in cfg.refresh_quota_providers:
        status, payload = _request_json(
            f"{cfg.base_url}/v1/admin/llm/providers/{urllib.parse.quote(provider)}/refresh-quota",
            headers=operator_headers,
            body={},
            timeout=cfg.timeout_seconds,
        )
        _assert(status == 200, f"quota refresh failed for provider {provider}")
        refreshed[provider] = payload["data"]
        _assert(payload["data"]["external_observed_at"], f"quota refresh did not populate observation for provider {provider}")

    live_routing = _verify_live_routing(cfg, operator_headers=operator_headers, admin_headers=admin_headers, providers=providers["data"]["providers"])

    if cfg.verify_metrics:
        status, metrics_text = _request_text(f"{cfg.base_url}/metrics", headers=viewer_headers, timeout=cfg.timeout_seconds)
        _assert(status == 200, "staging /metrics failed for viewer key")
        _assert("acp_rate_limit_backend_healthy" in metrics_text, "staging metrics missing rate limit backend health metric")

    create_body = {
        "project_id": "staging-smoke-project",
        "user_input": "staging smoke create cycle",
        "metadata": {"llm_complexity": "low", "llm_review_required": True},
    }
    status, created = _request_json(f"{cfg.base_url}/v1/cycles", headers=user_headers, body=create_body, timeout=cfg.timeout_seconds)
    _assert(status in {200, 201}, f"staging create cycle failed with status {status}")
    cycle_id = created["data"]["cycle_id"]

    status, summary = _request_json(f"{cfg.base_url}/v1/cycles/{urllib.parse.quote(cycle_id)}", headers=user_headers, timeout=cfg.timeout_seconds)
    _assert(status == 200 and summary["data"]["cycle_id"] == cycle_id, "staging cycle summary fetch failed")

    drill_report = _run_backup_drill(cfg, admin_headers=admin_headers)
    if drill_report is not None:
        _assert(drill_report.get("status") == "ok", "staging backup drill reported failure")
        if _env_bool("STAGING_EXPECT_OBJECT_STORE_UPLOAD", False):
            object_store = (drill_report.get("backup") or {}).get("object_store") or {}
            _assert(bool(object_store.get("artifact_uri")), "staging backup drill missing object_store artifact_uri")
            if _env_bool("BACKUP_OBJECT_STORE_VERIFY_RESTORE", False):
                _assert(str((drill_report.get("restore") or {}).get("backup_file", "")).startswith("s3://"), "staging backup drill did not restore from object store")
    print(
        json.dumps(
            {
                "ok": True,
                "cycle_id": cycle_id,
                "preview": preview["data"],
                "quota_refresh": refreshed,
                "live_routing": live_routing,
                "audit_event_count": len(audit["data"]["events"]),
                "backup_drill": drill_report,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"HTTPError: {exc.code} {detail}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"staging smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1)


# Admin ops management endpoints verified by tests and optional smoke invocations.
ADMIN_OPS_PATHS = [
    "/v1/admin/ops/abuse/config",
    "/v1/admin/ops/backups/config",
    "/v1/admin/ops/backups/drill/run",
    "/v1/admin/ops/backups/drill/jobs/{job_id}",
    "DELETE /v1/admin/ops/backups/drill/jobs/{job_id}",
    "/v1/admin/ops/observability/status",
]
