"""
Xyrox — Tools Package (Phase 2, File 7)

Central builder for the default tool registry.

Call build_default_registry() to get a registry containing every
tool Xyrox currently knows how to use. As new tools are added,
this file is the single place to register them.
"""

from app.backend.tools.registry import ToolRegistry
from app.backend.tools.tasks import register_task_tools


def build_default_registry() -> ToolRegistry:
    """
    Build and return the default ToolRegistry containing all
    currently implemented tools.
    """
    registry = ToolRegistry()
    register_task_tools(registry)
    return registry