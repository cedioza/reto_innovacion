"""Endpoints de health check de integraciones con terceros."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.helpers.responses import error_response, success_response
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


@router.post("/{service}")
def run_integration_check(service: str) -> JSONResponse:
    integration = INTEGRATIONS.get(service)
    if integration is None:
        return JSONResponse(
            status_code=404,
            content=error_response(message=f"integración desconocida: {service}"),
        )

    if integration.check is None:
        return JSONResponse(
            status_code=503,
            content=error_response(
                message=f"check no implementado aún para: {service}"
            ),
        )

    result = integration.check()

    if result.ok:
        return JSONResponse(status_code=200, content=success_response(data=result.model_dump()))

    return JSONResponse(
        status_code=503,
        content=error_response(
            message=result.detail or f"check falló para: {service}",
            details=result.model_dump(),
        ),
    )
