"""Check activo de conectividad con Resend (envío de correo).

Envía un correo de prueba real a `RESEND_TEST_TO` usando el remitente
`onboarding@resend.dev` del free tier para confirmar que la API key
configurada funciona. Nunca lanza excepción: cualquier fallo se traduce en un
`IntegrationCheckResult` con `ok=False`. La API key nunca aparece en `detail`.
"""

import time
from datetime import datetime, timezone

import httpx

from app.schemas.health import IntegrationCheckResult

RESEND_URL = "https://api.resend.com/emails"
RESEND_FROM = "onboarding@resend.dev"

# Mapa settings -> nombre de env var, para el mensaje de "no configurado".
_REQUIRED_ENV_BY_SETTING = {
    "resend_api_key": "RESEND_API_KEY",
    "resend_test_to": "RESEND_TEST_TO",
}


def check() -> IntegrationCheckResult:
    """Envía un correo de prueba vía Resend y devuelve el resultado."""
    from app.core.config import settings

    missing = [
        env_name
        for setting_name, env_name in _REQUIRED_ENV_BY_SETTING.items()
        if not getattr(settings, setting_name, "")
    ]
    if missing:
        return IntegrationCheckResult(
            service="resend",
            ok=False,
            detail=f"no configurado: falta(n) {', '.join(missing)}",
        )

    headers = {"Authorization": f"Bearer {settings.resend_api_key}"}
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = {
        "from": RESEND_FROM,
        "to": [settings.resend_test_to],
        "subject": f"health check ✅ {timestamp}",
        "text": "Correo de prueba del health check de integraciones (reto-innovacion).",
    }

    start = time.perf_counter()
    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(RESEND_URL, json=payload, headers=headers)
        latency_ms = int((time.perf_counter() - start) * 1000)

        if response.is_success:
            email_id = None
            try:
                email_id = response.json().get("id")
            except (ValueError, AttributeError):
                email_id = None

            detail = (
                f"correo enviado, id={email_id}"
                if email_id
                else "correo enviado correctamente"
            )
            return IntegrationCheckResult(
                service="resend",
                ok=True,
                latency_ms=latency_ms,
                detail=detail,
            )

        error_message = None
        try:
            error_message = response.json().get("message")
        except (ValueError, AttributeError):
            error_message = None

        excerpt = (error_message or response.text)[:200]
        return IntegrationCheckResult(
            service="resend",
            ok=False,
            latency_ms=latency_ms,
            detail=f"status {response.status_code}: {excerpt}",
        )
    except httpx.HTTPError as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return IntegrationCheckResult(
            service="resend",
            ok=False,
            latency_ms=latency_ms,
            detail=f"{type(exc).__name__}: {exc}",
        )
