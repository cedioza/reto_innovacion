"""Handoff API router.

Endpoint público (sin auth) que resuelve un `handoff_token` opaco contra la
solicitud consentida y devuelve un resumen sanitizado para la página de la
aseguradora simulada. Delgado: no toca repositories ni models, solo delega en
`consent_service`.
"""

from fastapi import APIRouter, HTTPException

from app.schemas.handoff import HandoffSummary
from app.services.consent import consent_service

router = APIRouter(prefix="/handoff", tags=["handoff"])


def _summary_from(application) -> HandoffSummary:
    quote = application.quote
    recommendation = application.recommendation
    state = application.state
    state_value = state.value if hasattr(state, "value") else str(state)

    return HandoffSummary(
        product_id=application.product_id,
        product_name=recommendation.product_name,
        insurer_name=application.insurer_name,
        monthly_premium=quote.monthly_premium,
        annual_premium=quote.annual_premium,
        currency=quote.currency,
        coverage_details=quote.coverage_details,
        exclusions=quote.exclusions,
        state=state_value,
        consent_timestamp=application.consent_timestamp,
    )


@router.get("/{token}", response_model=HandoffSummary)
async def get_handoff(token: str):
    application = consent_service.get_application_by_token(token)
    if application is None:
        raise HTTPException(status_code=404, detail="Handoff not found")

    return _summary_from(application)


@router.post("/{token}/finalize", response_model=HandoffSummary)
async def finalize_handoff(token: str):
    try:
        application = consent_service.finalize_by_token(token)
    except ValueError:
        raise HTTPException(status_code=404, detail="Handoff not found")

    return _summary_from(application)
