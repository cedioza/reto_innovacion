"""Conversation orchestration service.

Manages the state machine and orchestrates the end-to-end flow:
  collecting_profile → recommendation_ready → quote_ready →
  awaiting_consent → ready_for_payment
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.schemas.conversation import (
    ConversationState,
    ConversationResponse,
    ConversationCreate,
    ProfileData,
    Recommendation,
    QuoteDetail,
    Message,
    ConsentedApplication,
)
from app.services.propensity import PropensityService
from app.services.quote import QuoteService
from app.services.affiliate import AffiliateService
from app.services.consent import ConsentService
from app.repositories.conversations import ConversationRepository


class ConversationService:
    """Orchestrates the insurance conversation flow."""

    def __init__(self) -> None:
        self._propensity = PropensityService()
        self._quote = QuoteService()
        self._affiliates = AffiliateService()
        self._consent = ConsentService()
        self._repo = ConversationRepository()

    # -- public API -----------------------------------------------------------

    def create(
        self, body: ConversationCreate
    ) -> ConversationResponse:
        session_id = str(uuid.uuid4())
        profile: ProfileData | None = None

        # Try affiliate lookup
        if body.document_number:
            affiliate = self._affiliates.lookup(body.document_number)
            if affiliate:
                profile = ProfileData(
                    age_range=affiliate.age_range,
                    stratum=affiliate.stratum,
                    property_type=affiliate.property_type,
                    zone=affiliate.zone,
                )

        session = ConversationResponse(
            session_id=session_id,
            state=ConversationState.COLLECTING_PROFILE,
            messages=[body.message] if body.message else [],
            profile=profile,
            next_action="Contanos sobre tu hogar para recomendarte el seguro ideal",
        )
        self._repo.save(session.session_id, session)
        return session

    def get(self, session_id: str) -> ConversationResponse | None:
        return self._repo.find(session_id)

    # -- profile update ------------------------------------------------------

    def update_profile(
        self, session_id: str, profile: ProfileData
    ) -> ConversationResponse:
        session = self._repo.find(session_id)
        if not session:
            raise ValueError("Session not found")

        # If we already have a recommendation, don't re-profile
        if session.state not in (
            ConversationState.COLLECTING_PROFILE,
            ConversationState.RECOMMENDATION_READY,
        ):
            raise ValueError(
                f"Cannot update profile in state {session.state}"
            )

        # Evaluate propensity
        propensity_result = self._propensity.evaluate(profile)
        recommendation = Recommendation(
            product_id=propensity_result["product_id"],
            product_name="Hogar Estándar",
            reasons=propensity_result["reasons"],
        )

        # Calculate quote
        quote_data = self._quote.calculate_quote(profile)
        quote = QuoteDetail(
            base_amount=quote_data["base_amount"],
            adjustments=quote_data["adjustments"],
            monthly_premium=quote_data["monthly_premium"],
            coverage_details=quote_data["coverage_details"],
            exclusions=quote_data["exclusions"],
        )

        session.state = ConversationState.QUOTE_READY
        session.profile = profile
        session.recommendation = recommendation
        session.quote = quote
        session.messages.append(
            Message(
                role="assistant",
                content=(
                    "Basado en tu perfil, te recomendamos **Hogar Estándar**. "
                    f"Tu prima mensual estimada es ${quote.monthly_premium:,.0f} COP. "
                    "¿Querés ver los detalles de cobertura o ajustar algo?"
                ),
            )
        )
        session.next_action = "Revisá la cotización y coberturas, podés ajustar las opciones"
        self._repo.save(session.session_id, session)
        return session

    # -- accept quote --------------------------------------------------------

    def accept_quote(self, session_id: str) -> ConversationResponse:
        session = self._repo.find(session_id)
        if not session:
            raise ValueError("Session not found")
        if session.state != ConversationState.QUOTE_READY:
            raise ValueError(
                f"Cannot accept quote in state {session.state}"
            )

        session.state = ConversationState.AWAITING_CONSENT
        session.messages.append(
            Message(
                role="assistant",
                content=(
                    "Para continuar necesitamos tu consentimiento. "
                    "¿Confirmás que entendés las coberturas y exclusiones "
                    "y querés dejar tu solicitud lista para pago?"
                ),
            )
        )
        session.next_action = "Dá tu consentimiento para generar la solicitud"
        self._repo.save(session.session_id, session)
        return session

    # -- consent -------------------------------------------------------------

    def submit_consent(
        self, session_id: str, consent_given: bool
    ) -> ConsentedApplication:
        session = self._repo.find(session_id)
        if not session:
            raise ValueError("Session not found")
        if session.state != ConversationState.AWAITING_CONSENT:
            raise ValueError(
                f"Cannot submit consent in state {session.state}"
            )
        if not consent_given:
            raise ValueError("Consent must be given to proceed")

        if not session.profile or not session.recommendation or not session.quote:
            raise ValueError("Missing profile, recommendation, or quote")

        application = self._consent.capture(
            session_id=session_id,
            product_id=session.recommendation.product_id,
            profile=session.profile,
            recommendation=session.recommendation,
            quote=session.quote,
        )

        session.state = ConversationState.READY_FOR_PAYMENT
        self._repo.save(session.session_id, session)
        return application


# Shared module-level instance so the REST API and the channel webhooks
# (WhatsApp, Telegram) orchestrate the same in-memory sessions.
conversation_service = ConversationService()
