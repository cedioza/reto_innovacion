"""In-memory conversation repository.

Stores conversation sessions by session_id.
Thread-safe for single-process use.
"""

from __future__ import annotations

from typing import Any


class ConversationRepository:
    def __init__(self) -> None:
        self._sessions: dict[str, Any] = {}

    def save(self, session_id: str, session: Any) -> None:
        self._sessions[session_id] = session

    def find(self, session_id: str) -> Any | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def count(self) -> int:
        return len(self._sessions)
