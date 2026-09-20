"""HTTP endpoint for ADR-013 control-plane.

POST /sessions/{session_id}/cancel — validates session, publishes cancel via Redis,
returns 202 immediately (fire-and-forget actual cancellation).
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .publisher import CancelPublisher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions")

VALID_REASONS = {"user_cancelled", "tab_closed", "hidden", "timeout", "system_error"}


class CancelRequest(BaseModel):
    reason: str = Field(default="user_cancelled")
    user_id: str | None = Field(default=None)


class CancelResponse(BaseModel):
    status: str
    session_id: str


class SessionState:
    """In-memory session lifecycle tracker used by the cancel endpoint."""

    def __init__(self) -> None:
        self._active: set[str] = set()
        self._cancelled: set[str] = set()

    def is_active(self, session_id: str) -> bool:
        return session_id in self._active

    def is_cancelled(self, session_id: str) -> bool:
        return session_id in self._cancelled

    def activate(self, session_id: str) -> None:
        self._active.add(session_id)
        self._cancelled.discard(session_id)

    def mark_cancelled(self, session_id: str) -> None:
        self._cancelled.add(session_id)

    def complete(self, session_id: str) -> None:
        self._active.discard(session_id)


_state = SessionState()


def get_session_state() -> SessionState:
    return _state


def build_cancel_router(
    publisher: CancelPublisher,
    state: SessionState | None = None,
) -> APIRouter:
    """Create the cancel router wired to the given publisher and session state."""

    state = state or _state

    @router.post("/{session_id}/cancel", response_model=CancelResponse, status_code=202)
    async def cancel_session(session_id: str, body: CancelRequest) -> CancelResponse:
        if body.reason not in VALID_REASONS:
            raise HTTPException(status_code=422, detail=f"Invalid reason: {body.reason}")
        if not state.is_active(session_id):
            raise HTTPException(status_code=404, detail="Session not found")
        if state.is_cancelled(session_id):
            raise HTTPException(status_code=409, detail="Session already cancelled")

        await publisher.publish(session_id, body.reason, body.user_id)
        state.mark_cancelled(session_id)
        logger.info(
            "Cancel request received for session %s, reason=%s", session_id, body.reason
        )
        return CancelResponse(status="cancel_queued", session_id=session_id)

    return router