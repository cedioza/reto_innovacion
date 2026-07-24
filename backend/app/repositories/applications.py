"""In-memory application repository.

Stores consented applications by session_id.
"""

from __future__ import annotations

from app.schemas.conversation import ConsentedApplication


class ApplicationRepository:
    def __init__(self) -> None:
        self._apps: dict[str, tuple[str, ConsentedApplication]] = {}

    def save(
        self,
        session_id: str,
        evidence_hash: str,
        application: ConsentedApplication,
    ) -> None:
        self._apps[session_id] = (evidence_hash, application)

    def find(
        self, session_id: str
    ) -> ConsentedApplication | None:
        record = self._apps.get(session_id)
        return record[1] if record else None

    def get_evidence_hash(self, session_id: str) -> str | None:
        record = self._apps.get(session_id)
        return record[0] if record else None

    def count(self) -> int:
        return len(self._apps)
