"""Endpoints de health check de integraciones con terceros."""

from fastapi import APIRouter

from app.helpers.responses import success_response
from app.schemas.health import IntegrationStatus
from app.services.integrations import INTEGRATIONS, is_configured

router = APIRouter(prefix="/health/integrations", tags=["health"])


@router.get("")
def list_integrations_status() -> dict:
    data = [
        IntegrationStatus(
            service=integration.name,
            configured=is_configured(integration),
            required_env=integration.required_env,
        ).model_dump()
        for integration in INTEGRATIONS.values()
    ]
    return success_response(data=data)
