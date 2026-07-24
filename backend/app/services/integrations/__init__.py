"""Registro de integraciones con terceros y utilidades comunes.

Cada integración declara qué campos de `Settings` necesita (`required_settings`)
y qué variables de entorno se le muestran al usuario (`required_env`). El check
activo (`check`) se implementa en fases posteriores; por ahora queda en `None`.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from app.schemas.health import IntegrationCheckResult


@dataclass
class Integration:
    """Descriptor de una integración con un tercero."""

    name: str
    required_settings: list[str] = field(default_factory=list)
    required_env: list[str] = field(default_factory=list)
    check: Callable[[], IntegrationCheckResult] | None = None


def is_configured(integration: Integration) -> bool:
    """True si todas las settings requeridas por la integración tienen valor.

    Lee `settings` en el momento de la llamada (no al importar el módulo) para
    que los tests puedan hacer monkeypatch sobre `app.core.config.settings`.
    """
    from app.core.config import settings

    return all(getattr(settings, attr, "") != "" for attr in integration.required_settings)


INTEGRATIONS: dict[str, Integration] = {
    "gemini": Integration(
        name="gemini",
        required_settings=["gemini_api_key"],
        required_env=["GEMINI_API_KEY"],
    ),
    "whatsapp": Integration(
        name="whatsapp",
        required_settings=["whatsapp_token", "whatsapp_phone_id", "whatsapp_test_to"],
        required_env=["WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID", "WHATSAPP_TEST_TO"],
    ),
    "postgres": Integration(
        name="postgres",
        required_settings=["database_url"],
        required_env=["DATABASE_URL"],
    ),
    "resend": Integration(
        name="resend",
        required_settings=["resend_api_key", "resend_test_to"],
        required_env=["RESEND_API_KEY", "RESEND_TEST_TO"],
    ),
}
