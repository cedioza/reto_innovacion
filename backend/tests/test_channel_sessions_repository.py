"""Tests for the DB-backed channel session / event-dedup repository.

Corren contra SQLite in-memory por velocidad/CI; el shape es compatible con
Postgres (criterio C3: mismo repo, mismo contrato de tipos, distinto engine
subyacente).
"""

from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from app.repositories.channel_sessions import ChannelSessionRepository
from app.repositories.db import init_db


class TestChannelSessionRepository:
    def setup_method(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_db(self.engine)
        self.repo = ChannelSessionRepository(engine=self.engine)

    def test_save_and_find(self) -> None:
        self.repo.save("whatsapp", "user-1", "sess-1")
        found = self.repo.find("whatsapp", "user-1")
        assert found == "sess-1"
        assert self.repo.find("whatsapp", "desconocido") is None

    def test_save_upserts_session_id(self) -> None:
        self.repo.save("whatsapp", "user-1", "sess-1")
        self.repo.save("whatsapp", "user-1", "sess-2")
        found = self.repo.find("whatsapp", "user-1")
        assert found == "sess-2"

    def test_channels_are_isolated(self) -> None:
        self.repo.save("whatsapp", "user-1", "sess-whatsapp")
        self.repo.save("telegram", "user-1", "sess-telegram")
        assert self.repo.find("whatsapp", "user-1") == "sess-whatsapp"
        assert self.repo.find("telegram", "user-1") == "sess-telegram"

    def test_survives_repository_recreation(self) -> None:
        self.repo.save("whatsapp", "user-1", "sess-persist")
        self.repo.mark_event_processed("event-1")

        second_repo = ChannelSessionRepository(engine=self.engine)

        assert second_repo.find("whatsapp", "user-1") == "sess-persist"
        assert second_repo.is_event_processed("event-1") is True

    def test_mark_event_processed_first_time_true(self) -> None:
        result = self.repo.mark_event_processed("event-1")
        assert result is True
        assert self.repo.is_event_processed("event-1") is True

    def test_mark_event_processed_duplicate_false(self) -> None:
        first = self.repo.mark_event_processed("event-1")
        second = self.repo.mark_event_processed("event-1")
        assert first is True
        assert second is False

    def test_is_event_processed_unknown_false(self) -> None:
        assert self.repo.is_event_processed("no-existe") is False
