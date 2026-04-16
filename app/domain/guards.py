from app.domain.enums import CycleState


class StateConflictError(ValueError):
    pass


RETRY_ALLOWED_STATES = {CycleState.VERIFICATION_FAILED}
REPLAN_ALLOWED_STATES = {CycleState.VERIFICATION_FAILED}


def ensure_retry_allowed(current_state: str) -> None:
    if current_state not in RETRY_ALLOWED_STATES:
        raise StateConflictError(f"retry not allowed from state={current_state}")


def ensure_replan_allowed(current_state: str) -> None:
    if current_state not in REPLAN_ALLOWED_STATES:
        raise StateConflictError(f"replan not allowed from state={current_state}")


def ensure_result_available(current_state: str) -> None:
    if current_state not in {CycleState.TERMINALIZED, CycleState.TERMINAL_FAIL}:
        raise StateConflictError(f"result not available from state={current_state}")
