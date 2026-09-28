"""
Xyrox — Tool Base (Phase 2, File 5a)

Defines the Tool dataclass and the exception hierarchy used by the
tool system.

Design rules (Master Command §4, §5, §35):
- Tools have a name, a description for the AI, a JSON schema for their
  parameters, and a Python callable that does the actual work.
- Every failure path has its own exception type. Nothing is swallowed.
- No tool exists unless it has a real, tested implementation.
"""

from dataclasses import dataclass
from typing import Any, Callable


# ============================================================
# EXCEPTIONS
# ============================================================
class ToolError(Exception):
    """Base class for all tool-related errors."""
    pass


class ToolNotFoundError(ToolError):
    """Raised when a requested tool is not registered."""
    pass


class ToolValidationError(ToolError):
    """
    Raised when the AI supplies arguments that do not match the tool's
    expected schema, or when a tool is called with the wrong signature.
    """
    pass


class ToolExecutionError(ToolError):
    """
    Raised when a tool's function raises an exception during execution.
    The original error is chained (raise ... from exc) so the traceback
    is preserved for logs.
    """
    pass


# ============================================================
# TOOL
# ============================================================
@dataclass
class Tool:
    """
    A single callable tool that the AI can request.

    Attributes:
        name:        Unique identifier, lowercase, snake_case.
                     Example: "create_task".
        description: Natural-language description shown to the AI so it
                     knows when to use the tool.
        parameters:  JSON schema describing the tool's arguments.
                     Must be an object schema with "properties" and
                     "required" keys. This is passed to Ollama / OpenAI
                     verbatim.
        func:        The Python callable that executes the tool.
                     Receives keyword arguments matching the schema.
                     Returns any JSON-serializable value.
    """
    name: str
    description: str
    parameters: dict
    func: Callable[..., Any]