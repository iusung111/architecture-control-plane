from fastapi.testclient import TestClient
from sqlalchemy import select
import httpx

from app.db.models import Approval, NotificationOutbox
from app.domain.enums import CycleState, OutboxDeliveryState
from app.services.notifications import NotificationDispatcher
from app.workers.default_handlers import build_default_job_handlers, build_default_outbox_handlers
from app.workers.job_runner import JobRunner
from app.workers.outbox_consumer import OutboxConsumer



def test_default_job_handlers_complete_cycle_and_result_endpoint(client: TestClient, db_session) -> None:
    create = client.post(
        "/v1/cycles",
        headers={"X-User-Id": "owner-1", "Idempotency-Key": "runtime-create-1"},
        json={"project_id": "proj-1", "user_input": "complete automatically"},
    )
    cycle_id = create.json()["data"]["cycle_id"]

    run_result = JobRunner(db_session, handlers=build_default_job_handlers(db_session)).run_once(worker_id="worker-runtime", limit=10)
    assert run_result.succeeded == 1

    summary = client.get(f"/v1/cycles/{cycle_id}", headers={"X-User-Id": "owner-1"})
    assert summary.status_code == 200
    assert summary.json()["data"]["state"] == CycleState.TERMINALIZED

    result = client.get(f"/v1/cycles/{cycle_id}/result", headers={"X-User-Id": "owner-1"})
    assert result.status_code == 200
    body = result.json()["data"]
    assert body["final_state"] == CycleState.TERMINALIZED
    assert body["verification"]["status"] == "passed"
    assert body["summary"] == "Cycle completed without manual approval"
    assert len(body["output_artifacts"]) == 1



def test_default_job_handlers_pause_for_approval_then_resume(client: TestClient, db_session) -> None:
    create = client.post(
        "/v1/cycles",
        headers={"X-User-Id": "owner-2", "Idempotency-Key": "runtime-create-approval-1"},
        json={
            "project_id": "proj-1",
            "user_input": "needs human approval",
            "metadata": {"requires_human_approval": True, "required_role": "supervisor"},
        },
    )
    cycle_id = create.json()["data"]["cycle_id"]

    JobRunner(db_session, handlers=build_default_job_handlers(db_session)).run_once(worker_id="worker-runtime", limit=10)

    summary = client.get(f"/v1/cycles/{cycle_id}", headers={"X-User-Id": "owner-2"})
    assert summary.status_code == 200
    assert summary.json()["data"]["state"] == CycleState.HUMAN_APPROVAL_PENDING
    assert summary.json()["data"]["approval_required"] is True

    approval = db_session.execute(select(Approval).where(Approval.cycle_id == cycle_id)).scalar_one()
    confirm = client.post(
        f"/v1/approvals/{approval.approval_id}/confirm",
        headers={"X-User-Id": "owner-2", "X-User-Role": "supervisor", "Idempotency-Key": "approval-confirm-1"},
        json={"decision": "approved", "comment": "looks good"},
    )
    assert confirm.status_code == 200

    run_result = JobRunner(db_session, handlers=build_default_job_handlers(db_session)).run_once(worker_id="worker-runtime", limit=10)
    assert run_result.succeeded == 1

    result = client.get(f"/v1/cycles/{cycle_id}/result", headers={"X-User-Id": "owner-2"})
    assert result.status_code == 200
    assert result.json()["data"]["final_state"] == CycleState.TERMINALIZED
    assert result.json()["data"]["summary"] == "Cycle completed after human approval"



def test_default_job_handlers_support_replan_after_verification_failure(client: TestClient, db_session) -> None:
    create = client.post(
        "/v1/cycles",
        headers={"X-User-Id": "owner-3", "Idempotency-Key": "runtime-create-fail-1"},
        json={
            "project_id": "proj-1",
            "user_input": "initially fail verification",
            "metadata": {"force_verification_failure": True},
        },
    )
    cycle_id = create.json()["data"]["cycle_id"]

    JobRunner(db_session, handlers=build_default_job_handlers(db_session)).run_once(worker_id="worker-runtime", limit=10)

    summary = client.get(f"/v1/cycles/{cycle_id}", headers={"X-User-Id": "owner-3"})
    assert summary.status_code == 200
    assert summary.json()["data"]["state"] == CycleState.VERIFICATION_FAILED
    assert summary.json()["data"]["retry_allowed"] is True
    assert summary.json()["data"]["replan_allowed"] is True

    replan = client.post(
        f"/v1/cycles/{cycle_id}/replan",
        headers={"X-User-Id": "owner-3", "Idempotency-Key": "runtime-replan-1"},
        json={"reason": "remove failure flag", "override_input": {"force_verification_failure": "false"}},
    )
    assert replan.status_code == 202

    runner = JobRunner(db_session, handlers=build_default_job_handlers(db_session))
    first = runner.run_once(worker_id="worker-runtime", limit=10)
    second = runner.run_once(worker_id="worker-runtime", limit=10)
    assert first.succeeded == 1
    assert second.succeeded == 1

    result = client.get(f"/v1/cycles/{cycle_id}/result", headers={"X-User-Id": "owner-3"})
    assert result.status_code == 200
    assert result.json()["data"]["final_state"] == CycleState.TERMINALIZED



def test_default_outbox_handlers_use_webhook_dispatch_and_retry_classification(db_session) -> None:
    delivered_item = NotificationOutbox(
        outbox_id="outbox-success",
        cycle_id="cycle-1",
        event_type="cycle.completed",
        payload={"cycle_id": "cycle-1"},
        delivery_state=OutboxDeliveryState.PENDING,
    )
    retryable_item = NotificationOutbox(
        outbox_id="outbox-retryable",
        cycle_id="cycle-2",
        event_type="cycle.completed",
        payload={"cycle_id": "cycle-2"},
        delivery_state=OutboxDeliveryState.PENDING,
    )
    nonretryable_item = NotificationOutbox(
        outbox_id="outbox-fatal",
        cycle_id="cycle-3",
        event_type="cycle.completed",
        payload={"cycle_id": "cycle-3"},
        delivery_state=OutboxDeliveryState.PENDING,
    )
    db_session.add_all([delivered_item, retryable_item, nonretryable_item])
    db_session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        if "cycle-1" in body:
            return httpx.Response(202, json={"ok": True})
        if "cycle-2" in body:
            return httpx.Response(503, json={"ok": False})
        return httpx.Response(400, json={"ok": False})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    dispatcher = NotificationDispatcher(webhook_url="https://example.test/hook", client=client)
    consumer = OutboxConsumer(db_session, handlers=build_default_outbox_handlers(dispatcher=dispatcher))
    result = consumer.deliver_once(limit=10)

    db_session.refresh(delivered_item)
    db_session.refresh(retryable_item)
    db_session.refresh(nonretryable_item)

    assert result.processed == 3
    assert delivered_item.delivery_state == OutboxDeliveryState.DELIVERED
    assert retryable_item.delivery_state == OutboxDeliveryState.FAILED
    assert nonretryable_item.delivery_state == OutboxDeliveryState.DEAD_LETTERED
