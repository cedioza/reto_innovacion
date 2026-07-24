"""Tests de GET /health/integrations y de que /health sigue intacto."""

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)

INTEGRATION_SETTINGS_FIELDS = [
    "gemini_api_key",
    "whatsapp_token",
    "whatsapp_phone_id",
    "whatsapp_test_to",
    "database_url",
    "resend_api_key",
    "resend_test_to",
]


def _clear_integration_settings(monkeypatch) -> None:
    for field in INTEGRATION_SETTINGS_FIELDS:
        monkeypatch.setattr(settings, field, "")


def test_health_still_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_integrations_returns_all_services(monkeypatch):
    _clear_integration_settings(monkeypatch)

    response = client.get("/health/integrations")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"

    services = {item["service"]: item for item in body["data"]}
    assert set(services.keys()) == {"gemini", "whatsapp", "postgres", "resend"}
    for item in services.values():
        assert "configured" in item
        assert "required_env" in item
        assert isinstance(item["required_env"], list)


def test_all_unconfigured_when_settings_empty(monkeypatch):
    _clear_integration_settings(monkeypatch)

    response = client.get("/health/integrations")

    body = response.json()
    services = {item["service"]: item for item in body["data"]}
    for service in ("gemini", "whatsapp", "postgres", "resend"):
        assert services[service]["configured"] is False


def test_gemini_configured_when_key_present(monkeypatch):
    _clear_integration_settings(monkeypatch)
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    response = client.get("/health/integrations")

    services = {item["service"]: item for item in response.json()["data"]}
    assert services["gemini"]["configured"] is True
    assert services["whatsapp"]["configured"] is False


def test_whatsapp_requires_all_three_vars(monkeypatch):
    _clear_integration_settings(monkeypatch)
    monkeypatch.setattr(settings, "whatsapp_token", "test-token")
    monkeypatch.setattr(settings, "whatsapp_phone_id", "test-phone-id")
    # whatsapp_test_to sigue vacío: solo 2 de 3 vars configuradas.

    response = client.get("/health/integrations")

    services = {item["service"]: item for item in response.json()["data"]}
    assert services["whatsapp"]["configured"] is False

    monkeypatch.setattr(settings, "whatsapp_test_to", "573001234567")

    response = client.get("/health/integrations")

    services = {item["service"]: item for item in response.json()["data"]}
    assert services["whatsapp"]["configured"] is True


def test_postgres_and_resend_configured_with_fake_values(monkeypatch):
    _clear_integration_settings(monkeypatch)
    monkeypatch.setattr(settings, "database_url", "postgresql://user:pass@localhost/db")
    monkeypatch.setattr(settings, "resend_api_key", "test-resend-key")
    monkeypatch.setattr(settings, "resend_test_to", "test@example.com")

    response = client.get("/health/integrations")

    services = {item["service"]: item for item in response.json()["data"]}
    assert services["postgres"]["configured"] is True
    assert services["resend"]["configured"] is True
