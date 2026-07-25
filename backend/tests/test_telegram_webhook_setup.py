"""Tests for the Telegram webhook registration endpoint (POST /webhooks/telegram/set)."""

import httpx
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services import telegram_client

client = TestClient(app)


class _Response:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_set_webhook_without_bot_token_returns_503(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "backend_public_url", "https://backend.example.com")

    response = client.post("/webhooks/telegram/set")

    assert response.status_code == 503
    assert response.json()["ok"] is False


def test_set_webhook_without_backend_public_url_returns_503_and_does_not_call_httpx(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "test-token")
    monkeypatch.setattr(settings, "backend_public_url", "")

    def fail_request(*args, **kwargs):
        raise AssertionError("request should not be made")

    monkeypatch.setattr(telegram_client.httpx, "post", fail_request)

    response = client.post("/webhooks/telegram/set")

    assert response.status_code == 503
    assert response.json()["ok"] is False


def test_set_webhook_success_sends_expected_payload(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "test-token")
    monkeypatch.setattr(settings, "backend_public_url", "https://backend.example.com")
    monkeypatch.setattr(settings, "telegram_webhook_secret", "s3cret")
    captured = {}

    def fake_post(*args, **kwargs):
        captured.update(url=args[0] if args else kwargs.get("url"), kwargs=kwargs)
        return _Response({"ok": True, "result": True})

    monkeypatch.setattr(telegram_client.httpx, "post", fake_post)

    response = client.post("/webhooks/telegram/set")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "result": True}
    assert captured["kwargs"]["json"]["url"] == "https://backend.example.com/webhooks/telegram"
    assert captured["kwargs"]["json"]["secret_token"] == "s3cret"


def test_set_webhook_network_error_returns_503_without_leaking_token(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "test-token")
    monkeypatch.setattr(settings, "backend_public_url", "https://backend.example.com")

    def fake_post(*args, **kwargs):
        raise httpx.ConnectError("Connection failed for url 'https://api.telegram.org/bottest-token/setWebhook'")

    monkeypatch.setattr(telegram_client.httpx, "post", fake_post)

    response = client.post("/webhooks/telegram/set")

    assert response.status_code == 503
    assert "test-token" not in response.text
