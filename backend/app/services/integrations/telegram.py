"""Check activo de conectividad con la API de Telegram Bot (plan B de canal).

Envía un mensaje de texto real al chat de prueba configurado
(`TELEGRAM_TEST_CHAT_ID`) usando el bot creado con @BotFather para confirmar
que el token funciona de punta a punta. Nunca lanza excepción: cualquier
fallo se traduce en un `IntegrationCheckResult` con `ok=False`.

El token va dentro de la URL de la API de Telegram
(`https://api.telegram.org/bot{token}/...`), así que ningún mensaje de error
puede incluir la URL ni `str(exc)` de errores httpx (esas excepciones suelen
incluir la URL solicitada, y por tanto el token). Para errores de red se usa
únicamente `type(exc).__name__` con un texto fijo.
"""

import time
from datetime import datetime, timezone

import httpx

from app.schemas.health import IntegrationCheckResult

TELEGRAM_API_BASE = "https://api.telegram.org"

# Mapa settings -> nombre de env var, para el mensaje de "no configurado".
_REQUIRED_ENV_BY_SETTING = {
    "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
    "telegram_test_chat_id": "TELEGRAM_TEST_CHAT_ID",
}


def check() -> IntegrationCheckResult:
    """Envía un mensaje de prueba vía Telegram Bot API y devuelve el resultado."""
    from app.core.config import settings

    missing = [
        env_name
        for setting_name, env_name in _REQUIRED_ENV_BY_SETTING.items()
        if not getattr(settings, setting_name, "")
    ]
    if missing:
        return IntegrationCheckResult(
            service="telegram",
            ok=False,
            detail=f"no configurado: falta(n) {', '.join(missing)}",
        )

    url = f"{TELEGRAM_API_BASE}/bot{settings.telegram_bot_token}/sendMessage"
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "chat_id": settings.telegram_test_chat_id,
        "text": f"health check ✅ {timestamp}",
    }

    start = time.perf_counter()
    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(url, json=payload)
        latency_ms = int((time.perf_counter() - start) * 1000)

        body: dict | None = None
        try:
            body = response.json()
        except ValueError:
            body = None

        if response.is_success and isinstance(body, dict) and body.get("ok") is True:
            message_id = None
            try:
                message_id = body.get("result", {}).get("message_id")
            except AttributeError:
                message_id = None

            detail = (
                f"mensaje enviado, message_id={message_id}"
                if message_id
                else "mensaje enviado correctamente"
            )
            return IntegrationCheckResult(
                service="telegram",
                ok=True,
                latency_ms=latency_ms,
                detail=detail,
            )

        description = None
        if isinstance(body, dict):
            description = body.get("description")

        excerpt = (description or response.text)[:200]
        return IntegrationCheckResult(
            service="telegram",
            ok=False,
            latency_ms=latency_ms,
            detail=f"status {response.status_code}: {excerpt}",
        )
    except httpx.HTTPError as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return IntegrationCheckResult(
            service="telegram",
            ok=False,
            latency_ms=latency_ms,
            detail=f"error de red llamando a api.telegram.org ({type(exc).__name__})",
        )
