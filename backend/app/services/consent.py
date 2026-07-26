"""Consent and application service.

Captures explicit consent with timestamp, evidence hash,
and creates the application in ready_for_payment state.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from app.core.config import settings
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


def _apunta_a_localhost(url: str) -> bool:
    """True si el hostname de `url` es "localhost" o "127.0.0.1"."""
    return urlparse(url).hostname in ("localhost", "127.0.0.1")


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
            # Guard E7: si el backend está desplegado (hay `BACKEND_PUBLIC_URL`,
            # señal que solo se configura en producción para el webhook de
            # Telegram) pero `FRONTEND_URL` sigue apuntando a localhost, el
            # correo saldría con un botón "Continuar" muerto para el cliente.
            # Se omite el envío y se deja constancia en logs; el cierre
            # (aplicación persistida + handoff_token) no se ve afectado.
            if settings.backend_public_url and _apunta_a_localhost(
                settings.frontend_url
            ):
                logger.error(
                    "backend desplegado (BACKEND_PUBLIC_URL=%s) pero "
                    "FRONTEND_URL=%s apunta a localhost: se omite el envío "
                    "del correo de handoff para session_id=%s (el link "
                    "quedaría inaccesible para el cliente); configura "
                    "FRONTEND_URL con el dominio público real",
                    settings.backend_public_url,
                    settings.frontend_url,
                    session_id,
                )
            else:
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

    def get_application_by_token(
        self, token: str
    ) -> ConsentedApplication | None:
        return self._repo.find_by_token(token)

    def list_applications(self) -> list[ConsentedApplication]:
        """Lista todas las solicitudes (plan G4, Fase 2: vista de clientes).

        Delegación directa al `ApplicationRepository.list_all()` subyacente.
        """
        return self._repo.list_all()

    def finalize_by_token(self, token: str) -> ConsentedApplication:
        """Marca la solicitud como `finalizada_demo` (idempotente).

        Busca la aplicación por `handoff_token` y, si existe, actualiza su
        estado a `ConversationState.FINALIZED_DEMO`, re-persistiendo con el
        mismo `evidence_hash` original (no se recalcula: el hash es evidencia
        de lo consentido, no del estado de la demo).
        """
        application = self._repo.find_by_token(token)
        if application is None:
            raise ValueError("Handoff not found")

        application.state = ConversationState.FINALIZED_DEMO
        evidence_hash = self._repo.get_evidence_hash(application.session_id)
        self._repo.save(application.session_id, evidence_hash, application)

        return application


# Instancia compartida de módulo: el camino REST (`conversation_service`) y el
# camino tool (`agent_tools._cerrar_venta`) deben resolver el mismo
# `handoff_token` contra el mismo `ApplicationRepository` en memoria, mismo
# patrón que `conversation_service`.
consent_service = ConsentService()
