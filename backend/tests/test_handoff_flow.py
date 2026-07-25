"""Tests de la Fase 2 de E1 (handoff por correo con link de aseguradora simulada).

Cubre el disparo del correo de handoff al capturar el consentimiento, tanto
desde la tool `cerrar_venta` (LLM) como desde el endpoint estructurado
`POST /{id}/consent`, y la exigencia de correo antes de cerrar (criterio 2
del vault: "sin correo declarado, el bot lo pide antes del consentimiento").

Piezas que este archivo ejercita y que la Fase 2 debe implementar (RED hasta
entonces):
- `cerrar_venta` exige `email` (declaración + handler): sin email o con
  formato inválido, error controlado y NUNCA se crea la solicitud
  (`ConsentService.capture` no se invoca).
- `ConsentService.capture(..., email=...)` genera SIEMPRE `handoff_token` e
  `insurer_name`; si hay email, dispara el correo (best-effort: un fallo o
  una excepción de Resend jamás rompen el cierre, solo se loguea).
- `ConversationService.submit_consent(..., email=...)` propaga el email del
  endpoint estructurado.

Convención de mockeo: el correo SIEMPRE se mockea (cero red real). Se asume
que el consumidor (`app.services.consent`) llama a
`resend_client.send_email(...)` por acceso de atributo sobre el módulo
`app.services.integrations.resend_client` (tal como lo describe el plan de
Fase 2 y el patrón ya usado en `tests/test_handoff.py`), así que parchear
`resend_client.send_email` alcanza sin importar el alias local que use
`consent.py` para importarlo (siempre que sea `from ... import
resend_client` y no `from ... import send_email`, que copiaría el nombre
antes de que el monkeypatch actúe).

Nota de diseño de los tests: `ConsentService.capture` crea un
`ApplicationRepository()` NUEVO en cada `ConsentService()` (ver
`app/services/consent.py`), así que un `ConsentService().get_application(...)`
desde el test (una instancia distinta a la que usa el handler de la tool)
nunca vería lo persistido por esa otra instancia — no es una forma fiable de
verificar "se creó/no se creó la solicitud" para la tool. Por eso, la
ausencia de solicitud se verifica espiando que `ConsentService.capture` no se
haya invocado, y la creación exitosa se verifica sobre el dict que la propia
tool devuelve (que ES la solicitud serializada).
"""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from app.main import app
from app.services.agent_tools import ToolContext, execute_tool
from app.services.consent import ConsentService
from app.services.integrations import resend_client
from app.services.integrations.gemini_client import GeminiReply
import app.services.orchestrator as orchestrator

client = TestClient(app)


FAVORABLE_ARGS = {
    "property_type": "house",
    "zone": "urban",
    "stratum": 3,
    "age_range": "26-40",
}


def _build_full_funnel_ctx(session_id: str) -> ToolContext:
    """Perfila, recomienda y cotiza en un mismo ToolContext (motor real).

    Deja el ctx listo para `cerrar_venta`, igual que en
    `tests/test_agent_tools.py`.
    """
    ctx = ToolContext(session_id=session_id)
    execute_tool("perfilar_cliente", dict(FAVORABLE_ARGS), ctx)
    execute_tool("recomendar_seguro", {}, ctx)
    execute_tool("cotizar", {}, ctx)
    return ctx


def _mock_send_email_ok(monkeypatch, captured: list | None = None):
    """Mockea `resend_client.send_email` para que nunca haga red real."""

    def _fake(to, subject, html):
        if captured is not None:
            captured.append({"to": to, "subject": subject, "html": html})
        return {"ok": True, "id": "re_fake"}

    monkeypatch.setattr(resend_client, "send_email", _fake)


def _spy_consent_capture(monkeypatch) -> list:
    """Espía `ConsentService.capture` sin alterar su comportamiento real.

    Devuelve la lista de kwargs con los que se llamó (vacía si nunca se
    invocó) — la forma fiable de verificar "no se creó la solicitud" dado
    que cada `ConsentService()` trae su propio repositorio en memoria (ver
    docstring del módulo).
    """
    calls: list = []
    original_capture = ConsentService.capture

    def _spy(self, *args, **kwargs):
        calls.append(kwargs)
        return original_capture(self, *args, **kwargs)

    monkeypatch.setattr(ConsentService, "capture", _spy)
    return calls


# ---------------------------------------------------------------------------
# 1-2: cerrar_venta exige email — sin email / con formato inválido.
# ---------------------------------------------------------------------------


class TestCerrarVentaExigeEmail:
    def test_sin_email_error_controlado_y_no_crea_solicitud(self, monkeypatch):
        sent: list = []
        _mock_send_email_ok(monkeypatch, sent)
        capture_calls = _spy_consent_capture(monkeypatch)

        ctx = _build_full_funnel_ctx("sesion-sin-email")
        result = execute_tool("cerrar_venta", {"consentimiento": True}, ctx)

        assert "error" in result
        assert "correo" in result["error"].lower()

        assert capture_calls == []
        assert sent == []

    def test_email_con_formato_invalido_error_controlado(self, monkeypatch):
        sent: list = []
        _mock_send_email_ok(monkeypatch, sent)
        capture_calls = _spy_consent_capture(monkeypatch)

        ctx = _build_full_funnel_ctx("sesion-email-invalido")
        result = execute_tool(
            "cerrar_venta",
            {"consentimiento": True, "email": "no-es-correo"},
            ctx,
        )

        assert "error" in result
        assert "correo" in result["error"].lower()

        assert capture_calls == []
        assert sent == []


# ---------------------------------------------------------------------------
# 3: email válido -> solicitud con email/handoff_token/insurer_name + correo.
# ---------------------------------------------------------------------------


class TestCerrarVentaConEmailValido:
    def test_email_valido_crea_solicitud_y_envia_correo_una_vez(
        self, monkeypatch
    ):
        captured: list = []
        _mock_send_email_ok(monkeypatch, captured)

        ctx = _build_full_funnel_ctx("sesion-email-valido")
        result = execute_tool(
            "cerrar_venta",
            {"consentimiento": True, "email": "cliente@example.com"},
            ctx,
        )

        assert "error" not in result
        assert result["state"] == "ready_for_payment"
        assert result["email"] == "cliente@example.com"
        assert result["insurer_name"] == "Seguros Bolívar"
        assert result.get("handoff_token")
        assert len(result["handoff_token"]) >= 40

        assert len(captured) == 1
        sent = captured[0]
        assert sent["to"] == "cliente@example.com"
        assert f"/aseguradora/{result['handoff_token']}" in sent["html"]


# ---------------------------------------------------------------------------
# 4-5: un fallo (o excepción) de Resend jamás rompe el cierre.
# ---------------------------------------------------------------------------


class TestFalloDeResendNoRompeElCierre:
    def test_send_email_ok_false_no_rompe_cierre_y_loguea(
        self, monkeypatch, caplog
    ):
        monkeypatch.setattr(
            resend_client,
            "send_email",
            lambda *a, **k: {"ok": False, "error": "status 500: boom"},
        )

        ctx = _build_full_funnel_ctx("sesion-resend-falla")
        with caplog.at_level(logging.ERROR):
            result = execute_tool(
                "cerrar_venta",
                {"consentimiento": True, "email": "cliente@example.com"},
                ctx,
            )

        assert "error" not in result
        assert result["state"] == "ready_for_payment"
        assert result.get("handoff_token")

        assert any(record.levelno >= logging.ERROR for record in caplog.records)

    def test_send_email_lanza_excepcion_no_rompe_cierre_y_loguea(
        self, monkeypatch, caplog
    ):
        def _boom(*args, **kwargs):
            raise RuntimeError("network exploded")

        monkeypatch.setattr(resend_client, "send_email", _boom)

        ctx = _build_full_funnel_ctx("sesion-resend-excepcion")
        with caplog.at_level(logging.ERROR):
            result = execute_tool(
                "cerrar_venta",
                {"consentimiento": True, "email": "cliente@example.com"},
                ctx,
            )

        assert "error" not in result
        assert result["state"] == "ready_for_payment"
        assert result.get("handoff_token")

        assert any(record.levelno >= logging.ERROR for record in caplog.records)


# ---------------------------------------------------------------------------
# 6: endpoint estructurado POST /{id}/consent — email opcional en el body.
# ---------------------------------------------------------------------------


def _seed_session_awaiting_consent() -> str:
    resp = client.post("/api/v1/conversations", json={})
    session_id = resp.json()["session_id"]
    client.post(
        f"/api/v1/conversations/{session_id}/profile",
        json=dict(FAVORABLE_ARGS),
    )
    client.post(f"/api/v1/conversations/{session_id}/accept")
    return session_id


class TestConsentEndpointConEmail:
    def test_con_email_en_body_envia_correo(self, monkeypatch):
        captured: list = []
        _mock_send_email_ok(monkeypatch, captured)

        session_id = _seed_session_awaiting_consent()

        response = client.post(
            f"/api/v1/conversations/{session_id}/consent",
            json={"consent_given": True, "email": "x@y.co"},
        )

        assert response.status_code == 200, response.text
        assert len(captured) == 1
        assert captured[0]["to"] == "x@y.co"

    def test_sin_email_en_body_no_envia_correo(self, monkeypatch):
        sent: list = []
        _mock_send_email_ok(monkeypatch, sent)

        session_id = _seed_session_awaiting_consent()

        response = client.post(
            f"/api/v1/conversations/{session_id}/consent",
            json={"consent_given": True},
        )

        assert response.status_code == 200, response.text
        assert sent == []


# ---------------------------------------------------------------------------
# 7: E2E guionizado — el bot pide el correo y cierra en el siguiente turno.
# ---------------------------------------------------------------------------


def _scripted_llm(replies: list[GeminiReply]):
    """Fábrica de un `generate_reply` guionado (sin red).

    Mismo patrón que `tests/test_e2e_orchestrator.py`.
    """

    calls: list[dict] = []

    def _generate_reply(contents, *, tools=None, system_instruction=None):
        calls.append(
            {
                "contents": contents,
                "tools": tools,
                "system_instruction": system_instruction,
            }
        )
        assert len(calls) <= len(replies), (
            "LLM script exhausted: more calls than scripted replies"
        )
        return replies[len(calls) - 1]

    _generate_reply.calls = calls
    return _generate_reply


def _create_session() -> str:
    response = client.post("/api/v1/conversations", json={})
    assert response.status_code == 201
    return response.json()["session_id"]


class TestE2EOrquestadorPideCorreoAntesDeCerrar:
    def test_bot_pide_correo_y_cierra_en_el_siguiente_turno(self, monkeypatch):
        captured: list = []
        _mock_send_email_ok(monkeypatch, captured)

        session_id = _create_session()

        script = [
            GeminiReply(
                kind="tool_call",
                tool_name="perfilar_cliente",
                tool_args=dict(FAVORABLE_ARGS),
                thought_signature="sig-1",
            ),
            GeminiReply(
                kind="text",
                text="¡Con gusto! ¿Cuánto te gustaría cotizar?",
            ),
            GeminiReply(
                kind="tool_call",
                tool_name="recomendar_seguro",
                tool_args={},
                thought_signature="sig-2",
            ),
            GeminiReply(
                kind="tool_call",
                tool_name="cotizar",
                tool_args={},
                thought_signature="sig-3",
            ),
            GeminiReply(
                kind="text",
                text="Tu prima mensual es la de la cotización",
            ),
            GeminiReply(
                kind="tool_call",
                tool_name="cerrar_venta",
                tool_args={"consentimiento": True},
                thought_signature="sig-4",
            ),
            GeminiReply(
                kind="text",
                text=(
                    "Para enviarte el link de cierre necesito tu correo, "
                    "¿me lo compartes?"
                ),
            ),
        ]
        llm = _scripted_llm(script)
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        turno_1 = client.post(
            f"/api/v1/conversations/{session_id}/message",
            json={"content": "hola, quiero cotizar mi hogar"},
        )
        assert turno_1.status_code == 200, turno_1.text

        turno_2 = client.post(
            f"/api/v1/conversations/{session_id}/message",
            json={"content": "listo, cuánto me costaría"},
        )
        assert turno_2.status_code == 200, turno_2.text

        turno_3 = client.post(
            f"/api/v1/conversations/{session_id}/message",
            json={"content": "sí, acepto, quiero cerrarlo"},
        )
        assert turno_3.status_code == 200, turno_3.text

        get_resp = client.get(f"/api/v1/conversations/{session_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()

        # El cierre NO ocurrió todavía: falta el correo.
        assert data["state"] == "quote_ready"
        assert data["application"] is None

        assistant_texts = [
            m["content"] for m in data["messages"] if m["role"] == "assistant"
        ]
        assert any("correo" in text.lower() for text in assistant_texts)
        assert captured == []

        script_2 = [
            GeminiReply(
                kind="tool_call",
                tool_name="cerrar_venta",
                tool_args={
                    "consentimiento": True,
                    "email": "cliente@example.com",
                },
                thought_signature="sig-5",
            ),
            GeminiReply(
                kind="text",
                text="¡Listo! Tu solicitud quedó lista para pago",
            ),
        ]
        llm_2 = _scripted_llm(script_2)
        monkeypatch.setattr(orchestrator, "generate_reply", llm_2)

        turno_4 = client.post(
            f"/api/v1/conversations/{session_id}/message",
            json={"content": "mi correo es cliente@example.com"},
        )
        assert turno_4.status_code == 200, turno_4.text

        get_resp_2 = client.get(f"/api/v1/conversations/{session_id}")
        assert get_resp_2.status_code == 200
        data_2 = get_resp_2.json()

        assert data_2["state"] == "ready_for_payment"
        assert data_2["application"] is not None
        assert data_2["application"]["email"] == "cliente@example.com"
        assert data_2["application"]["handoff_token"]

        assert len(captured) == 1
        assert captured[0]["to"] == "cliente@example.com"
