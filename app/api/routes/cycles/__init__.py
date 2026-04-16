from .common import router

# Import route modules for side effects so handlers are registered on the shared router.
from . import cycle_actions, cycle_queries, cycle_streams, runtime, runtime_streams, workspace  # noqa: F401

__all__ = ["router"]
