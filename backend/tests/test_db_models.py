"""Tests for the SQLModel persistence layer (engine/session + tables).

SQLite in-memory por velocidad/CI; el shape SQL es compatible con Postgres
(JSON->JSONB variant). Estos tests fallan por ImportError hasta que se
implementen `app.repositories.db`, `app.models.conversation`,
`app.models.application` y `app.models.channel` (fase siguiente).
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine, select

from app.repositories.db import get_engine, get_session, init_db
from app.models.conversation import ConversationRecord
from app.models.application import ApplicationRecord
from app.models.channel import ChannelSessionRecord, ProcessedEventRecord


def _make_sqlite_engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


class TestEngineAndSession:
    def test_get_engine_returns_same_instance(self) -> None:
        engine_a = get_engine()
        engine_b = get_engine()
        assert engine_a is engine_b

    def test_init_db_creates_all_tables(self) -> None:
        engine = _make_sqlite_engine()
        init_db(engine)
        tables = set(inspect(engine).get_table_names())
        assert {
            "conversaciones",
            "solicitudes",
            "sesiones_canal",
            "eventos_procesados",
        }.issubset(tables)

    def test_get_session_is_usable_context_manager(self) -> None:
        engine = _make_sqlite_engine()
        init_db(engine)
        with get_session(engine) as session:
            record = ConversationRecord(
                session_id="sess-ctx",
                canal=None,
                estado="collecting_profile",
                data={},
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(record)
            session.commit()

        with get_session(engine) as session:
            found = session.get(ConversationRecord, "sess-ctx")
            assert found is not None
            assert found.session_id == "sess-ctx"


class TestConversationRecord:
    def setup_method(self) -> None:
        self.engine = _make_sqlite_engine()
        init_db(self.engine)

    def test_roundtrip_with_nested_data(self) -> None:
        now = datetime.now(timezone.utc)
        nested_data = {"messages": [{"role": "user", "content": "hola"}]}
        with get_session(self.engine) as session:
            record = ConversationRecord(
                session_id="sess-1",
                canal="whatsapp",
                estado="collecting_profile",
                data=nested_data,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.commit()

        with get_session(self.engine) as session:
            found = session.get(ConversationRecord, "sess-1")
            assert found is not None
            assert found.canal == "whatsapp"
            assert found.estado == "collecting_profile"
            assert found.data == nested_data


class TestApplicationRecord:
    def setup_method(self) -> None:
        self.engine = _make_sqlite_engine()
        init_db(self.engine)

    def test_roundtrip_query_by_handoff_token(self) -> None:
        now = datetime.now(timezone.utc)
        with get_session(self.engine) as session:
            record = ApplicationRecord(
                session_id="sess-app-1",
                evidence_hash="abc123",
                handoff_token="tok-xyz",
                consent_timestamp="2026-07-25T00:00:00Z",
                data={"producto": "hogar"},
                created_at=now,
            )
            session.add(record)
            session.commit()

        with get_session(self.engine) as session:
            statement = select(ApplicationRecord).where(
                ApplicationRecord.handoff_token == "tok-xyz"
            )
            found = session.exec(statement).first()
            assert found is not None
            assert found.session_id == "sess-app-1"
            assert found.evidence_hash == "abc123"
            assert found.data == {"producto": "hogar"}


class TestChannelSessionRecord:
    def setup_method(self) -> None:
        self.engine = _make_sqlite_engine()
        init_db(self.engine)

    def test_roundtrip_composite_pk(self) -> None:
        now = datetime.now(timezone.utc)
        with get_session(self.engine) as session:
            record = ChannelSessionRecord(
                channel="whatsapp",
                user_ref="573001112233",
                session_id="sess-channel-1",
                updated_at=now,
            )
            session.add(record)
            session.commit()

        with get_session(self.engine) as session:
            found = session.get(
                ChannelSessionRecord, ("whatsapp", "573001112233")
            )
            assert found is not None
            assert found.session_id == "sess-channel-1"


class TestProcessedEventRecord:
    def setup_method(self) -> None:
        self.engine = _make_sqlite_engine()
        init_db(self.engine)

    def test_duplicate_event_id_raises_integrity_error(self) -> None:
        now = datetime.now(timezone.utc)
        with get_session(self.engine) as session:
            session.add(ProcessedEventRecord(event_id="evt-1", created_at=now))
            session.commit()

        with get_session(self.engine) as session:
            session.add(ProcessedEventRecord(event_id="evt-1", created_at=now))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

        with get_session(self.engine) as session:
            found = session.get(ProcessedEventRecord, "evt-1")
            assert found is not None
