from pydantic import ValidationError
import pytest



from app.schemas.conversation import (
    ConsentRequest,
    ConsentedApplication,
    ConversationCreate,
    ConversationResponse,
    ConversationState,
    ProfileData,
    QuoteDetail,
    Recommendation,
)
from app.schemas.product import ProductResponse


class TestConversationCreate:
    def test_optional_message(self):
        c = ConversationCreate()
        assert c.message is None
        assert c.document_number is None

    def test_without_document_number(self):
        data = {"message": {"role": "user", "content": "hello"}}
        c = ConversationCreate(**data)
        assert c.message.content == "hello"
        assert c.document_number is None

    def test_with_document_number(self):
        data = {
            "message": {"role": "user", "content": "hello"},
            "document_number": "12345678",
        }
        c = ConversationCreate(**data)
        assert c.document_number == "12345678"


class TestConversationResponse:
    def test_all_fields_defaults(self):
        resp = ConversationResponse(
            session_id="abc-123",
            state=ConversationState.COLLECTING_PROFILE,
            next_action="tell us about your home",
        )
        assert resp.session_id == "abc-123"
        assert resp.state == ConversationState.COLLECTING_PROFILE
        assert resp.next_action == "tell us about your home"
        assert resp.messages == []
        assert resp.profile is None
        assert resp.recommendation is None
        assert resp.quote is None
        assert resp.application is None


class TestConversationState:
    def test_has_six_states(self):
        assert len(ConversationState) == 6

    def test_enum_values(self):
        assert ConversationState.COLLECTING_PROFILE.value == "collecting_profile"
        assert ConversationState.RECOMMENDATION_READY.value == "recommendation_ready"
        assert ConversationState.QUOTE_READY.value == "quote_ready"
        assert ConversationState.AWAITING_CONSENT.value == "awaiting_consent"
        assert ConversationState.READY_FOR_PAYMENT.value == "ready_for_payment"
        assert ConversationState.FINALIZED_DEMO.value == "finalizada_demo"


class TestProductResponse:
    def test_required_fields(self):
        p = ProductResponse(
            id="hogar-estandar",
            name="Hogar Estándar",
            description="Seguro de hogar",
            coverages=[],
            exclusions=[],
            adjustments=[],
            base_price=100.0,
        )
        assert p.id == "hogar-estandar"
        assert p.name == "Hogar Estándar"
        assert p.coverages == []
        assert p.exclusions == []
        assert p.base_price == 100.0
        assert p.currency == "COP"


class TestQuoteDetail:
    def test_all_fields(self):
        q = QuoteDetail(
            base_amount=50000.0,
            monthly_premium=57500.0,
            coverage_details=["Incendio", "Terremoto"],
            exclusions=["Guerra"],
        )
        assert q.currency == "COP"
        assert q.base_amount == 50000.0
        assert q.monthly_premium == 57500.0
        assert q.coverage_details == ["Incendio", "Terremoto"]
        assert q.exclusions == ["Guerra"]


class TestConsentRequest:
    def test_accepts_consent_given(self):
        c = ConsentRequest(consent_given=True)
        assert c.consent_given is True

    def test_rejects_missing_consent_given(self):
        with pytest.raises(ValidationError):
            ConsentRequest()


class TestConsentedApplication:
    def test_default_state_is_ready_for_payment(self):
        app = ConsentedApplication(
            session_id="sess-1",
            product_id="hogar-estandar",
            profile=ProfileData(),
            recommendation=Recommendation(
                product_id="hogar-estandar",
                product_name="Hogar Estándar",
                reasons=[],
            ),
            quote=QuoteDetail(
                base_amount=0,
                monthly_premium=0,
                coverage_details=[],
                exclusions=[],
            ),
            consent_timestamp="2026-01-01T00:00:00",
        )
        assert app.state == ConversationState.READY_FOR_PAYMENT
