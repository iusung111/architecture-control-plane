# Coverage expansion report

- Baseline total coverage: 87.34%
- Updated total coverage: 89.20%
- Test results: 298 passed, 6 skipped, 1 warning

## Added tests

- `tests/test_coverage_expansion.py`
  - bearer auth helper validation and decode error handling
  - FastAPI lifespan init/shutdown order
  - PostgreSQL backup CLI parser/defaults/dispatch/validation
  - tracing helper parsing/context/span fallback behavior

## Biggest coverage gains

- `app/ops/postgres_backup_restore_support/cli.py`: 9.02% → 97.54% (+88.52)
- `app/bootstrap/lifespan.py`: 63.16% → 100.00% (+36.84)
- `app/core/auth_support/bearer.py`: 45.83% → 80.56% (+34.72)
- `app/core/telemetry_support/tracing.py`: 52.98% → 70.20% (+17.22)

## Remaining lowest-coverage modules

- `app/services/cycle_service/query_cycles.py` — 52.48% (101 statements)
- `app/api/routes/cycles/cycle_actions.py` — 61.29% (62 statements)
- `app/services/llm_management.py` — 66.67% (12 statements)
- `app/services/orchestration_support/retry_handlers.py` — 66.67% (21 statements)
- `app/ops/postgres_backup_restore_support/object_store.py` — 67.96% (103 statements)
- `app/core/telemetry_support/tracing.py` — 70.20% (151 statements)
- `app/ops/postgres_backup_restore_support/commands.py` — 71.28% (94 statements)
- `app/api/routes/cycles/workspace.py` — 71.43% (105 statements)
- `app/services/management_config_support/drill_service.py` — 72.97% (111 statements)
- `app/api/routes/cycles/runtime.py` — 74.19% (62 statements)
- `app/services/cycle_service/assignment_helpers.py` — 74.19% (62 statements)
- `app/services/llm_access_support/common.py` — 74.83% (151 statements)

## Assessment

- Coverage is broader and more diverse than before; it now includes unit tests for parser/CLI branches, auth helper branches, lifecycle hooks, and tracing helpers.
- The next gaps are no longer basic utility branches; the lowest areas are now mostly domain-heavy flows (`query_cycles`, cycle route actions/workspace) and optional integrations (`object_store`, `commands`, `oidc`).