import httpx

from app.core.config import settings

TELEGRAM_API = "https://api.telegram.org/bot"


def send_telegram_message(chat_id: int | str, text: str) -> bool:
    if not settings.telegram_bot_token:
        return False
    url = f"{TELEGRAM_API}{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    try:
        resp = httpx.post(url, json=payload, timeout=10)
        return resp.is_success
    except Exception:
        return False
