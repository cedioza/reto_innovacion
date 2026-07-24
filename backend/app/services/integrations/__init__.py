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

    if integration.name == "whatsapp" and settings.whatsapp_provider.lower() == "meta":
        required_settings = ["whatsapp_token", "whatsapp_phone_id", "whatsapp_test_to"]
    else:
        required_settings = integration.required_settings
    return all(getattr(settings, attr, "") != "" for attr in required_settings)


INTEGRATIONS: dict[str, Integration] = {
    "gemini": Integration(
        name="gemini",
        required_settings=["gemini_api_key"],
        required_env=["GEMINI_API_KEY"],
    ),
    "whatsapp": Integration(
        name="whatsapp",
        required_settings=["ycloud_api_key", "ycloud_whatsapp_from"],
        required_env=["YCLOUD_API_KEY", "YCLOUD_WHATSAPP_FROM"],
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
    "telegram": Integration(
        name="telegram",
        required_settings=["telegram_bot_token", "telegram_test_chat_id"],
        required_env=["TELEGRAM_BOT_TOKEN", "TELEGRAM_TEST_CHAT_ID"],
    ),
}


def _register_checks() -> None:
    """Enlaza el `check()` de cada módulo de integración a su entrada en el registro.

    Import diferido (dentro de la función) para evitar ciclos: los módulos de
    check importan `app.schemas.health`, no este paquete.
    """
    from app.services.integrations import database, gemini, whatsapp
    from app.services.integrations import resend as resend_service
    from app.services.integrations import telegram as telegram_service

    INTEGRATIONS["gemini"].check = gemini.check
    INTEGRATIONS["whatsapp"].check = whatsapp.check
    INTEGRATIONS["postgres"].check = database.check
    INTEGRATIONS["resend"].check = resend_service.check
    INTEGRATIONS["telegram"].check = telegram_service.check


_register_checks()


def required_env_for(integration: Integration) -> list[str]:
    """Return provider-specific configuration names for the WhatsApp entry."""
    if integration.name == "whatsapp":
        from app.core.config import settings

        if settings.whatsapp_provider.lower() == "meta":
            return ["WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID", "WHATSAPP_TEST_TO"]
    return integration.required_env
