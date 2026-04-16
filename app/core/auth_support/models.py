from dataclasses import dataclass


@dataclass(slots=True)
class AuthContext:
    user_id: str
    role: str
    tenant_id: str | None


class AuthError(ValueError):
    def __init__(self, message: str, *, status_code: int = 401):
        super().__init__(message)
        self.status_code = status_code
