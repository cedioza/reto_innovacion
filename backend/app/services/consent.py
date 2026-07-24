"""Consent and application service.

Captures explicit consent with timestamp, evidence hash,
and creates the application in ready_for_payment state.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.schemas.conversation import (
    ProfileData,
    Recommendation,
    QuoteDetail,
    ConsentedApplication,
    ConversationState,
)
from app.repositories.applications import ApplicationRepository


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
    ) -> ConsentedApplication:
        """Capture consent and create an application.

        Generates an evidence hash from the recommendation and quote
        to provide a tamper-evident record of what was consented to.
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

        application = ConsentedApplication(
            session_id=session_id,
            product_id=product_id,
            profile=profile,
            recommendation=recommendation,
            quote=quote,
            consent_timestamp=timestamp,
            state=ConversationState.READY_FOR_PAYMENT,
        )

        self._repo.save(session_id, evidence_hash, application)
        return application

    def get_application(
        self, session_id: str
    ) -> ConsentedApplication | None:
        return self._repo.find(session_id)
