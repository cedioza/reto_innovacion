"""Check activo de conectividad con WhatsApp Cloud API (Meta).

Envía un mensaje de texto real al número de prueba configurado
(`WHATSAPP_TEST_TO`) para confirmar que el token y el phone id funcionan de
punta a punta. Nunca lanza excepción: cualquier fallo se traduce en un
`IntegrationCheckResult` con `ok=False`. El token nunca aparece en `detail`.
"""

import time
from datetime import datetime, timezone

import httpx

from app.schemas.health import IntegrationCheckResult

WHATSAPP_API_VERSION = "v20.0"

# Mapa settings -> nombre de env var, para el mensaje de "no configurado".
_REQUIRED_ENV_BY_SETTING = {
    "whatsapp_token": "WHATSAPP_TOKEN",
    "whatsapp_phone_id": "WHATSAPP_PHONE_ID",
    "whatsapp_test_to": "WHATSAPP_TEST_TO",
}


def check() -> IntegrationCheckResult:
    """Envía un mensaje de prueba vía WhatsApp Cloud API y devuelve el resultado."""
    from app.core.config import settings

    missing = [
        env_name
        for setting_name, env_name in _REQUIRED_ENV_BY_SETTING.items()
        if not getattr(settings, setting_name, "")
    ]
    if missing:
        return IntegrationCheckResult(
            service="whatsapp",
            ok=False,
            detail=f"no configurado: falta(n) {', '.join(missing)}",
        )

    url = (
        f"https://graph.facebook.com/{WHATSAPP_API_VERSION}"
        f"/{settings.whatsapp_phone_id}/messages"
    )
    headers = {"Authorization": f"Bearer {settings.whatsapp_token}"}
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "messaging_product": "whatsapp",
        "to": settings.whatsapp_test_to,
        "type": "text",
        "text": {"body": f"health check ✅ {timestamp}"},
    }

    start = time.perf_counter()
    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(url, json=payload, headers=headers)
        latency_ms = int((time.perf_counter() - start) * 1000)

        if response.is_success:
            message_id = None
            try:
                message_id = response.json()["messages"][0]["id"]
            except (ValueError, KeyError, IndexError, TypeError):
                message_id = None

            detail = (
                f"mensaje enviado, message_id={message_id}"
                if message_id
                else "mensaje enviado correctamente"
            )
            return IntegrationCheckResult(
                service="whatsapp",
                ok=True,
                latency_ms=latency_ms,
                detail=detail,
            )

        error_message = None
        try:
            error_message = response.json().get("error", {}).get("message")
        except (ValueError, AttributeError):
            error_message = None

        excerpt = (error_message or response.text)[:200]
        return IntegrationCheckResult(
            service="whatsapp",
            ok=False,
            latency_ms=latency_ms,
            detail=f"status {response.status_code}: {excerpt}",
        )
    except httpx.HTTPError as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return IntegrationCheckResult(
            service="whatsapp",
            ok=False,
            latency_ms=latency_ms,
            detail=f"{type(exc).__name__}: {exc}",
        )
