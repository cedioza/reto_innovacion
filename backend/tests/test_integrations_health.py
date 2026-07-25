"""Tests de GET /api/v1/health/integrations y de que /api/v1/health sigue intacto."""

import httpx
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.integrations import INTEGRATIONS, Integration
from app.services.integrations import database as database_service
from app.services.integrations import gemini as gemini_service
from app.services.integrations import resend as resend_service
from app.services.integrations import telegram as telegram_service
from app.services.integrations import whatsapp as whatsapp_service

client = TestClient(app)

INTEGRATION_SETTINGS_FIELDS = [
    "gemini_api_key",
    "whatsapp_token",
    "whatsapp_phone_id",
    "whatsapp_test_to",
    "ycloud_api_key",
    "ycloud_whatsapp_from",
    "database_url",
    "resend_api_key",
    "resend_test_to",
    "telegram_bot_token",
    "telegram_test_chat_id",
]


def _clear_integration_settings(monkeypatch) -> None:
    for field in INTEGRATION_SETTINGS_FIELDS:
        monkeypatch.setattr(settings, field, "")


def test_health_still_ok():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_integrations_returns_all_services(monkeypatch):
    _clear_integration_settings(monkeypatch)

    response = client.get("/api/v1/health/integrations")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"

    services = {item["service"]: item for item in body["data"]}
    assert set(services.keys()) == {"gemini", "whatsapp", "postgres", "resend", "telegram"}
    for item in services.values():
        assert "configured" in item
        assert "required_env" in item
        assert isinstance(item["required_env"], list)


def test_all_unconfigured_when_settings_empty(monkeypatch):
    _clear_integration_settings(monkeypatch)

    response = client.get("/api/v1/health/integrations")

    body = response.json()
    services = {item["service"]: item for item in body["data"]}
    for service in ("gemini", "whatsapp", "postgres", "resend", "telegram"):
        assert services[service]["configured"] is False


def test_gemini_configured_when_key_present(monkeypatch):
    _clear_integration_settings(monkeypatch)
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    response = client.get("/api/v1/health/integrations")

    services = {item["service"]: item for item in response.json()["data"]}
    assert services["gemini"]["configured"] is True
    assert services["whatsapp"]["configured"] is False


def test_whatsapp_requires_all_three_vars(monkeypatch):
    _clear_integration_settings(monkeypatch)
    monkeypatch.setattr(settings, "whatsapp_provider", "meta")
    monkeypatch.setattr(settings, "whatsapp_token", "test-token")
    monkeypatch.setattr(settings, "whatsapp_phone_id", "test-phone-id")
    # whatsapp_test_to sigue vacío: solo 2 de 3 vars configuradas.

    response = client.get("/api/v1/health/integrations")

    services = {item["service"]: item for item in response.json()["data"]}
    assert services["whatsapp"]["configured"] is False

    monkeypatch.setattr(settings, "whatsapp_test_to", "573001234567")

    response = client.get("/api/v1/health/integrations")

    services = {item["service"]: item for item in response.json()["data"]}
    assert services["whatsapp"]["configured"] is True


def test_postgres_and_resend_configured_with_fake_values(monkeypatch):
    _clear_integration_settings(monkeypatch)
    monkeypatch.setattr(settings, "database_url", "postgresql://user:pass@localhost/db")
    monkeypatch.setattr(settings, "resend_api_key", "test-resend-key")
    monkeypatch.setattr(settings, "resend_test_to", "test@example.com")

    response = client.get("/api/v1/health/integrations")

    services = {item["service"]: item for item in response.json()["data"]}
    assert services["postgres"]["configured"] is True
    assert services["resend"]["configured"] is True


class _FakeResponse:
    def __init__(
        self, status_code: int, text: str = "", json_data: dict | None = None
    ) -> None:
        self.status_code = status_code
        self.text = text
        self.is_success = 200 <= status_code < 300
        self._json_data = json_data

    def json(self):
        if self._json_data is None:
            raise ValueError("respuesta fake sin cuerpo json")
        return self._json_data


class _FakeClient:
    """Sustituto de httpx.Client que responde con un status/text fijos.

    Si se le pasa `captured` (una lista), registra cada llamada a `post`
    (args/kwargs) para que el test pueda inspeccionar el payload enviado.
    """

    def __init__(self, response: _FakeResponse, captured: list | None = None) -> None:
        self._response = response
        self._captured = captured

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, *args, **kwargs):
        if self._captured is not None:
            self._captured.append({"args": args, "kwargs": kwargs})
        return self._response


class _RaisingClient:
    """Sustituto de httpx.Client que simula un fallo de red."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, *args, **kwargs):
        raise httpx.ConnectError("boom")


def test_post_gemini_success(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(
        gemini_service.httpx,
        "Client",
        lambda *a, **k: _FakeClient(_FakeResponse(200, "{}")),
    )

    response = client.post("/api/v1/health/integrations/gemini")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["data"]["service"] == "gemini"
    assert body["data"]["ok"] is True
    assert "latency_ms" in body["data"]
    assert body["data"]["latency_ms"] is not None


def test_post_gemini_error_status(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(
        gemini_service.httpx,
        "Client",
        lambda *a, **k: _FakeClient(_FakeResponse(401, "unauthorized")),
    )

    response = client.post("/api/v1/health/integrations/gemini")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"


def test_post_gemini_network_error(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(gemini_service.httpx, "Client", lambda *a, **k: _RaisingClient())

    response = client.post("/api/v1/health/integrations/gemini")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"


def test_post_gemini_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")

    response = client.post("/api/v1/health/integrations/gemini")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert "no configurado" in body["details"]["detail"]


def test_post_unknown_service_returns_404():
    response = client.post("/api/v1/health/integrations/noexiste")

    assert response.status_code == 404
    body = response.json()
    assert body["status"] == "error"


def test_post_check_not_implemented_yet():
    """Cubre el branch 503 "check no implementado" del router, con una
    integración fake registrada temporalmente (todas las reales ya tienen
    `check` implementado)."""
    INTEGRATIONS["fake"] = Integration(name="fake", required_settings=[], required_env=[])
    try:
        response = client.post("/api/v1/health/integrations/fake")
    finally:
        del INTEGRATIONS["fake"]

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert "no implementado" in body["message"]


class _FakeCursor:
    """Sustituto de un cursor de psycopg: recuerda la última query ejecutada."""

    def __init__(self) -> None:
        self._last_query: str | None = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, *args, **kwargs):
        self._last_query = query

    def fetchone(self):
        if self._last_query == "SELECT 1":
            return (1,)
        if self._last_query == "SHOW server_version":
            return ("16.4",)
        return None


class _FakeConnection:
    """Sustituto de una conexión de psycopg usada como context manager."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return _FakeCursor()


def test_post_postgres_success(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "postgresql://user:pass@localhost/db")
    monkeypatch.setattr(
        database_service.psycopg,
        "connect",
        lambda *a, **k: _FakeConnection(),
    )

    response = client.post("/api/v1/health/integrations/postgres")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["data"]["service"] == "postgres"
    assert body["data"]["ok"] is True
    assert "latency_ms" in body["data"]
    assert body["data"]["latency_ms"] is not None


def test_post_postgres_operational_error(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "postgresql://user:pass@localhost/db")

    def _raise(*args, **kwargs):
        raise database_service.psycopg.OperationalError("connection refused")

    monkeypatch.setattr(database_service.psycopg, "connect", _raise)

    response = client.post("/api/v1/health/integrations/postgres")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"


def test_post_postgres_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "")

    response = client.post("/api/v1/health/integrations/postgres")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert "no configurado" in body["details"]["detail"]
    assert "DATABASE_URL" in body["details"]["detail"]


def test_post_whatsapp_success(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_provider", "meta")
    monkeypatch.setattr(settings, "whatsapp_token", "test-token")
    monkeypatch.setattr(settings, "whatsapp_phone_id", "123456")
    monkeypatch.setattr(settings, "whatsapp_test_to", "573001234567")

    captured: list = []
    fake_response = _FakeResponse(
        200, "{}", json_data={"messages": [{"id": "wamid.TEST"}]}
    )
    monkeypatch.setattr(
        whatsapp_service.httpx,
        "Client",
        lambda *a, **k: _FakeClient(fake_response, captured),
    )

    response = client.post("/api/v1/health/integrations/whatsapp")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["data"]["service"] == "whatsapp"
    assert body["data"]["ok"] is True
    assert "wamid.TEST" in body["data"]["detail"]

    assert len(captured) == 1
    sent_payload = captured[0]["kwargs"]["json"]
    assert sent_payload["messaging_product"] == "whatsapp"
    assert sent_payload["to"] == "573001234567"


def test_post_whatsapp_meta_error(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_provider", "meta")
    monkeypatch.setattr(settings, "whatsapp_token", "invalid-token")
    monkeypatch.setattr(settings, "whatsapp_phone_id", "123456")
    monkeypatch.setattr(settings, "whatsapp_test_to", "573001234567")

    fake_response = _FakeResponse(
        401,
        text='{"error": {"message": "Invalid OAuth access token"}}',
        json_data={"error": {"message": "Invalid OAuth access token"}},
    )
    monkeypatch.setattr(
        whatsapp_service.httpx,
        "Client",
        lambda *a, **k: _FakeClient(fake_response),
    )

    response = client.post("/api/v1/health/integrations/whatsapp")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert "Invalid OAuth access token" in body["details"]["detail"]


def test_post_whatsapp_network_error(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_provider", "meta")
    monkeypatch.setattr(settings, "whatsapp_token", "test-token")
    monkeypatch.setattr(settings, "whatsapp_phone_id", "123456")
    monkeypatch.setattr(settings, "whatsapp_test_to", "573001234567")
    monkeypatch.setattr(whatsapp_service.httpx, "Client", lambda *a, **k: _RaisingClient())

    response = client.post("/api/v1/health/integrations/whatsapp")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"


def test_post_whatsapp_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_provider", "meta")
    monkeypatch.setattr(settings, "whatsapp_token", "test-token")
    monkeypatch.setattr(settings, "whatsapp_phone_id", "123456")
    monkeypatch.setattr(settings, "whatsapp_test_to", "")

    response = client.post("/api/v1/health/integrations/whatsapp")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert "no configurado" in body["details"]["detail"]
    assert "WHATSAPP_TEST_TO" in body["details"]["detail"]


def test_post_whatsapp_ycloud_check_only_validates_configuration(monkeypatch):
    monkeypatch.setattr(settings, "whatsapp_provider", "ycloud")
    monkeypatch.setattr(settings, "ycloud_api_key", "ycloud-key")
    monkeypatch.setattr(settings, "ycloud_whatsapp_from", "57300999")
    monkeypatch.setattr(whatsapp_service.httpx, "Client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no request")))

    response = client.post("/api/v1/health/integrations/whatsapp")

    assert response.status_code == 200
    assert response.json()["data"]["ok"] is True


def test_post_resend_success(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "test-resend-key")
    monkeypatch.setattr(settings, "resend_test_to", "test@example.com")

    captured: list = []
    fake_response = _FakeResponse(200, "{}", json_data={"id": "re_TEST123"})
    monkeypatch.setattr(
        resend_service.httpx,
        "Client",
        lambda *a, **k: _FakeClient(fake_response, captured),
    )

    response = client.post("/api/v1/health/integrations/resend")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["data"]["service"] == "resend"
    assert body["data"]["ok"] is True
    assert "re_TEST123" in body["data"]["detail"]

    assert len(captured) == 1
    sent_payload = captured[0]["kwargs"]["json"]
    assert sent_payload["to"] == ["test@example.com"]
    assert sent_payload["from"] == "onboarding@resend.dev"


def test_post_resend_error_status(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "invalid-key")
    monkeypatch.setattr(settings, "resend_test_to", "test@example.com")

    fake_response = _FakeResponse(
        401,
        text='{"message": "API key is invalid"}',
        json_data={"message": "API key is invalid"},
    )
    monkeypatch.setattr(
        resend_service.httpx,
        "Client",
        lambda *a, **k: _FakeClient(fake_response),
    )

    response = client.post("/api/v1/health/integrations/resend")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert "API key is invalid" in body["details"]["detail"]


def test_post_resend_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "test-resend-key")
    monkeypatch.setattr(settings, "resend_test_to", "")

    response = client.post("/api/v1/health/integrations/resend")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert "no configurado" in body["details"]["detail"]
    assert "RESEND_TEST_TO" in body["details"]["detail"]


class _TokenLeakingRaisingClient:
    """Sustituto de httpx.Client que simula un ConnectError cuya excepción
    incluye la URL solicitada (y por tanto el token) en su mensaje, tal como
    hace httpx de verdad."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, *args, **kwargs):
        raise httpx.ConnectError("boom https://api.telegram.org/botSECRET/sendMessage")


def test_post_telegram_success(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "test-bot-token")
    monkeypatch.setattr(settings, "telegram_test_chat_id", "123456789")

    captured: list = []
    fake_response = _FakeResponse(
        200, "{}", json_data={"ok": True, "result": {"message_id": 42}}
    )
    monkeypatch.setattr(
        telegram_service.httpx,
        "Client",
        lambda *a, **k: _FakeClient(fake_response, captured),
    )

    response = client.post("/api/v1/health/integrations/telegram")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["data"]["service"] == "telegram"
    assert body["data"]["ok"] is True
    assert "42" in body["data"]["detail"]

    assert len(captured) == 1
    sent_payload = captured[0]["kwargs"]["json"]
    assert sent_payload["chat_id"] == "123456789"


def test_post_telegram_error_status(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "invalid-token")
    monkeypatch.setattr(settings, "telegram_test_chat_id", "123456789")

    fake_response = _FakeResponse(
        401,
        text='{"ok": false, "description": "Unauthorized"}',
        json_data={"ok": False, "description": "Unauthorized"},
    )
    monkeypatch.setattr(
        telegram_service.httpx,
        "Client",
        lambda *a, **k: _FakeClient(fake_response),
    )

    response = client.post("/api/v1/health/integrations/telegram")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert "Unauthorized" in body["details"]["detail"]


def test_post_telegram_network_error_does_not_leak_token(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "SECRET")
    monkeypatch.setattr(settings, "telegram_test_chat_id", "123456789")
    monkeypatch.setattr(
        telegram_service.httpx, "Client", lambda *a, **k: _TokenLeakingRaisingClient()
    )

    response = client.post("/api/v1/health/integrations/telegram")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert "SECRET" not in response.text


def test_post_telegram_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "test-bot-token")
    monkeypatch.setattr(settings, "telegram_test_chat_id", "")

    response = client.post("/api/v1/health/integrations/telegram")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert "no configurado" in body["details"]["detail"]
    assert "TELEGRAM_TEST_CHAT_ID" in body["details"]["detail"]
