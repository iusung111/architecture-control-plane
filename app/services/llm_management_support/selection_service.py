from __future__ import annotations

from .selection_assignment import SelectionAssignmentMixin
from .selection_routing import SelectionRoutingMixin


class SelectionServiceMixin(SelectionAssignmentMixin, SelectionRoutingMixin):
    pass
