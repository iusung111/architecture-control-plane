# Agent Instructions

## Goal
Implement the control-plane service for cycle orchestration. Use the contracts under `docs/contracts/` as the source of truth.

## Read First
1. `README.md`
2. `docs/contracts/openapi.yaml`
3. `docs/contracts/state_transition_matrix.md`
4. `docs/contracts/approval_state_machine.md`
5. `app/domain/enums.py`
6. `app/domain/guards.py`
7. `app/db/models.py`
8. `alembic/versions/0001_initial.py`

## Rules
- Keep route handlers thin. Business logic belongs in services.
- Repositories perform persistence only. They do not decide allowed state transitions.
- Use a single transaction for state update + job enqueue + outbox insert.
- Do not trust actor identity from request bodies. Resolve it from request context.
- Raw LLM output must be validated before policy decisions.
- Preserve the response envelope shape already used by the API.
- Expand tests when you add behavior. Prefer contract-focused tests.

## Commands
- Install: `pip install -e .[dev]`
- Run app: `uvicorn app.main:app --reload`
- Lint: `ruff check .`
- Test: `pytest`
- Migrate: `alembic upgrade head`

## Priority Gaps
- Add richer OpenAPI examples and response components when changing endpoints.
- Add integration tests before adding worker consumers.
- Keep `docs/contracts/*` and `app/schemas/*` aligned.
