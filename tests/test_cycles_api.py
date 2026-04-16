from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import AuditEvent


from datetime import datetime, timedelta, timezone

from app.db.models import Cycle
from app.domain.enums import CycleState, UserStatus


def test_list_cycles_returns_owner_scoped_items_and_filters(client: TestClient, db_session) -> None:
    first = client.post(
        "/v1/cycles",
        headers={"X-User-Id": "list-owner", "X-Tenant-Id": "tenant-a", "Idempotency-Key": "list-001"},
        json={"project_id": "proj-keep", "user_input": "first"},
    )
    second = client.post(
        "/v1/cycles",
        headers={"X-User-Id": "list-owner", "X-Tenant-Id": "tenant-a", "Idempotency-Key": "list-002"},
        json={"project_id": "proj-skip", "user_input": "second"},
    )
    third = client.post(
        "/v1/cycles",
        headers={"X-User-Id": "other-owner", "X-Tenant-Id": "tenant-a", "Idempotency-Key": "list-003"},
        json={"project_id": "proj-keep", "user_input": "third"},
    )
    assert third.status_code == 201
    first_id = first.json()["data"]["cycle_id"]
    second_id = second.json()["data"]["cycle_id"]

    keep = db_session.get(Cycle, first_id)
    skip = db_session.get(Cycle, second_id)
    assert keep is not None and skip is not None
    keep.current_state = CycleState.VERIFICATION_FAILED
    keep.user_status = UserStatus.ACTION_REQUIRED
    keep.updated_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    skip.updated_at = datetime.now(timezone.utc)
    db_session.commit()

    response = client.get(
        "/v1/cycles",
        headers={"X-User-Id": "list-owner", "X-Tenant-Id": "tenant-a"},
        params={"project_id": "proj-keep", "state": CycleState.VERIFICATION_FAILED, "user_status": UserStatus.ACTION_REQUIRED},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    items = body["data"]["items"]
    assert [item["cycle_id"] for item in items] == [first_id]
    assert items[0]["retry_allowed"] is True
    assert items[0]["replan_allowed"] is True
    assert items[0]["project_id"] == "proj-keep"


def test_list_cycles_supports_cursor_pagination(client: TestClient, db_session) -> None:
    created_ids = []
    for idx in range(3):
        response = client.post(
            "/v1/cycles",
            headers={"X-User-Id": "pager-owner", "Idempotency-Key": f"page-{idx}"},
            json={"project_id": f"proj-{idx}", "user_input": f"payload-{idx}"},
        )
        assert response.status_code == 201
        created_ids.append(response.json()["data"]["cycle_id"])

    base_time = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    for offset, cycle_id in enumerate(created_ids):
        cycle = db_session.get(Cycle, cycle_id)
        assert cycle is not None
        cycle.updated_at = base_time + timedelta(minutes=offset)
    db_session.commit()

    first_page = client.get("/v1/cycles", headers={"X-User-Id": "pager-owner"}, params={"limit": 2})
    assert first_page.status_code == 200
    first_body = first_page.json()["data"]
    assert len(first_body["items"]) == 2
    assert first_body["has_more"] is True
    assert first_body["next_cursor"]
    first_ids = [item["cycle_id"] for item in first_body["items"]]
    assert first_ids == [created_ids[2], created_ids[1]]

    second_page = client.get(
        "/v1/cycles",
        headers={"X-User-Id": "pager-owner"},
        params={"limit": 2, "cursor": first_body["next_cursor"]},
    )
    assert second_page.status_code == 200
    second_body = second_page.json()["data"]
    assert [item["cycle_id"] for item in second_body["items"]] == [created_ids[0]]
    assert second_body["has_more"] is False
    assert second_body["next_cursor"] is None


def test_list_cycles_rejects_invalid_cursor(client: TestClient) -> None:
    response = client.get("/v1/cycles", headers={"X-User-Id": "cursor-owner"}, params={"cursor": "not-valid"})
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "validation_error"


def test_create_cycle_returns_201(client: TestClient, db_session) -> None:
    response = client.post(
        "/v1/cycles",
        headers={"X-User-Id": "user-1", "Idempotency-Key": "idem-001"},
        json={"project_id": "proj-1", "user_input": "inspect hydraulic pressure drift"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ok"
    assert body["data"]["state"] == "intent_accepted"
    assert body["data"]["user_status"] == "accepted"
    assert body["data"]["cycle_id"]

    audit_event = db_session.execute(
        select(AuditEvent).where(AuditEvent.cycle_id == body["data"]["cycle_id"], AuditEvent.event_type == "cycle.created")
    ).scalar_one()
    assert audit_event.actor_id == "user-1"
    assert audit_event.event_payload["idempotency_key"] == "idem-001"
    assert audit_event.event_payload["state"] == "intent_accepted"


def test_create_cycle_requires_user_header(client: TestClient) -> None:
    response = client.post(
        "/v1/cycles",
        headers={"Idempotency-Key": "idem-002"},
        json={"project_id": "proj-1", "user_input": "missing actor"},
    )
    assert response.status_code == 403
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "forbidden"
    assert body["error"]["message"] == "missing x-user-id header"


def test_create_cycle_is_idempotent_for_same_key(client: TestClient) -> None:
    headers = {"X-User-Id": "user-1", "Idempotency-Key": "idem-003"}
    payload = {"project_id": "proj-1", "user_input": "repeat request"}

    first = client.post("/v1/cycles", headers=headers, json=payload)
    second = client.post("/v1/cycles", headers=headers, json=payload)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["data"]["cycle_id"] == second.json()["data"]["cycle_id"]



def test_get_cycle_requires_auth_and_owner_scope(client: TestClient) -> None:
    create = client.post(
        "/v1/cycles",
        headers={"X-User-Id": "owner-1", "Idempotency-Key": "idem-004"},
        json={"project_id": "proj-1", "user_input": "authorized summary"},
    )
    cycle_id = create.json()["data"]["cycle_id"]

    missing = client.get(f"/v1/cycles/{cycle_id}")
    assert missing.status_code == 403

    forbidden = client.get(f"/v1/cycles/{cycle_id}", headers={"X-User-Id": "other-user"})
    assert forbidden.status_code == 403

    allowed = client.get(f"/v1/cycles/{cycle_id}", headers={"X-User-Id": "owner-1"})
    assert allowed.status_code == 200
    assert allowed.json()["data"]["cycle_id"] == cycle_id


def test_create_cycle_same_idempotency_key_with_different_payload_returns_409(client: TestClient) -> None:
    headers = {"X-User-Id": "user-1", "Idempotency-Key": "idem-004b"}

    first = client.post(
        "/v1/cycles",
        headers=headers,
        json={"project_id": "proj-1", "user_input": "original payload"},
    )
    second = client.post(
        "/v1/cycles",
        headers=headers,
        json={"project_id": "proj-1", "user_input": "different payload"},
    )

    assert first.status_code == 201
    assert second.status_code == 409
    body = second.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "conflict"
    assert body["error"]["message"] == "idempotency key reused with different request payload"


def test_create_cycle_validation_error_uses_error_envelope(client: TestClient) -> None:
    response = client.post(
        "/v1/cycles",
        headers={"X-User-Id": "user-1", "Idempotency-Key": "idem-validation"},
        json={"project_id": "proj-1"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "validation_error"



def test_create_cycle_same_idempotency_key_with_different_metadata_returns_409(client: TestClient) -> None:
    headers = {"X-User-Id": "user-1", "Idempotency-Key": "idem-004c"}

    first = client.post(
        "/v1/cycles",
        headers=headers,
        json={"project_id": "proj-1", "user_input": "same prompt", "metadata": {"mode": "safe"}},
    )
    second = client.post(
        "/v1/cycles",
        headers=headers,
        json={"project_id": "proj-1", "user_input": "same prompt", "metadata": {"mode": "fast"}},
    )

    assert first.status_code == 201
    assert second.status_code == 409
    body = second.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "conflict"
    assert body["error"]["message"] == "idempotency key reused with different request payload"



def test_create_cycle_allows_same_idempotency_key_across_tenants(client: TestClient) -> None:
    payload = {"project_id": "proj-1", "user_input": "same request"}

    first = client.post(
        "/v1/cycles",
        headers={"X-User-Id": "user-1", "X-Tenant-Id": "tenant-a", "Idempotency-Key": "idem-cross-tenant"},
        json=payload,
    )
    second = client.post(
        "/v1/cycles",
        headers={"X-User-Id": "user-1", "X-Tenant-Id": "tenant-b", "Idempotency-Key": "idem-cross-tenant"},
        json=payload,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["data"]["cycle_id"] != second.json()["data"]["cycle_id"]



def test_create_cycle_rejects_payload_tenant_mismatch(client: TestClient) -> None:
    response = client.post(
        "/v1/cycles",
        headers={"X-User-Id": "user-1", "X-Tenant-Id": "tenant-a", "Idempotency-Key": "idem-tenant-mismatch"},
        json={"project_id": "proj-1", "user_input": "tenant mismatch", "tenant_id": "tenant-b"},
    )

    assert response.status_code == 403
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "forbidden"
    assert body["error"]["message"] == "tenant mismatch between auth context and payload"


def test_cycle_events_stream_returns_snapshot_and_result_for_terminal_cycle(client: TestClient, db_session) -> None:
    create = client.post(
        "/v1/cycles",
        headers={"X-User-Id": "stream-owner", "Idempotency-Key": "stream-001"},
        json={"project_id": "proj-stream", "user_input": "stream terminal status"},
    )
    cycle_id = create.json()["data"]["cycle_id"]

    cycle = db_session.get(Cycle, cycle_id)
    assert cycle is not None
    cycle.current_state = CycleState.TERMINALIZED
    cycle.user_status = UserStatus.COMPLETED
    cycle.updated_at = datetime.now(timezone.utc)
    db_session.commit()

    with client.stream("GET", f"/v1/cycles/{cycle_id}/events", headers={"X-User-Id": "stream-owner"}) as response:
        assert response.status_code == 200
        payload = "".join(response.iter_text())

    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: cycle.snapshot" in payload
    assert "event: cycle.result" in payload
    assert f'"cycle_id":"{cycle_id}"' in payload
    assert '"final_state":"terminalized"' in payload



def test_cycle_events_stream_emits_heartbeat_and_timeout_for_non_terminal_cycle(client: TestClient) -> None:
    create = client.post(
        "/v1/cycles",
        headers={"X-User-Id": "stream-timeout-owner", "Idempotency-Key": "stream-002"},
        json={"project_id": "proj-stream", "user_input": "stream pending status"},
    )
    cycle_id = create.json()["data"]["cycle_id"]

    with client.stream(
        "GET",
        f"/v1/cycles/{cycle_id}/events",
        headers={"X-User-Id": "stream-timeout-owner"},
        params={"poll_interval_seconds": 0.01, "heartbeat_seconds": 0.01, "stream_timeout_seconds": 0.04},
    ) as response:
        assert response.status_code == 200
        payload = "".join(response.iter_text())

    assert "event: cycle.snapshot" in payload
    assert "event: heartbeat" in payload
    assert "event: stream.timeout" in payload



def test_cycle_events_stream_enforces_owner_scope(client: TestClient) -> None:
    create = client.post(
        "/v1/cycles",
        headers={"X-User-Id": "stream-secure-owner", "Idempotency-Key": "stream-003"},
        json={"project_id": "proj-stream", "user_input": "stream owner scope"},
    )
    cycle_id = create.json()["data"]["cycle_id"]

    forbidden = client.get(f"/v1/cycles/{cycle_id}/events", headers={"X-User-Id": "other-user"})
    assert forbidden.status_code == 403
