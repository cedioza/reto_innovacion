"""Consent and application service.

Captures explicit consent with timestamp, evidence hash,
and creates the application in ready_for_payment state.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

from app.schemas.conversation import (
    ProfileData,
    Recommendation,
    QuoteDetail,
    ConsentedApplication,
    ConversationState,
)
from app.repositories.applications import ApplicationRepository
from app.services import handoff
from app.services.integrations import resend_client

logger = logging.getLogger(__name__)


class ConsentService:
    def __init__(self) -> None:
        self._repo = ApplicationRepository()

    def capture(
        self,
        session_id: str,
        product_id: str,
        profile: ProfileData,
        recommendation: Recommendation,
        quote: QuoteDetail,
        email: str | None = None,
    ) -> ConsentedApplication:
        """Capture consent and create an application.

        Generates an evidence hash from the recommendation and quote
        to provide a tamper-evident record of what was consented to.

        Siempre genera el token de handoff y la aseguradora simulada
        asociada al producto. Si hay email, dispara el correo de
        comprobante (best-effort: un fallo o una excepción de Resend
        nunca rompen el cierre, solo se loguea).
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        evidence_payload = {
            "session_id": session_id,
            "product_id": product_id,
            "recommendation": recommendation.model_dump(),
            "quote": quote.model_dump(),
            "profile": profile.model_dump(),
            "consent_timestamp": timestamp,
        }
        evidence_hash = hashlib.sha256(
            json.dumps(evidence_payload, sort_keys=True).encode()
        ).hexdigest()[:16]

        handoff_token = handoff.new_token()
        insurer_name = handoff.insurer_for(product_id)

        application = ConsentedApplication(
            session_id=session_id,
            product_id=product_id,
            profile=profile,
            recommendation=recommendation,
            quote=quote,
            consent_timestamp=timestamp,
            state=ConversationState.READY_FOR_PAYMENT,
            email=email,
            handoff_token=handoff_token,
            insurer_name=insurer_name,
        )

        self._repo.save(session_id, evidence_hash, application)

        if email:
            try:
                subject, html = handoff.build_handoff_email(
                    application, handoff_token
                )
                result = resend_client.send_email(email, subject, html)
                if not result.get("ok", False):
                    logger.error(
                        "fallo al enviar correo de handoff para session_id=%s",
                        session_id,
                    )
            except Exception:  # noqa: BLE001 - best-effort, nunca rompe el cierre
                logger.error(
                    "excepcion al enviar correo de handoff para session_id=%s",
                    session_id,
                )
        else:
            logger.info("sin correo de destino, no se envía handoff")

        return application

    def get_application(
        self, session_id: str
    ) -> ConsentedApplication | None:
        return self._repo.find(session_id)
