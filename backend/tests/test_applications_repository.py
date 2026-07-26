"""Tests for the DB-backed application repository.

Corren contra SQLite in-memory por velocidad/CI; el shape es compatible con
Postgres (criterio C3: mismo repo, mismo contrato de tipos, distinto engine
subyacente).
"""

from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from app.repositories.applications import ApplicationRepository
from app.repositories.db import init_db
from app.schemas.conversation import (
    ProfileData,
    Recommendation,
    QuoteDetail,
    ConsentedApplication,
    ConversationState,
)


class TestApplicationRepository:
    def setup_method(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_db(self.engine)
        self.repo = ApplicationRepository(engine=self.engine)

    def _app(self, sid: str = "app-1", handoff_token: str | None = None) -> ConsentedApplication:
        return ConsentedApplication(
            session_id=sid,
            product_id="hogar-estandar",
            profile=ProfileData(age_range="26-40", stratum=3),
            recommendation=Recommendation(
                product_id="hogar-estandar",
                product_name="Hogar Estándar",
                reasons=[],
            ),
            quote=QuoteDetail(
                base_amount=45000.0,
                monthly_premium=3750.0,
                coverage_details=[],
                exclusions=[],
            ),
            consent_timestamp="2026-07-24T00:00:00",
            handoff_token=handoff_token,
        )

    def test_save_and_find(self) -> None:
        app = self._app()
        self.repo.save("app-1", "abc123", app)
        found = self.repo.find("app-1")
        assert found is not None
        assert found.session_id == "app-1"
        assert found.state == ConversationState.READY_FOR_PAYMENT

    def test_find_nonexistent_returns_none(self) -> None:
        assert self.repo.find("no-existe") is None

    def test_get_evidence_hash(self) -> None:
        self.repo.save("app-1", "evidence-hash-xyz", self._app())
        assert self.repo.get_evidence_hash("app-1") == "evidence-hash-xyz"

    def test_count(self) -> None:
        assert self.repo.count() == 0
        self.repo.save("a", "h1", self._app("a"))
        self.repo.save("b", "h2", self._app("b"))
        assert self.repo.count() == 2

    def test_find_by_token(self) -> None:
        app = self._app("app-1", handoff_token="tok-abc")
        self.repo.save("app-1", "abc123", app)

        found = self.repo.find_by_token("tok-abc")
        assert found is not None
        assert found.session_id == "app-1"

        assert self.repo.find_by_token("nope") is None

    def test_survives_repository_recreation(self) -> None:
        app = self._app("app-persist", handoff_token="tok-persist")
        self.repo.save("app-persist", "evidence-hash-persist", app)

        second_repo = ApplicationRepository(engine=self.engine)

        found = second_repo.find("app-persist")
        assert found is not None
        assert found.session_id == "app-persist"

        assert second_repo.get_evidence_hash("app-persist") == "evidence-hash-persist"

        found_by_token = second_repo.find_by_token("tok-persist")
        assert found_by_token is not None
        assert found_by_token.session_id == "app-persist"
