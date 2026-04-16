from __future__ import annotations

from .query_runtime_actions import CycleQueryRuntimeActionMixin
from .query_runtime_panel import CycleQueryRuntimePanelMixin


class CycleQueryRuntimeMixin(
    CycleQueryRuntimePanelMixin,
    CycleQueryRuntimeActionMixin,
):
    """Runtime queries grouped by panel/registration views and action history."""


__all__ = ["CycleQueryRuntimeMixin"]
