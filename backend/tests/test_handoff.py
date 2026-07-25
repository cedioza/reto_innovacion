"""Tests de la Fase 1 de E1 (handoff por correo con link de aseguradora simulada).

Cubre dos piezas puras, sin tocar el flujo de conversación todavía:

- `app.services.integrations.resend_client.send_email` — cliente httpx que
  nunca lanza (patrón clonado de `integrations/resend.py`, el health check).
- `app.services.handoff` — `INSURER_BY_PRODUCT`/`insurer_for`, `new_token` y
  `build_handoff_email` (comprobante de la solicitud en HTML inline).

Ambos módulos aún no existen: este archivo debe fallar por `ImportError` hasta
que la Fase 1 los implemente (TDD-light).
"""

import httpx
import pytest

from app.core.config import settings
from app.schemas.conversation import (
    ConsentedApplication,
    ProfileData,
    QuoteDetail,
    Recommendation,
)
from app.services import handoff
from app.services.integrations import resend_client


# ---------------------------------------------------------------------------
# Fixture de application consentida (motor real de schemas, datos de prueba).
# ---------------------------------------------------------------------------


@pytest.fixture
def application() -> ConsentedApplication:
    return ConsentedApplication(
        session_id="sess-e1-fase1",
        product_id="hogar-estandar",
        profile=ProfileData(
            property_type="apartamento",
            zone="norte",
            stratum=4,
            age_range="30-40",
            has_family=True,
        ),
        recommendation=Recommendation(
            product_id="hogar-estandar",
            product_name="Hogar Estándar",
            reasons=[
                {
                    "label": "Cobertura de incendio adecuada al estrato",
                    "evidence": "Estrato 4 con inmueble propio",
                },
                {
                    "label": "Ajuste por zona de riesgo medio",
                    "evidence": "Zona norte, sin siniestros reportados",
                },
            ],
        ),
        quote=QuoteDetail(
            currency="COP",
            base_amount=1_000_000.0,
            adjustments=[],
            monthly_premium=3750.0,
            annual_premium=45000.0,
            coverage_details=["Incendio", "Robo", "Responsabilidad civil"],
            exclusions=["Guerra", "Desastres naturales no cubiertos"],
        ),
        consent_timestamp="2026-07-25T10:00:00-05:00",
    )


# ---------------------------------------------------------------------------
# insurer_for / INSURER_BY_PRODUCT
# ---------------------------------------------------------------------------


def test_insurer_for_known_product_returns_mapped_insurer():
    assert handoff.insurer_for("hogar-estandar") == "Seguros Bolívar"


def test_insurer_for_unknown_product_falls_back():
    assert handoff.insurer_for("producto-x") == "la aseguradora aliada"


# ---------------------------------------------------------------------------
# new_token
# ---------------------------------------------------------------------------


def test_new_token_generates_distinct_urlsafe_tokens():
    token_a = handoff.new_token()
    token_b = handoff.new_token()

    assert token_a != token_b
    assert len(token_a) >= 40
    assert len(token_b) >= 40
    for token in (token_a, token_b):
        assert "+" not in token
        assert "/" not in token
        assert "=" not in token


# ---------------------------------------------------------------------------
# build_handoff_email
# ---------------------------------------------------------------------------


def test_build_handoff_email_subject_mentions_product(application):
    token = "tok-fase1-abc"

    subject, _html = handoff.build_handoff_email(application, token)

    assert "Comprobante" in subject
    assert "Hogar Estándar" in subject


def test_build_handoff_email_html_contains_expected_content(application):
    token = "tok-fase1-abc123"

    _subject, html = handoff.build_handoff_email(application, token)

    # Producto.
    assert "Hogar Estándar" in html

    # Prima mensual y anual, formateadas con separador de miles (COP).
    assert "3.750" in html
    assert "45.000" in html

    # Al menos 2 razones (label) de la recomendación.
    assert "Cobertura de incendio adecuada al estrato" in html
    assert "Ajuste por zona de riesgo medio" in html

    # Link de handoff con el token, hacia la ruta de aseguradora simulada.
    assert f"/aseguradora/{token}" in html

    # Etiqueta de simulación visible (case-insensitive).
    assert "simulaci" in html.lower()

    # Nombre de la aseguradora simulada del producto.
    assert "Seguros Bolívar" in html


def test_build_handoff_email_uses_frontend_url_setting(application, monkeypatch):
    monkeypatch.setattr(settings, "frontend_url", "https://demo.example.com")
    token = "tok-fase1-xyz"

    _subject, html = handoff.build_handoff_email(application, token)

    assert f"https://demo.example.com/aseguradora/{token}" in html


# ---------------------------------------------------------------------------
# resend_client.send_email — httpx mockeado, cero red real.
# ---------------------------------------------------------------------------


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
    """Sustituto de httpx.Client que responde con un status/json fijos."""

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


def test_send_email_success(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "test-resend-key")

    captured: list = []
    fake_response = _FakeResponse(200, json_data={"id": "re_ABC123"})
    monkeypatch.setattr(
        resend_client.httpx,
        "Client",
        lambda *a, **k: _FakeClient(fake_response, captured),
    )

    result = resend_client.send_email(
        "cliente@example.com", "Comprobante de tu solicitud", "<p>hola</p>"
    )

    assert result == {"ok": True, "id": "re_ABC123"}
    assert len(captured) == 1
    sent_payload = captured[0]["kwargs"]["json"]
    assert sent_payload["from"] == "onboarding@resend.dev"
    assert sent_payload["to"] == ["cliente@example.com"]
    assert sent_payload["subject"] == "Comprobante de tu solicitud"
    assert "test-resend-key" not in str(result)


def test_send_email_http_error_status(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "test-resend-key")

    fake_response = _FakeResponse(
        422,
        text='{"message": "invalid `to` field"}',
        json_data={"message": "invalid `to` field"},
    )
    monkeypatch.setattr(
        resend_client.httpx, "Client", lambda *a, **k: _FakeClient(fake_response)
    )

    result = resend_client.send_email("no-es-un-correo", "Asunto", "<p>hola</p>")

    assert result["ok"] is False
    assert "422" in result["error"]
    assert "test-resend-key" not in result["error"]


def test_send_email_network_exception(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "test-resend-key")
    monkeypatch.setattr(resend_client.httpx, "Client", lambda *a, **k: _RaisingClient())

    result = resend_client.send_email(
        "cliente@example.com", "Asunto", "<p>hola</p>"
    )

    assert result["ok"] is False
    assert "ConnectError" in result["error"]
    assert "test-resend-key" not in result["error"]


def test_send_email_not_configured_skips_network_call(monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "")

    called: list = []

    def _boom(*args, **kwargs):
        called.append((args, kwargs))
        raise AssertionError("no debería llamarse a httpx.Client sin API key")

    monkeypatch.setattr(resend_client.httpx, "Client", _boom)

    result = resend_client.send_email(
        "cliente@example.com", "Asunto", "<p>hola</p>"
    )

    assert result == {"ok": False, "error": "no configurado: falta RESEND_API_KEY"}
    assert called == []
