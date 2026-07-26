"""Panel API router (disparador proactivo).

Thin layer: delegates to ProactiveService and returns the response
validated by CohortsResponse. No business logic here.
"""

from fastapi import APIRouter

from app.schemas.panel import CohortsResponse
from app.services.proactive import ProactiveService

router = APIRouter(prefix="/panel", tags=["panel"])


@router.get("/cohortes", response_model=CohortsResponse)
async def get_cohortes():
    return ProactiveService().list_cohorts()
