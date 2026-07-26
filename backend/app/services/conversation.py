"""Conversation orchestration service.

Manages the state machine and orchestrates the end-to-end flow:
  collecting_profile → recommendation_ready → quote_ready →
  awaiting_consent → ready_for_payment
"""

from __future__ import annotations

import re
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
from app.services.catalog import CatalogService
from app.services.consent import consent_service
from app.repositories.conversations import ConversationRepository

_EMAIL_RE = re.compile(r"^\S+@\S+\.\S+$")


class ConversationService:
    """Orchestrates the insurance conversation flow."""

    def __init__(self) -> None:
        self._propensity = PropensityService()
        self._quote = QuoteService()
        self._affiliates = AffiliateService()
        self._catalog = CatalogService()
        self._consent = consent_service
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
                    has_children=affiliate.has_children,
                    has_vehicle=affiliate.has_vehicle,
                    has_credit=affiliate.has_credit,
                    source="base",
                    gender=affiliate.gender,
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
        product_id = propensity_result["product_id"]
        product = self._catalog.get_product(product_id)
        product_name = product.name if product else product_id
        recommendation = Recommendation(
            product_id=product_id,
            product_name=product_name,
            reasons=propensity_result["reasons"],
        )

        # Calculate quote
        quote_data = self._quote.calculate_quote(profile, product_id=product_id)
        quote = QuoteDetail(
            base_amount=quote_data["base_amount"],
            adjustments=quote_data["adjustments"],
            monthly_premium=quote_data["monthly_premium"],
            annual_premium=quote_data["annual_premium"],
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
                    f"Basado en tu perfil, te recomendamos **{product_name}**. "
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
        session.messages.append(
            Message(
                role="assistant",
                type="consent",
                content=(
                    "📝 Consentimiento: confirma para dejar tu solicitud lista"
                ),
                payload={
                    "product_id": session.recommendation.product_id,
                    "product_name": session.recommendation.product_name,
                    "monthly_premium": session.quote.monthly_premium,
                    "annual_premium": session.quote.annual_premium,
                    "currency": session.quote.currency,
                    "coverage_details": session.quote.coverage_details,
                },
            )
        )
        session.next_action = "Dá tu consentimiento para generar la solicitud"
        self._repo.save(session.session_id, session)
        return session

    # -- consent -------------------------------------------------------------

    def submit_consent(
        self,
        session_id: str,
        consent_given: bool,
        email: str | None = None,
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

        if email and not _EMAIL_RE.match(email):
            raise ValueError("Email inválido")

        application = self._consent.capture(
            session_id=session_id,
            product_id=session.recommendation.product_id,
            profile=session.profile,
            recommendation=session.recommendation,
            quote=session.quote,
            email=email,
        )

        session.state = ConversationState.READY_FOR_PAYMENT

        if email:
            success_text = (
                "¡Listo! Tu solicitud va en camino: revisa tu correo para "
                f"finalizar con {application.insurer_name} 🎉"
            )
            session.next_action = "Revisa tu correo para finalizar con la aseguradora"
        else:
            success_text = (
                "¡Listo! Tu solicitud quedó registrada y lista para pago 🎉"
            )
            session.next_action = (
                "Tu solicitud quedó lista para pago con la aseguradora"
            )

        session.messages.append(
            Message(role="assistant", content=success_text)
        )
        session.messages.append(
            Message(
                role="assistant",
                type="application",
                content="🎉 Solicitud lista — pendiente de pago",
                payload={
                    "product_name": session.recommendation.product_name,
                    "monthly_premium": session.quote.monthly_premium,
                    "currency": session.quote.currency,
                    "insurer_name": application.insurer_name,
                    "email": application.email,
                    "consent_timestamp": application.consent_timestamp,
                },
            )
        )

        self._repo.save(session.session_id, session)
        return application

    # -- adjustments / comparison --------------------------------------------

    def apply_adjustments(
        self, session_id: str, adjustments: list[str]
    ) -> ConversationResponse:
        session = self._repo.find(session_id)
        if not session:
            raise ValueError("Session not found")

        if session.profile is None or session.quote is None:
            raise ValueError("Cannot adjust before a quote exists")

        product_id = (
            session.recommendation.product_id
            if session.recommendation
            else "hogar-estandar"
        )
        product = self._catalog.get_product(product_id)
        available_codes = {adj.code for adj in (product.adjustments if product else [])}
        for code in adjustments:
            if code not in available_codes:
                raise ValueError(f"Unknown adjustment code: {code}")

        adjustments_a = [a["code"] for a in (session.quote.adjustments or [])]
        result = self._quote.compare(
            session.profile, product_id, adjustments_a, adjustments
        )

        session.quote = QuoteDetail(
            **{
                k: v
                for k, v in result["propuesta"].items()
                if k in QuoteDetail.model_fields
            }
        )

        payload = result
        content = (
            f"⚖️ Comparación: diferencia ${result['diferencia_mensual']:,.0f} COP/mes"
        )

        comparison_message = next(
            (
                msg
                for msg in reversed(session.messages)
                if msg.type == "comparison"
            ),
            None,
        )
        if comparison_message is not None:
            comparison_message.payload = payload
            comparison_message.content = content
        else:
            session.messages.append(
                Message(
                    role="assistant",
                    type="comparison",
                    content=content,
                    payload=payload,
                )
            )

        self._repo.save(session.session_id, session)
        return session


# Shared module-level instance so the REST API and the channel webhooks
# (WhatsApp, Telegram) orchestrate the same in-memory sessions.
conversation_service = ConversationService()
