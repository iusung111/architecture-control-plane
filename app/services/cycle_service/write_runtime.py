from __future__ import annotations

from .write_runtime_actions import CycleWriteRuntimeActionMixin
from .write_runtime_assignments import CycleWriteRuntimeAssignmentMixin


class CycleWriteRuntimeMixin(
    CycleWriteRuntimeAssignmentMixin,
    CycleWriteRuntimeActionMixin,
):
    """Runtime writes grouped by agent assignment and runtime action flows."""


__all__ = ["CycleWriteRuntimeMixin"]
