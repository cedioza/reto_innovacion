"""Cliente de envío transaccional vía Resend (correo de handoff).

Clona el patrón httpx del health check ([resend.py](resend.py)): sin SDK,
timeout corto, y **nunca lanza excepción** — cualquier fallo (de red, de
status HTTP o de configuración) se traduce en un dict `{"ok": False,
"error": ...}` sin exponer la API key en ningún caso.
"""

import httpx

RESEND_URL = "https://api.resend.com/emails"
RESEND_FROM = "onboarding@resend.dev"


def send_email(to: str, subject: str, html: str) -> dict:
    """Envía un correo vía Resend y devuelve un resultado nunca-lanzante.

    Devuelve `{"ok": True, "id": ...}` en éxito o `{"ok": False, "error":
    ...}` en cualquier fallo (sin API key configurada, error HTTP o
    excepción de red). La API key nunca aparece en el resultado.
    """
    from app.core.config import settings

    if not settings.resend_api_key:
        return {"ok": False, "error": "no configurado: falta RESEND_API_KEY"}

    headers = {"Authorization": f"Bearer {settings.resend_api_key}"}
    payload = {
        "from": RESEND_FROM,
        "to": [to],
        "subject": subject,
        "html": html,
    }

    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(RESEND_URL, json=payload, headers=headers)

        if response.is_success:
            email_id = None
            try:
                email_id = response.json().get("id")
            except (ValueError, AttributeError):
                email_id = None
            return {"ok": True, "id": email_id}

        error_message = None
        try:
            error_message = response.json().get("message")
        except (ValueError, AttributeError):
            error_message = None

        excerpt = (error_message or response.text)[:200]
        return {"ok": False, "error": f"status {response.status_code}: {excerpt}"}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
