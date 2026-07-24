import httpx

from app.core.config import settings

WHATSAPP_API = "https://graph.facebook.com/v21.0"


def send_whatsapp_message(to: str, text: str) -> bool:
    if not settings.whatsapp_token or not settings.whatsapp_phone_id:
        return False
    url = f"{WHATSAPP_API}/{settings.whatsapp_phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=10)
        return resp.is_success
    except Exception:
        return False
