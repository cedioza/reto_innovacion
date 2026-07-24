"""DTOs de request/response para los endpoints de health de integraciones."""

from pydantic import BaseModel


class IntegrationStatus(BaseModel):
    """Estado de configuración de una integración (sin llamar al tercero)."""

    service: str
    configured: bool
    required_env: list[str]


class IntegrationCheckResult(BaseModel):
    """Resultado de un check activo contra un tercero."""

    service: str
    ok: bool
    latency_ms: int | None = None
    detail: str | None = None
