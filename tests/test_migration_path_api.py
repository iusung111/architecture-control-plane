from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def test_create_cycle_via_alembic_migrated_schema(migrated_client: TestClient) -> None:
    response = migrated_client.post(
        "/v1/cycles",
        headers={
            "X-User-Id": "user-migrated",
            "X-User-Role": "approver",
            "X-Tenant-Id": "tenant-a",
            "Idempotency-Key": "idem-migrated-001",
        },
        json={
            "project_id": "project-a",
            "user_input": "run migrated path",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["data"]["cycle_id"], str)
    assert body["data"]["cycle_id"]


def test_invalid_cycle_state_is_rejected_by_db_constraint(migrated_db_session) -> None:
    with __import__("pytest").raises(IntegrityError):
        migrated_db_session.execute(
            text(
                """
                INSERT INTO cycles (
                    cycle_id, tenant_id, tenant_scope, project_id, owner_user_id, current_state, user_status,
                    latest_iteration_no, active_approval_id, result_ref, idempotency_key,
                    request_fingerprint, created_at, updated_at, version
                ) VALUES (
                    :cycle_id, :tenant_id, :tenant_scope, :project_id, :owner_user_id, :current_state, :user_status,
                    :latest_iteration_no, :active_approval_id, :result_ref, :idempotency_key,
                    :request_fingerprint, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :version
                )
                """
            ),
            {
                "cycle_id": "cycle-invalid-state",
                "tenant_id": "tenant-a",
                "tenant_scope": "tenant-a",
                "project_id": "project-a",
                "owner_user_id": "user-a",
                "current_state": "definitely_not_a_real_state",
                "user_status": "accepted",
                "latest_iteration_no": 0,
                "active_approval_id": None,
                "result_ref": None,
                "idempotency_key": "idem-invalid-state",
                "request_fingerprint": "fp-invalid-state",
                "version": 1,
            },
        )
        migrated_db_session.commit()



def test_cycles_idempotency_unique_constraint_is_tenant_scoped(migrated_db_session) -> None:
    migrated_db_session.execute(
        text(
            """
            INSERT INTO cycles (
                cycle_id, tenant_id, tenant_scope, project_id, owner_user_id, current_state, user_status,
                latest_iteration_no, active_approval_id, result_ref, idempotency_key,
                request_fingerprint, created_at, updated_at, version
            ) VALUES (
                :cycle_id, :tenant_id, :tenant_scope, :project_id, :owner_user_id, :current_state, :user_status,
                :latest_iteration_no, :active_approval_id, :result_ref, :idempotency_key,
                :request_fingerprint, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :version
            )
            """
        ),
        {
            "cycle_id": "cycle-tenant-a",
            "tenant_id": "tenant-a",
            "tenant_scope": "tenant-a",
            "project_id": "project-a",
            "owner_user_id": "user-a",
            "current_state": "intent_accepted",
            "user_status": "accepted",
            "latest_iteration_no": 0,
            "active_approval_id": None,
            "result_ref": None,
            "idempotency_key": "same-idem",
            "request_fingerprint": "fp-tenant-a",
            "version": 1,
        },
    )
    migrated_db_session.execute(
        text(
            """
            INSERT INTO cycles (
                cycle_id, tenant_id, tenant_scope, project_id, owner_user_id, current_state, user_status,
                latest_iteration_no, active_approval_id, result_ref, idempotency_key,
                request_fingerprint, created_at, updated_at, version
            ) VALUES (
                :cycle_id, :tenant_id, :tenant_scope, :project_id, :owner_user_id, :current_state, :user_status,
                :latest_iteration_no, :active_approval_id, :result_ref, :idempotency_key,
                :request_fingerprint, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :version
            )
            """
        ),
        {
            "cycle_id": "cycle-tenant-b",
            "tenant_id": "tenant-b",
            "tenant_scope": "tenant-b",
            "project_id": "project-a",
            "owner_user_id": "user-a",
            "current_state": "intent_accepted",
            "user_status": "accepted",
            "latest_iteration_no": 0,
            "active_approval_id": None,
            "result_ref": None,
            "idempotency_key": "same-idem",
            "request_fingerprint": "fp-tenant-b",
            "version": 1,
        },
    )
    migrated_db_session.commit()
