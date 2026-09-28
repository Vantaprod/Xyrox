"""
Xyrox — Agent (Phase 2, File 10)

The agent loop. This is the code that turns a chat message into
a real action (or a real answer).

The loop (per Master Command §4, §5):
    1. Build messages = [system prompt] + [conversation history] + [new user msg]
    2. Send to AI, with tool schemas attached.
    3. If the AI returns tool calls:
         - Validate the tool exists.
         - Execute it against the real tool registry.
         - Feed the result back to the AI as a "tool" message.
         - Loop.
    4. If the AI returns final text (no tool calls): return it.

Strict rules:
- The model NEVER touches the database. It only requests tools.
- Every tool call is recorded in the AgentResult for auditing.
- Loops are capped (default 5 iterations) to prevent runaway behavior.
- Tool errors are fed back to the AI so it can respond intelligently,
  but they are also recorded for the audit log.
- No fabrication. The agent reports exactly what happened.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from app.backend.ai.base import AIProvider, AIProviderError, AIResponse
from app.backend.ai.factory import get_provider
from app.backend.agents.prompts import build_system_prompt
from app.backend.config import settings
from app.backend.tools import build_default_registry
from app.backend.tools.base import (
    ToolError,
    ToolNotFoundError,
    ToolValidationError,
    ToolExecutionError,
)
from app.backend.tools.registry import ToolRegistry


# ============================================================
# RESULT TYPES
# ============================================================
@dataclass
class ToolCallRecord:
    """A record of one tool call made during an agent turn."""
    name: str
    arguments: dict
    success: bool
    result: Any = None
    error: Optional[str] = None


@dataclass
class AgentResult:
    """
    The complete result of one agent turn.

    final_message : What the AI said to the user (text only).
    tool_calls    : Every tool call the AI requested, in order.
    iterations    : How many AI calls were needed.
    model         : The exact model used.
    provider      : The provider name.
    conversation  : The full conversation after this turn
                    (including system, user, assistant, tool msgs).
    """
    final_message: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    iterations: int = 0
    model: str = ""
    provider: str = ""
    conversation: list[dict] = field(default_factory=list)


# ============================================================
# AGENT
# ============================================================
class Agent:
    """
    A stateful conversational agent.

    Typical usage:
        agent = Agent()
        result = agent.chat("Create a task to call Promise tomorrow.")
        print(result.final_message)
        for tc in result.tool_calls:
            print(tc.name, tc.arguments, tc.success)
    """

    def __init__(
        self,
        provider: Optional[AIProvider] = None,
        registry: Optional[ToolRegistry] = None,
        timezone: Optional[str] = None,
        max_iterations: int = 5,
        extra_system_context: str = "",
    ):
        self.provider = provider or get_provider()
        self.registry = registry or build_default_registry()
        self.timezone = timezone or settings.TZ
        self.max_iterations = max_iterations
        self.extra_system_context = extra_system_context

        # Conversation always begins with the system prompt
        self.conversation: list[dict] = [
            {
                "role": "system",
                "content": build_system_prompt(
                    timezone=self.timezone,
                    extra=self.extra_system_context,
                ),
            }
        ]

    # ------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------
    def chat(self, user_message: str) -> AgentResult:
        """
        Send a user message and run the agent loop until the AI
        produces a final text response or the iteration cap is hit.

        The conversation history is preserved between calls.
        """
        if not isinstance(user_message, str) or not user_message.strip():
            raise ValueError("user_message must be a non-empty string.")

        # Append the user's message
        self.conversation.append({
            "role": "user",
            "content": user_message,
        })

        return self._run_loop()

    def reset(self) -> None:
        """
        Clear the conversation. Keeps the system prompt.
        Useful for tests and for the user to start fresh.
        """
        self.conversation = [
            {
                "role": "system",
                "content": build_system_prompt(
                    timezone=self.timezone,
                    extra=self.extra_system_context,
                ),
            }
        ]

    # ------------------------------------------------------------
    # THE LOOP
    # ------------------------------------------------------------
    def _run_loop(self) -> AgentResult:
        tool_records: list[ToolCallRecord] = []
        iterations = 0
        model_used = ""
        provider_used = ""
        final_content = ""

        while iterations < self.max_iterations:
            iterations += 1

            # Send the whole conversation + tool schemas to the AI
            try:
                response: AIResponse = self.provider.chat(
                    messages=self.conversation,
                    tools=self.registry.to_ai_schema(),
                    temperature=0.2,
                )
            except AIProviderError as exc:
                # Provider failure: return what we have, no fabrication
                return AgentResult(
                    final_message=(
                        f"I could not reach the AI provider. Error: {exc}"
                    ),
                    tool_calls=tool_records,
                    iterations=iterations,
                    model=model_used or self.provider.model,
                    provider=self.provider.name,
                    conversation=list(self.conversation),
                )

            model_used = response.model
            provider_used = response.provider

            # No tool calls → this is the final answer
            if not response.tool_calls:
                final_content = response.content or ""
                # Append the assistant message to history
                self.conversation.append({
                    "role": "assistant",
                    "content": final_content,
                })
                break

            # Tool calls present → record the assistant message,
            # then execute each tool call in order.
            self.conversation.append({
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": [
                    {
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"],
                        }
                    }
                    for tc in response.tool_calls
                ],
            })

            for tool_call in response.tool_calls:
                record = self._execute_tool(
                    name=tool_call.get("name", ""),
                    arguments=tool_call.get("arguments", {}) or {},
                )
                tool_records.append(record)

                # Feed the result back to the AI as a "tool" message.
                # The AI uses this to decide its next move.
                self.conversation.append({
                    "role": "tool",
                    "content": self._format_tool_result_for_ai(record),
                })

        # If we exhausted iterations without a final message,
        # produce an honest report — do not pretend success.
        if not final_content:
            if tool_records:
                summary_lines = [
                    f"- {r.name}: {'success' if r.success else 'failed'}"
                    for r in tool_records
                ]
                final_content = (
                    "I reached the maximum number of tool-call iterations "
                    "without producing a final response. Here is what was "
                    "executed so far:\n" + "\n".join(summary_lines)
                )
            else:
                final_content = (
                    "I could not produce a final response within the "
                    "iteration limit."
                )
            self.conversation.append({
                "role": "assistant",
                "content": final_content,
            })

        return AgentResult(
            final_message=final_content,
            tool_calls=tool_records,
            iterations=iterations,
            model=model_used,
            provider=provider_used,
            conversation=list(self.conversation),
        )

    # ------------------------------------------------------------
    # TOOL EXECUTION
    # ------------------------------------------------------------
    def _execute_tool(self, name: str, arguments: dict) -> ToolCallRecord:
        """
        Execute a single tool call. Never raises — always returns a
        ToolCallRecord describing the outcome, so the loop can continue.
        """
        if not name:
            return ToolCallRecord(
                name="",
                arguments=arguments,
                success=False,
                error="The AI requested a tool with no name.",
            )

        try:
            result = self.registry.execute(name, arguments)
            return ToolCallRecord(
                name=name,
                arguments=arguments,
                success=True,
                result=result,
            )
        except ToolNotFoundError as exc:
            return ToolCallRecord(
                name=name,
                arguments=arguments,
                success=False,
                error=f"Tool not found: {exc}",
            )
        except ToolValidationError as exc:
            return ToolCallRecord(
                name=name,
                arguments=arguments,
                success=False,
                error=f"Invalid arguments: {exc}",
            )
        except ToolExecutionError as exc:
            return ToolCallRecord(
                name=name,
                arguments=arguments,
                success=False,
                error=f"Tool execution failed: {exc}",
            )
        except ToolError as exc:
            return ToolCallRecord(
                name=name,
                arguments=arguments,
                success=False,
                error=f"Tool error: {exc}",
            )
        except Exception as exc:
            return ToolCallRecord(
                name=name,
                arguments=arguments,
                success=False,
                error=f"Unexpected error: {exc}",
            )

    @staticmethod
    def _format_tool_result_for_ai(record: ToolCallRecord) -> str:
        """
        Convert a ToolCallRecord into a string the AI can read as the
        result of the tool call. Must be JSON-serializable text.
        """
        if record.success:
            payload = {
                "tool": record.name,
                "success": True,
                "result": record.result,
            }
        else:
            payload = {
                "tool": record.name,
                "success": False,
                "error": record.error,
            }
        try:
            return json.dumps(payload, default=str)
        except Exception:
            # Fallback for exotic result types
            return f"tool={record.name} success={record.success} error={record.error}"