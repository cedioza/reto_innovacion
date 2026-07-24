"""In-memory conversation repository.

Stores conversation sessions by session_id.
Thread-safe for single-process use.
"""

from __future__ import annotations

from app.schemas.conversation import ConversationResponse


class ConversationRepository:
    def __init__(self) -> None:
        self._sessions: dict[str, ConversationResponse] = {}

    def save(self, session: ConversationResponse) -> None:
        self._sessions[session.session_id] = session

    def find(self, session_id: str) -> ConversationResponse | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def count(self) -> int:
        return len(self._sessions)
