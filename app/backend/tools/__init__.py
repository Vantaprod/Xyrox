"""
Xyrox — Tools Package (Phase 4.4)
"""

from app.backend.tools.registry import ToolRegistry
from app.backend.tools.tasks import register_task_tools
from app.backend.tools.work_logs import register_work_log_tools
from app.backend.tools.reports import register_report_tools
from app.backend.tools.exports import register_export_tools


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_task_tools(registry)
    register_work_log_tools(registry)
    register_report_tools(registry)
    register_export_tools(registry)
    return registry