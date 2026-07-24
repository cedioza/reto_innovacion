"""Client for sending WhatsApp messages through YCloud."""

import httpx

from app.core.config import settings

YCLOUD_MESSAGES_URL = "https://api.ycloud.com/v2/whatsapp/messages/sendDirectly"


def send_ycloud_message(to: str, text: str) -> bool:
    """Send a text WhatsApp message through YCloud.

    Returns ``False`` when credentials are missing or the request fails.
    """
    if not settings.ycloud_api_key or not settings.ycloud_whatsapp_from:
        return False

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": settings.ycloud_api_key,
    }
    payload = {
        "from": settings.ycloud_whatsapp_from,
        "to": to,
        "type": "text",
        "text": {"body": text},
    }

    try:
        response = httpx.post(
            YCLOUD_MESSAGES_URL,
            json=payload,
            headers=headers,
            timeout=10,
        )
        return response.is_success
    except Exception:
        return False
