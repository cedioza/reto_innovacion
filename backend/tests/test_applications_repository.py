"""Tests for in-memory application repository."""

from app.repositories.applications import ApplicationRepository
from app.schemas.conversation import (
    ProfileData,
    Recommendation,
    QuoteDetail,
    ConsentedApplication,
    ConversationState,
)


class TestApplicationRepository:
    def setup_method(self) -> None:
        self.repo = ApplicationRepository()

    def _app(self, sid: str = "app-1") -> ConsentedApplication:
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
