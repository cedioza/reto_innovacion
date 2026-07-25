"""Tests for the Telegram webhook secret token validation."""

from fastapi.testclient import TestClient

from app.api.routes import webhooks
from app.core.config import settings
from app.main import app

client = TestClient(app)


def _telegram_payload() -> dict:
    return {
        "message": {
            "chat": {"id": 42},
            "from": {"id": 42},
            "text": "hola",
        }
    }


def test_telegram_webhook_accepts_valid_secret_header(monkeypatch):
    monkeypatch.setattr(settings, "telegram_webhook_secret", "s3cret")
    handled = []
    monkeypatch.setattr(
        webhooks._handler,
        "handle_incoming",
        lambda channel, chat_id, text: handled.append((channel, chat_id, text)) or "Respuesta",
    )
    monkeypatch.setattr(webhooks, "send_telegram_message", lambda chat_id, text: True)

    response = client.post(
        "/api/v1/webhooks/telegram",
        json=_telegram_payload(),
        headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert handled == [("telegram", "42", "hola")]


def test_telegram_webhook_rejects_missing_secret_header(monkeypatch):
    monkeypatch.setattr(settings, "telegram_webhook_secret", "s3cret")
    handled = []
    monkeypatch.setattr(
        webhooks._handler,
        "handle_incoming",
        lambda channel, chat_id, text: handled.append((channel, chat_id, text)) or "Respuesta",
    )
    monkeypatch.setattr(webhooks, "send_telegram_message", lambda chat_id, text: True)

    response = client.post("/api/v1/webhooks/telegram", json=_telegram_payload())

    assert response.status_code == 401
    assert handled == []


def test_telegram_webhook_rejects_incorrect_secret_header(monkeypatch):
    monkeypatch.setattr(settings, "telegram_webhook_secret", "s3cret")
    handled = []
    monkeypatch.setattr(
        webhooks._handler,
        "handle_incoming",
        lambda channel, chat_id, text: handled.append((channel, chat_id, text)) or "Respuesta",
    )
    monkeypatch.setattr(webhooks, "send_telegram_message", lambda chat_id, text: True)

    response = client.post(
        "/api/v1/webhooks/telegram",
        json=_telegram_payload(),
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )

    assert response.status_code == 401
    assert handled == []


def test_telegram_webhook_allows_unconfigured_secret_without_header(monkeypatch):
    monkeypatch.setattr(settings, "telegram_webhook_secret", "")
    handled = []
    monkeypatch.setattr(
        webhooks._handler,
        "handle_incoming",
        lambda channel, chat_id, text: handled.append((channel, chat_id, text)) or "Respuesta",
    )
    monkeypatch.setattr(webhooks, "send_telegram_message", lambda chat_id, text: True)

    response = client.post("/api/v1/webhooks/telegram", json=_telegram_payload())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert handled == [("telegram", "42", "hola")]
