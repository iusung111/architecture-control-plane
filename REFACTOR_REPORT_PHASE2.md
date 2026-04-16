# Refactor Report - Phase 2

## Scope
Continued from the previous route/bootstrap refactor and included validation work requested in the follow-up.

## Environment setup
Installed missing runtime/test dependencies in the container so validation could run:
- SQLAlchemy
- Alembic
- psycopg[binary]
- openai
- opentelemetry SDK/exporter
- redis
- related transitive dependencies

## Code changes
### 1) Fixed regression introduced by previous route package split
- File: `app/api/routes/cycles/common.py`
- Added `__all__` export coverage so shared SSE helper functions used via `from .common import *` are exported, including internal helper names like `_snapshot_version`, `_board_snapshot_version`, `_format_sse_event`.
- This fixed the runtime `NameError` in the cycle SSE stream path.

### 2) Removed duplicate runtime SSE route definition
- File: `app/api/routes/cycles/runtime.py`
- Removed the duplicated `/runtime/registrations/{runtime_id}/actions/{action_id}/events` route.
- Canonical definition now lives in `app/api/routes/cycles/runtime_streams.py`.
- Result: eliminated duplicate OpenAPI operation IDs and tightened route ownership.

### 3) Added regression tests
- File: `tests/test_openapi_contract.py`
- Added `test_openapi_operation_ids_are_unique`
- Added `test_cycle_route_common_star_import_exposes_internal_sse_helpers`

## Validation
### Test status
Executed full test suite after environment setup and fixes.

Result:
- `268 passed`
- `6 skipped`
- `1 warning`

Command used:
```bash
pytest -q
```

### Remaining warning
- `PendingDeprecationWarning` from third-party package loading `python_multipart`
- This is external/tooling-level and did not block application validation.

## Current structure status
### Recent route package sizes
- `app/main.py` -> 54 lines
- `app/api/routes/cycles/runtime_streams.py` -> 94 lines
- `app/api/routes/cycles/runtime.py` -> 165 lines
- `app/api/routes/cycles/cycle_streams.py` -> 202 lines

### Remaining files above 300 lines
These still need staged refactoring in later phases:
- `app/services/cycles.py` -> 2403
- `app/services/remote_workspace.py` -> 1492
- `app/ops/postgres_backup_restore.py` -> 1092
- `app/services/llm_access.py` -> 917
- `app/core/rate_limit.py` -> 745
- `app/schemas/cycles.py` -> 649
- `app/core/telemetry.py` -> 633
- `app/services/llm_management.py` -> 610
- `app/services/management_config.py` -> 559
- `app/core/config.py` -> 461
- `app/services/orchestration.py` -> 393
- `app/core/auth.py` -> 315
- `app/api/routes/remote_workspace.py` -> 306

## Recommended next refactor order
1. `app/api/routes/remote_workspace.py`
2. `app/core/auth.py`
3. `app/core/config.py`
4. `app/services/orchestration.py`
5. `app/services/cycles.py` (domain-sliced, staged)

## Notes
The codebase is now in a verified state after the previous refactor, with the major regression closed and automated coverage added to prevent recurrence.
