"""Focused tests for YCloud WhatsApp integration and provider selection."""

import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient

from app.api.routes import webhooks
from app.core.config import settings
from app.main import app
from app.services import whatsapp_provider, ycloud_whatsapp_client

client = TestClient(app)


class _Response:
    def __init__(self, success: bool) -> None:
        self.is_success = success


def _ycloud_payload() -> dict:
    return {
        "id": "evt_123",
        "type": "whatsapp.inbound_message.received",
        "whatsappInboundMessage": {
            "from": "573001234567",
            "type": "text",
            "text": {"body": "Hola"},
        },
    }


def _signed_body(payload: dict, secret: str, timestamp: str | None = None):
    timestamp = timestamp or str(int(time.time()))
    raw_body = json.dumps(payload, separators=(",", ":")).encode()
    digest = hmac.new(
        secret.encode(), timestamp.encode() + b"." + raw_body, hashlib.sha256
    ).hexdigest()
    return raw_body, f"t={timestamp},s={digest}"


def test_ycloud_client_without_configuration_does_not_request(monkeypatch):
    monkeypatch.setattr(settings, "ycloud_api_key", "")
    monkeypatch.setattr(settings, "ycloud_whatsapp_from", "")

    def fail_request(*args, **kwargs):
        raise AssertionError("request should not be made")

    monkeypatch.setattr(ycloud_whatsapp_client.httpx, "post", fail_request)

    assert ycloud_whatsapp_client.send_ycloud_message("57300", "Hola") is False


def test_ycloud_client_sends_expected_payload(monkeypatch):
    monkeypatch.setattr(settings, "ycloud_api_key", "test-key")
    monkeypatch.setattr(settings, "ycloud_whatsapp_from", "57300999")
    captured = {}

    def fake_post(*args, **kwargs):
        captured.update(url=args[0], kwargs=kwargs)
        return _Response(True)

    monkeypatch.setattr(ycloud_whatsapp_client.httpx, "post", fake_post)

    assert ycloud_whatsapp_client.send_ycloud_message("57300", "Hola") is True
    assert captured["url"].endswith("/v2/whatsapp/messages/sendDirectly")
    assert captured["kwargs"]["headers"]["X-API-Key"] == "test-key"
    assert captured["kwargs"]["json"] == {
        "from": "57300999",
        "to": "57300",
        "type": "text",
        "text": {"body": "Hola"},
    }


def test_provider_selects_ycloud_by_default(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_provider", "ycloud")
    monkeypatch.setattr(whatsapp_provider, "send_ycloud_message", lambda to, text: True)

    assert whatsapp_provider.send_whatsapp_message("57300", "Hola") is True


def test_provider_selects_meta(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_provider", "meta")
    monkeypatch.setattr(whatsapp_provider, "send_meta_message", lambda to, text: True)

    assert whatsapp_provider.send_whatsapp_message("57300", "Hola") is True


def test_ycloud_webhook_accepts_valid_signature_and_sends_response(monkeypatch):
    secret = "webhook-secret"
    monkeypatch.setattr(settings, "ycloud_webhook_secret", secret)
    raw_body, signature = _signed_body(_ycloud_payload(), secret)
    handled = []
    sent = []
    monkeypatch.setattr(
        webhooks._handler,
        "handle_incoming",
        lambda channel, phone, text: handled.append((channel, phone, text)) or "Respuesta",
    )
    monkeypatch.setattr(
        webhooks, "send_whatsapp_message", lambda phone, text: sent.append((phone, text)) or True
    )

    response = client.post(
        "/webhooks/ycloud/whatsapp",
        content=raw_body,
        headers={"YCloud-Signature": signature},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert handled == [("whatsapp", "573001234567", "Hola")]
    assert sent == [("573001234567", "Respuesta")]


def test_ycloud_webhook_returns_5xx_when_processing_fails(monkeypatch):
    monkeypatch.setattr(settings, "ycloud_webhook_secret", "")
    monkeypatch.setattr(settings, "ycloud_allow_unsigned_webhooks", True)
    monkeypatch.setattr(webhooks._handler, "handle_incoming", lambda *args: "Respuesta")
    monkeypatch.setattr(webhooks, "send_whatsapp_message", lambda *args: False)

    payload = _ycloud_payload()
    payload["id"] = "evt_delivery_failure"
    response = client.post("/webhooks/ycloud/whatsapp", json=payload)

    assert response.status_code == 502
    assert response.json() == {"detail": "Webhook processing failed"}


def test_ycloud_webhook_deduplicates_event_in_process(monkeypatch):
    monkeypatch.setattr(settings, "ycloud_webhook_secret", "")
    monkeypatch.setattr(settings, "ycloud_allow_unsigned_webhooks", True)
    handled = []
    monkeypatch.setattr(
        webhooks._handler,
        "handle_incoming",
        lambda *args: handled.append(args) or "Respuesta",
    )
    monkeypatch.setattr(webhooks, "send_whatsapp_message", lambda *args: True)

    payload = _ycloud_payload()
    payload["id"] = "evt_dedupe"
    first = client.post("/webhooks/ycloud/whatsapp", json=payload)
    second = client.post("/webhooks/ycloud/whatsapp", json=payload)

    assert first.status_code == second.status_code == 200
    assert handled == [("whatsapp", "573001234567", "Hola")]


def test_ycloud_webhook_rejects_invalid_signature(monkeypatch):
    monkeypatch.setattr(settings, "ycloud_webhook_secret", "webhook-secret")
    monkeypatch.setattr(webhooks.time, "time", lambda: 1720000000)

    response = client.post(
        "/webhooks/ycloud/whatsapp",
        json=_ycloud_payload(),
        headers={"YCloud-Signature": "t=1720000000,s=invalid"},
    )

    assert response.status_code == 401


def test_ycloud_webhook_rejects_unsigned_by_default(monkeypatch):
    monkeypatch.setattr(settings, "ycloud_webhook_secret", "")
    monkeypatch.setattr(settings, "ycloud_allow_unsigned_webhooks", False)

    response = client.post("/webhooks/ycloud/whatsapp", json=_ycloud_payload())

    assert response.status_code == 401


def test_ycloud_webhook_allows_unsigned_only_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "ycloud_webhook_secret", "")
    monkeypatch.setattr(settings, "ycloud_allow_unsigned_webhooks", True)
    monkeypatch.setattr(webhooks._handler, "handle_incoming", lambda *args: "Respuesta")
    monkeypatch.setattr(webhooks, "send_whatsapp_message", lambda *args: True)

    response = client.post("/webhooks/ycloud/whatsapp", json=_ycloud_payload())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ycloud_webhook_rejects_old_signature(monkeypatch):
    secret = "webhook-secret"
    monkeypatch.setattr(settings, "ycloud_webhook_secret", secret)
    monkeypatch.setattr(webhooks.time, "time", lambda: 1720001000)
    raw_body, signature = _signed_body(_ycloud_payload(), secret, "1720000000")

    response = client.post(
        "/webhooks/ycloud/whatsapp",
        content=raw_body,
        headers={"YCloud-Signature": signature},
    )

    assert response.status_code == 401


def test_ycloud_webhook_ignores_other_events(monkeypatch):
    monkeypatch.setattr(settings, "ycloud_webhook_secret", "")
    monkeypatch.setattr(settings, "ycloud_allow_unsigned_webhooks", True)
    payload = {"type": "whatsapp.message.delivered"}

    response = client.post("/webhooks/ycloud/whatsapp", json=payload)

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


def test_meta_webhook_verification_remains_available(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_verify_token", "verify-token")

    response = client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-token",
            "hub.challenge": "challenge",
        },
    )

    assert response.status_code == 200
    assert response.text == "challenge"
