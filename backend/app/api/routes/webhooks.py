import hashlib
import hmac
import json
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.services import channel_gateway
from app.services.channel_handler import ChannelHandler
from app.services.channels.meta_whatsapp import MetaWhatsAppAdapter
from app.services.telegram_client import send_telegram_message, set_telegram_webhook
from app.services.whatsapp_provider import send_whatsapp_message

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
_handler = ChannelHandler()
_meta_adapter = MetaWhatsAppAdapter()


@router.get("/whatsapp")
async def verify_whatsapp_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if (
        settings.whatsapp_verify_token
        and mode == "subscribe"
        and token == settings.whatsapp_verify_token
    ):
        return PlainTextResponse(challenge, status_code=200)

    return PlainTextResponse("Forbidden", status_code=403)


@router.post("/whatsapp")
async def receive_whatsapp(payload: dict):
    try:
        inbound = _meta_adapter.parse_incoming(payload)
        if inbound is None:
            return {"status": "ok"}

        response = await run_in_threadpool(
            channel_gateway.handle, inbound.channel, inbound.user_ref, inbound.text
        )
        await run_in_threadpool(_meta_adapter.deliver, inbound.user_ref, response)
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
        if event_id and await run_in_threadpool(_handler.was_event_processed, event_id):
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
                await run_in_threadpool(_handler.mark_event_processed, event_id)
    except Exception:
        return JSONResponse({"detail": "Webhook processing failed"}, status_code=502)

    return {"status": "ok"}


@router.post("/telegram")
async def receive_telegram(request: Request, payload: dict):
    if settings.telegram_webhook_secret:
        received_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token") or ""
        if not hmac.compare_digest(received_token, settings.telegram_webhook_secret):
            return JSONResponse({"detail": "Invalid secret token"}, status_code=401)

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


@router.post("/telegram/set")
async def register_telegram_webhook():
    result = set_telegram_webhook()

    if result.get("ok") is False:
        return JSONResponse(result, status_code=503)

    return result
