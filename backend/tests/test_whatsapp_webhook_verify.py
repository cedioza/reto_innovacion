"""Tests for GET /api/v1/webhooks/whatsapp (Meta webhook verification handshake)."""

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


def test_verify_whatsapp_webhook_succeeds_with_correct_token(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_verify_token", "token-prueba")

    response = client.get(
        "/api/v1/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "token-prueba",
            "hub.challenge": "1234",
        },
    )

    assert response.status_code == 200
    assert response.text == "1234"


def test_verify_whatsapp_webhook_rejects_wrong_token(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_verify_token", "token-prueba")

    response = client.get(
        "/api/v1/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "otro-token",
            "hub.challenge": "1234",
        },
    )

    assert response.status_code == 403


def test_verify_whatsapp_webhook_fails_closed_when_token_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_verify_token", "")

    response = client.get(
        "/api/v1/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "",
            "hub.challenge": "1234",
        },
    )

    assert response.status_code == 403
