import httpx

from app.core.config import settings

TELEGRAM_API = "https://api.telegram.org/bot"


def send_telegram_message(
    chat_id: int | str, text: str, parse_mode: str | None = "Markdown"
) -> bool:
    if not settings.telegram_bot_token:
        return False
    url = f"{TELEGRAM_API}{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if parse_mode is not None:
        payload["parse_mode"] = parse_mode
    try:
        resp = httpx.post(url, json=payload, timeout=10)
        return resp.is_success
    except Exception:
        return False


def set_telegram_webhook() -> dict:
    if not settings.telegram_bot_token:
        return {"ok": False, "error": "telegram_bot_token not configured"}

    if not settings.backend_public_url:
        return {"ok": False, "error": "backend_public_url not configured"}

    webhook_url = f"{settings.backend_public_url.rstrip('/')}/api/v1/webhooks/telegram"
    api_url = f"{TELEGRAM_API}{settings.telegram_bot_token}/setWebhook"
    payload = {"url": webhook_url}
    if settings.telegram_webhook_secret:
        payload["secret_token"] = settings.telegram_webhook_secret

    try:
        resp = httpx.post(api_url, json=payload, timeout=10)
        return resp.json()
    except Exception as exc:
        # Never include str(exc) here: httpx connection errors can embed the
        # full request URL, which contains the bot token.
        return {"ok": False, "error": type(exc).__name__}
