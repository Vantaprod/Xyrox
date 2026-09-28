"""
Xyrox — Chat Route (Phase 3, File 9)

POST /api/v1/chat     — send a message, get AI response
POST /api/v1/chat/reset — clear the user's conversation history

Rules:
- Every request requires authentication (Bearer token).
- The agent runs synchronously in a worker thread (FastAPI handles this).
- Errors are surfaced as HTTP 500 with a clear message — never swallowed.
- The response exposes exactly what happened: text + tool calls.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from app.backend.api.deps import get_current_user
from app.backend.models.models import User
from app.backend.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatResetResponse,
    ToolCallInfo,
)
from app.backend.services.agent_service import (
    chat_with_agent,
    reset_agent,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    """
    Send a message to Xyrox. Runs the agent loop and returns the
    final text response and any tool calls executed.
    """
    try:
        result = chat_with_agent(current_user, payload.message)
    except Exception as exc:
        # Surface the failure honestly. Do not invent a response.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent execution failed: {exc}",
        )

    return ChatResponse(
        message=result.final_message,
        tool_calls=[
            ToolCallInfo(
                name=tc.name,
                arguments=tc.arguments,
                success=tc.success,
                result=tc.result,
                error=tc.error,
            )
            for tc in result.tool_calls
        ],
        iterations=result.iterations,
        model=result.model,
        provider=result.provider,
        timestamp=datetime.now(timezone.utc),
    )


@router.post("/reset", response_model=ChatResetResponse)
def reset(
    current_user: User = Depends(get_current_user),
) -> ChatResetResponse:
    """
    Clear the current user's conversation history.
    Keeps the same Agent instance; only the message list is reset.
    """
    existed = reset_agent(current_user.id)
    return ChatResetResponse(
        cleared=existed,
        message=(
            "Conversation cleared."
            if existed
            else "No active conversation to clear."
        ),
    )