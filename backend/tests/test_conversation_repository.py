"""Tests for in-memory conversation repository."""

from app.repositories.conversations import ConversationRepository
from app.schemas.conversation import (
    ConversationResponse,
    ConversationState,
    Message,
)


class TestConversationRepository:
    def setup_method(self) -> None:
        self.repo = ConversationRepository()

    def _session(self, sid: str = "sess-1") -> ConversationResponse:
        return ConversationResponse(
            session_id=sid,
            state=ConversationState.COLLECTING_PROFILE,
            messages=[Message(role="user", content="Hola")],
            next_action="Tell us about your home",
        )

    def test_save_and_find(self) -> None:
        s = self._session()
        self.repo.save(s)
        found = self.repo.find("sess-1")
        assert found is not None
        assert found.session_id == "sess-1"
        assert found.state == ConversationState.COLLECTING_PROFILE

    def test_find_nonexistent_returns_none(self) -> None:
        found = self.repo.find("no-existe")
        assert found is None

    def test_save_overwrites_existing(self) -> None:
        s1 = self._session("sess-1")
        self.repo.save(s1)
        s2 = self._session("sess-1")
        s2.state = ConversationState.QUOTE_READY
        self.repo.save(s2)
        found = self.repo.find("sess-1")
        assert found is not None
        assert found.state == ConversationState.QUOTE_READY

    def test_delete_removes_session(self) -> None:
        self.repo.save(self._session())
        self.repo.delete("sess-1")
        assert self.repo.find("sess-1") is None

    def test_count(self) -> None:
        assert self.repo.count() == 0
        self.repo.save(self._session("a"))
        self.repo.save(self._session("b"))
        assert self.repo.count() == 2
