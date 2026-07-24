"""Check activo de conectividad con la API de Gemini (Google AI Studio).

Hace una llamada real mínima a `generateContent` para confirmar que la API
key configurada funciona. Nunca lanza excepción: cualquier fallo se traduce
en un `IntegrationCheckResult` con `ok=False`.
"""

import time

import httpx

from app.schemas.health import IntegrationCheckResult

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def check() -> IntegrationCheckResult:
    """Ejecuta un ping mínimo contra Gemini y devuelve el resultado."""
    from app.core.config import settings

    if not settings.gemini_api_key:
        return IntegrationCheckResult(
            service="gemini",
            ok=False,
            detail="no configurado: falta GEMINI_API_KEY",
        )

    payload = {
        "contents": [{"parts": [{"text": "ping"}]}],
        "generationConfig": {"maxOutputTokens": 1},
    }
    headers = {"x-goog-api-key": settings.gemini_api_key}

    start = time.perf_counter()
    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(GEMINI_URL, json=payload, headers=headers)
        latency_ms = int((time.perf_counter() - start) * 1000)

        if response.is_success:
            return IntegrationCheckResult(
                service="gemini",
                ok=True,
                latency_ms=latency_ms,
                detail=f"respuesta ok del modelo {GEMINI_MODEL}",
            )

        excerpt = response.text[:200]
        return IntegrationCheckResult(
            service="gemini",
            ok=False,
            latency_ms=latency_ms,
            detail=f"status {response.status_code}: {excerpt}",
        )
    except httpx.HTTPError as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return IntegrationCheckResult(
            service="gemini",
            ok=False,
            latency_ms=latency_ms,
            detail=f"{type(exc).__name__}: {exc}",
        )
