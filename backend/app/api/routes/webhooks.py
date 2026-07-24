import hashlib
import hmac
import json
import time

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.services.channel_handler import ChannelHandler
from app.services.telegram_client import send_telegram_message
from app.services.whatsapp_provider import send_whatsapp_message

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
_handler = ChannelHandler()
# Instance-local deduplication; Postgres will provide cross-restart idempotency in stage two.
_processed_ycloud_events: set[str] = set()


@router.get("/whatsapp")
async def verify_whatsapp_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == settings.whatsapp_verify_token:
        return PlainTextResponse(challenge, status_code=200)

    return PlainTextResponse("Forbidden", status_code=403)


@router.post("/whatsapp")
async def receive_whatsapp(payload: dict):
    try:
        entry = payload.get("entry", [])
        if not entry:
            return {"status": "ok"}

        changes = entry[0].get("changes", [])
        if not changes:
            return {"status": "ok"}

        value = changes[0].get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return {"status": "ok"}

        msg = messages[0]
        phone = msg.get("from", "")
        msg_type = msg.get("type", "")
        text = ""

        if msg_type == "text":
            text = msg.get("text", {}).get("body", "")
        elif msg_type == "interactive":
            interactive = msg.get("interactive", {})
            button_reply = interactive.get("button_reply", {})
            text = button_reply.get("title", "")

        if text:
            response = _handler.handle_incoming("whatsapp", phone, text)
            send_whatsapp_message(phone, response)
    except Exception:
        pass

    return {"status": "ok"}


def _is_valid_ycloud_signature(raw_body: bytes, signature: str) -> bool:
    """Validate a YCloud ``t=timestamp,s=hex_signature`` header."""
    if not settings.ycloud_webhook_secret:
        return settings.ycloud_allow_unsigned_webhooks

    parts = {}
    for item in signature.split(","):
        key, separator, value = item.strip().partition("=")
        if not separator or not key or not value:
            return False
        parts[key] = value

    timestamp = parts.get("t")
    received_signature = parts.get("s")
    if not timestamp or not received_signature:
        return False

    try:
        timestamp_value = int(timestamp)
    except ValueError:
        return False

    if abs(time.time() - timestamp_value) > settings.ycloud_webhook_tolerance_seconds:
        return False

    signed_payload = timestamp.encode() + b"." + raw_body
    expected_signature = hmac.new(
        settings.ycloud_webhook_secret.encode(),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_signature, received_signature)


@router.post("/ycloud/whatsapp")
async def receive_ycloud_whatsapp(request: Request):
    """Receive inbound YCloud WhatsApp text messages."""
    raw_body = await request.body()
    signature = request.headers.get("YCloud-Signature", "")

    if not _is_valid_ycloud_signature(raw_body, signature):
        return JSONResponse({"detail": "Invalid signature"}, status_code=401)

    try:
        payload = json.loads(raw_body)
        if payload.get("type") != "whatsapp.inbound_message.received":
            return {"status": "ignored"}

        event_id = payload.get("id")
        if event_id and event_id in _processed_ycloud_events:
            return {"status": "ok"}

        message = payload.get("whatsappInboundMessage", {})
        phone = message.get("from", "")
        text = message.get("text", {}).get("body", "")
        if message.get("type") == "text" and phone and text:
            response = await run_in_threadpool(_handler.handle_incoming, "whatsapp", phone, text)
            sent = await run_in_threadpool(send_whatsapp_message, phone, response)
            if not sent:
                raise RuntimeError("message delivery failed")
            if event_id:
                _processed_ycloud_events.add(event_id)
    except Exception:
        return JSONResponse({"detail": "Webhook processing failed"}, status_code=502)

    return {"status": "ok"}


@router.post("/telegram")
async def receive_telegram(payload: dict):
    try:
        message = payload.get("message", {})
        chat = message.get("chat", {})
        chat_id = chat.get("id") or message.get("from", {}).get("id")
        text = message.get("text", "")

        if chat_id and text:
            response = _handler.handle_incoming("telegram", str(chat_id), text)
            send_telegram_message(chat_id, response)
    except Exception:
        pass

    return {"status": "ok"}


@router.get("/telegram/set")
async def set_telegram_webhook():
    if not settings.telegram_bot_token:
        return {"ok": False, "error": "telegram_bot_token not configured"}

    public_url = settings.frontend_url.replace("http://", "https://")
    if "localhost" in public_url or "127.0.0.1" in public_url:
        public_url = "https://tu-dominio.com"

    webhook_url = f"{public_url}/webhooks/telegram"
    api_url = (
        f"https://api.telegram.org/bot{settings.telegram_bot_token}"
        f"/setWebhook?url={webhook_url}"
    )

    if settings.telegram_webhook_secret:
        api_url += f"&secret_token={settings.telegram_webhook_secret}"

    try:
        resp = httpx.get(api_url, timeout=10)
        return resp.json()
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
