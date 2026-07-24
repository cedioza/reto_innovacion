"""Configurable WhatsApp provider selection."""

from app.core.config import settings
from app.services.whatsapp_client import send_whatsapp_message as send_meta_message
from app.services.ycloud_whatsapp_client import send_ycloud_message


def send_whatsapp_message(to: str, text: str) -> bool:
    """Send a WhatsApp message using the configured provider."""
    provider = settings.whatsapp_provider.lower()
    if provider == "ycloud":
        return send_ycloud_message(to, text)
    if provider == "meta":
        return send_meta_message(to, text)
    return False
