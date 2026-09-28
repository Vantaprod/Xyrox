"""
Xyrox — Tools Package (Phase 4)

Central builder for the default tool registry. As new tools are
added, register them here.
"""

from app.backend.tools.registry import ToolRegistry
from app.backend.tools.tasks import register_task_tools
from app.backend.tools.work_logs import register_work_log_tools


def build_default_registry() -> ToolRegistry:
    """
    Build and return the default ToolRegistry containing all
    currently implemented tools.
    """
    registry = ToolRegistry()
    register_task_tools(registry)
    register_work_log_tools(registry)
    return registry