from __future__ import annotations

from .write_workspace_comments import CycleWriteWorkspaceCommentMixin
from .write_workspace_filters import CycleWriteWorkspaceFilterMixin
from .write_workspace_runtime import CycleWriteWorkspaceRuntimeMixin


class CycleWriteWorkspaceMixin(
    CycleWriteWorkspaceCommentMixin,
    CycleWriteWorkspaceFilterMixin,
    CycleWriteWorkspaceRuntimeMixin,
):
    """Workspace writes grouped by discussion, saved-filter, and runtime registration flows."""


__all__ = ["CycleWriteWorkspaceMixin"]
