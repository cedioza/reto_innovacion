"""Tests for consent service — TDD RED phase."""

import pytest

from app.services.consent import ConsentService
from app.schemas.conversation import (
    ProfileData,
    Recommendation,
    QuoteDetail,
    ConversationState,
)


class TestConsentService:
    def setup_method(self) -> None:
        self.service = ConsentService()
        self.profile = ProfileData(
            age_range="26-40",
            property_type="house",
            zone="urban",
            stratum=3,
        )
        self.recommendation = Recommendation(
            product_id="hogar-estandar",
            product_name="Hogar Estándar",
            reasons=[{"code": "homeowner", "label": "Propietario", "evidence": "Casa"}],
        )
        self.quote = QuoteDetail(
            base_amount=45000.0,
            monthly_premium=3750.0,
            coverage_details=["Incendio", "Hurto"],
            exclusions=["Guerra"],
        )

    def test_capture_creates_application(self) -> None:
        app = self.service.capture(
            session_id="sess-1",
            product_id="hogar-estandar",
            profile=self.profile,
            recommendation=self.recommendation,
            quote=self.quote,
        )
        assert app.session_id == "sess-1"
        assert app.state == ConversationState.READY_FOR_PAYMENT
        assert app.consent_timestamp is not None

    def test_application_has_all_data(self) -> None:
        app = self.service.capture(
            session_id="sess-2",
            product_id="hogar-estandar",
            profile=self.profile,
            recommendation=self.recommendation,
            quote=self.quote,
        )
        assert app.product_id == "hogar-estandar"
        assert app.profile.age_range == "26-40"
        assert app.recommendation.product_name == "Hogar Estándar"
        assert app.quote.monthly_premium == 3750.0

    def test_get_application_after_capture(self) -> None:
        self.service.capture(
            session_id="sess-3",
            product_id="hogar-estandar",
            profile=self.profile,
            recommendation=self.recommendation,
            quote=self.quote,
        )
        app = self.service.get_application("sess-3")
        assert app is not None
        assert app.session_id == "sess-3"

    def test_get_nonexistent_returns_none(self) -> None:
        app = self.service.get_application("no-existe")
        assert app is None
