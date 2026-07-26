"""Tests for the DB-backed conversation repository.

Corren contra SQLite in-memory por velocidad/CI; el shape es compatible con
Postgres (criterio C3: mismo repo, mismo contrato de tipos, distinto engine
subyacente).
"""

from datetime import datetime, timezone

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.models.conversation import ConversationRecord
from app.repositories.conversations import ConversationRepository
from app.repositories.db import init_db
from app.schemas.conversation import (
    ConversationResponse,
    ConversationState,
    Message,
)


class TestConversationRepository:
    def setup_method(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_db(self.engine)
        self.repo = ConversationRepository(engine=self.engine)

    def _session(self, sid: str = "sess-1") -> ConversationResponse:
        return ConversationResponse(
            session_id=sid,
            state=ConversationState.COLLECTING_PROFILE,
            messages=[Message(role="user", content="Hola")],
            next_action="Tell us about your home",
        )

    def test_save_and_find(self) -> None:
        s = self._session()
        self.repo.save(s.session_id, s)
        found = self.repo.find("sess-1")
        assert found is not None
        assert found.session_id == "sess-1"
        assert found.state == ConversationState.COLLECTING_PROFILE

    def test_find_nonexistent_returns_none(self) -> None:
        found = self.repo.find("no-existe")
        assert found is None

    def test_save_overwrites_existing(self) -> None:
        s1 = self._session("sess-1")
        self.repo.save(s1.session_id, s1)
        s2 = self._session("sess-1")
        s2.state = ConversationState.QUOTE_READY
        self.repo.save(s2.session_id, s2)
        found = self.repo.find("sess-1")
        assert found is not None
        assert found.state == ConversationState.QUOTE_READY

    def test_delete_removes_session(self) -> None:
        s = self._session()
        self.repo.save(s.session_id, s)
        self.repo.delete("sess-1")
        assert self.repo.find("sess-1") is None

    def test_count(self) -> None:
        assert self.repo.count() == 0
        a = self._session("a")
        b = self._session("b")
        self.repo.save(a.session_id, a)
        self.repo.save(b.session_id, b)
        assert self.repo.count() == 2

    def test_timestamp_survives_roundtrip(self) -> None:
        s = ConversationResponse(
            session_id="sess-ts",
            state=ConversationState.COLLECTING_PROFILE,
            messages=[
                Message(
                    role="user",
                    content="Hola",
                    timestamp="2026-07-25T10:00:00+00:00",
                )
            ],
            next_action="Tell us about your home",
        )
        self.repo.save(s.session_id, s)

        second_repo = ConversationRepository(engine=self.engine)
        found = second_repo.find("sess-ts")

        assert found is not None
        assert found.messages[0].timestamp == "2026-07-25T10:00:00+00:00"

    def test_survives_repository_recreation(self) -> None:
        s = ConversationResponse(
            session_id="sess-persist",
            state=ConversationState.COLLECTING_PROFILE,
            messages=[
                Message(role="user", content="Hola"),
                Message(role="assistant", content="Cuéntame sobre tu hogar"),
            ],
            next_action="Tell us about your home",
        )
        self.repo.save(s.session_id, s)

        second_repo = ConversationRepository(engine=self.engine)
        found = second_repo.find("sess-persist")

        assert found is not None
        assert found.session_id == "sess-persist"
        assert [m.role for m in found.messages] == [
            m.role for m in s.messages
        ]
        assert [m.content for m in found.messages] == [
            m.content for m in s.messages
        ]

    # -- list_all (plan G4, Fase 2) -------------------------------------------

    def test_list_all_returns_sessions_ordered_by_updated_at_desc(self) -> None:
        a = self._session("a")
        b = self._session("b")
        c = self._session("c")
        self.repo.save(a.session_id, a)
        self.repo.save(b.session_id, b)
        self.repo.save(c.session_id, c)

        # Se fuerza un orden de `updated_at` explícito e independiente de la
        # resolución del reloj/orden de inserción, para que el assert sobre
        # el orden descendente sea determinista.
        with Session(self.engine) as db_session:
            rec_a = db_session.get(ConversationRecord, "a")
            rec_b = db_session.get(ConversationRecord, "b")
            rec_c = db_session.get(ConversationRecord, "c")
            rec_a.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
            rec_b.updated_at = datetime(2026, 1, 3, tzinfo=timezone.utc)
            rec_c.updated_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
            db_session.add_all([rec_a, rec_b, rec_c])
            db_session.commit()

        items = self.repo.list_all()
        session_ids = [item["session"].session_id for item in items]
        assert session_ids == ["b", "c", "a"]

    def test_list_all_item_has_expected_shape(self) -> None:
        s = self._session("shape-1")
        self.repo.save(s.session_id, s)

        items = self.repo.list_all()
        item = next(i for i in items if i["session"].session_id == "shape-1")

        assert isinstance(item["session"], ConversationResponse)
        assert item["session"].state == ConversationState.COLLECTING_PROFILE
        assert item["canal"] is None
        assert item["created_at"] is not None
        assert item["updated_at"] is not None

    def test_list_all_skips_corrupt_rows(self) -> None:
        good = self._session("good-1")
        self.repo.save(good.session_id, good)

        with Session(self.engine) as db_session:
            corrupt = ConversationRecord(
                session_id="corrupt-1",
                canal=None,
                estado="collecting_profile",
                data={"garbage": True},
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db_session.add(corrupt)
            db_session.commit()

        items = self.repo.list_all()
        session_ids = [item["session"].session_id for item in items]
        assert "good-1" in session_ids
        assert "corrupt-1" not in session_ids
