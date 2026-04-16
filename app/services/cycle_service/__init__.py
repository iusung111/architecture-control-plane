from .query_assignment_insights import CycleQueryAssignmentInsightMixin
from .query_assignments import CycleQueryAssignmentMixin
from .query_cycle_timeline import CycleQueryTimelineMixin
from .query_cycles import CycleQueryCycleMixin
from .query_runtime import CycleQueryRuntimeMixin
from .query_support import CycleQuerySupportMixin
from .query_workspace import CycleQueryWorkspaceMixin
from .query_workspace_discussions import CycleQueryWorkspaceDiscussionMixin
from .stream_service import CycleStreamService, CycleStreamSnapshot
from .write_base import CycleWriteBaseMixin
from .write_runtime import CycleWriteRuntimeMixin
from .write_transitions import CycleWriteTransitionMixin
from .write_workspace import CycleWriteWorkspaceMixin


class CycleWriteService(
    CycleWriteBaseMixin,
    CycleWriteWorkspaceMixin,
    CycleWriteRuntimeMixin,
    CycleWriteTransitionMixin,
):
    pass


class CycleQueryService(
    CycleQuerySupportMixin,
    CycleQueryCycleMixin,
    CycleQueryWorkspaceMixin,
    CycleQueryWorkspaceDiscussionMixin,
    CycleQueryRuntimeMixin,
    CycleQueryAssignmentMixin,
    CycleQueryAssignmentInsightMixin,
    CycleQueryTimelineMixin,
):
    pass


__all__ = [
    "CycleQueryService",
    "CycleWriteService",
    "CycleStreamService",
    "CycleStreamSnapshot",
]
