"""
Xyrox — Tool Registry (Phase 2, File 5b)

The registry is the single source of truth for which tools exist.
- The AI receives the schema list (to_ai_schema) when it needs to
  decide which tool to call.
- The application receives the tool name + arguments and executes the
  real function (execute).

Design rules (Master Command §4, §5):
- Tools must be registered explicitly. There is no auto-discovery magic.
- Executing an unregistered tool is a hard error, never a silent no-op.
- Arguments are always validated as a dict before calling the tool.
- Tool function errors are wrapped in ToolExecutionError, preserving
  the original exception via `raise ... from exc`.
"""

from typing import Any

from app.backend.tools.base import (
    Tool,
    ToolError,
    ToolNotFoundError,
    ToolValidationError,
    ToolExecutionError,
)


class ToolRegistry:
    """
    A registry of tools available to the agent.

    Typical usage:
        registry = ToolRegistry()
        registry.register(Tool(name="create_task", ...))
        schema = registry.to_ai_schema()   # passed to the AI
        result = registry.execute("create_task", {"title": "..."})
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    # ------------------------------------------------------------
    # REGISTRATION
    # ------------------------------------------------------------
    def register(self, tool: Tool) -> None:
        """
        Register a tool. Raises ToolError if:
        - name is empty or not a string
        - name is already registered (no silent overwrite)
        - func is not callable
        """
        if not isinstance(tool.name, str) or not tool.name.strip():
            raise ToolError("Tool name must be a non-empty string.")

        if tool.name in self._tools:
            raise ToolError(
                f"Tool '{tool.name}' is already registered. "
                f"Duplicate registration is not allowed."
            )

        if not callable(tool.func):
            raise ToolError(
                f"Tool '{tool.name}' has a non-callable func."
            )

        if not isinstance(tool.parameters, dict):
            raise ToolError(
                f"Tool '{tool.name}' parameters must be a dict."
            )

        self._tools[tool.name] = tool

    # ------------------------------------------------------------
    # LOOKUP
    # ------------------------------------------------------------
    def get(self, name: str) -> Tool:
        """Return the tool with the given name, or raise ToolNotFoundError."""
        if name not in self._tools:
            raise ToolNotFoundError(
                f"Tool '{name}' is not registered. "
                f"Available tools: {self.names()}"
            )
        return self._tools[name]

    def all(self) -> list[Tool]:
        """Return every registered tool."""
        return list(self._tools.values())

    def names(self) -> list[str]:
        """Return the sorted list of tool names."""
        return sorted(self._tools.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    # ------------------------------------------------------------
    # SCHEMA FOR THE AI
    # ------------------------------------------------------------
    def to_ai_schema(self) -> list[dict]:
        """
        Return the tool definitions in the format Ollama and OpenAI
        expect. Each entry:
            {
                "type": "function",
                "function": {
                    "name": "...",
                    "description": "...",
                    "parameters": { <JSON schema> }
                }
            }
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
        ]

    # ------------------------------------------------------------
    # EXECUTION
    # ------------------------------------------------------------
    def execute(self, name: str, arguments: dict) -> Any:
        """
        Execute a registered tool by name.

        - Tool must exist (else ToolNotFoundError).
        - Arguments must be a dict (else ToolValidationError).
        - Tool function is called with **arguments.
        - Any TypeError (wrong signature) is a ToolValidationError.
        - Any other exception is wrapped in ToolExecutionError.
        - ToolError subclasses raised by the tool propagate unchanged,
          so tools can raise domain-specific errors.
        """
        tool = self.get(name)

        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise ToolValidationError(
                f"Arguments for tool '{name}' must be a dict, "
                f"got {type(arguments).__name__}."
            )

        try:
            return tool.func(**arguments)
        except ToolError:
            # A tool is allowed to raise its own ToolError subclass
            # (e.g. ToolValidationError) — propagate it unchanged.
            raise
        except TypeError as exc:
            raise ToolValidationError(
                f"Tool '{name}' called with invalid arguments: {exc}"
            ) from exc
        except Exception as exc:
            raise ToolExecutionError(
                f"Tool '{name}' failed during execution: {exc}"
            ) from exc