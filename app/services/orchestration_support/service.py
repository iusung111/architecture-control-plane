from __future__ import annotations

from .base import OrchestrationBase
from .retry_handlers import RetryHandlersMixin
from .verification_handlers import VerificationHandlersMixin


class CycleExecutionOrchestrator(
    RetryHandlersMixin,
    VerificationHandlersMixin,
    OrchestrationBase,
):
    pass
