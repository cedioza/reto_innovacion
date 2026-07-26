"""Tests for the closing flow (consent + success cards) — TDD RED phase (Fase 1 de D4).

Cubre `.claude/analysis/plans/
20260725-d4-cierre-ui-resumen-consentimiento-exito.plan.md` (Fase 1):

- `ConversationService.accept_quote` agrega, además del texto actual, un
  mensaje-tarjeta `type="consent"` con el resumen de lo que el cliente va a
  aceptar (producto, prima, coberturas), tomado de `session.recommendation` /
  `session.quote`.
- `ConversationService.submit_consent` valida el formato del email (regex
  `^\\S+@\\S+\\.\\S+$`) ANTES de crear la solicitud: con email presente pero
  inválido, lanza `ValueError` y `ConsentService.capture` nunca se invoca (el
  endpoint estructurado responde 400 y no se envía correo). Tras un cierre
  exitoso, agrega a la sesión un texto de éxito (que menciona "revisa tu
  correo" solo si hay email, y jamás "contactaremos"/"contactanos") y un
  mensaje-tarjeta `type="application"` con
  `{product_name, monthly_premium, currency, insurer_name, email,
  consent_timestamp}` (sin `handoff_token`); `next_action` pasa a mencionar
  el correo/la aseguradora.
- El orquestador (`cerrar_venta` vía LLM guionizado) deja la sesión con un
  mensaje `type="application"` del mismo shape.
- `ChannelHandler`, en el flujo completo hasta el cierre, ya no responde con
  "contactaremos" ni "contactanos".

Ninguno de estos comportamientos existe todavía: es intencional que estos
tests fallen por ASERCIÓN (falta la tarjeta `consent`/`application`, el
`ValueError` no se lanza para email inválido, o el texto sigue diciendo
"contactaremos"/"contactanos") — nunca por `ImportError` ni por un fixture
roto.

El LLM se guioniza vía `monkeypatch` de `orchestrator.generate_reply`, mismo
patrón de `tests/test_card_messages.py` / `tests/test_handoff_flow.py`; el
envío de correo se mockea siempre vía `resend_client.send_email` (cero red
real), mismo patrón de `tests/test_handoff_flow.py`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.conversation import (
    ConversationCreate,
    ConversationState,
    ProfileData,
)
from app.services import handoff
from app.services.channel_handler import ChannelHandler
from app.services.conversation import ConversationService, conversation_service
from app.services.consent import ConsentService
from app.services.integrations import resend_client
from app.services.integrations.gemini_client import GeminiReply

import app.services.orchestrator as orchestrator

client = TestClient(app)


FAVORABLE_PROFILE = ProfileData(
    age_range="26-40", stratum=3, property_type="house", zone="urban"
)

FAVORABLE_ARGS = {
    "property_type": "house",
    "zone": "urban",
    "stratum": 3,
    "age_range": "26-40",
}


def _mock_send_email_ok(monkeypatch, captured: list | None = None):
    """Mockea `resend_client.send_email` para que nunca haga red real."""

    def _fake(to, subject, html):
        if captured is not None:
            captured.append({"to": to, "subject": subject, "html": html})
        return {"ok": True, "id": "re_fake"}

    monkeypatch.setattr(resend_client, "send_email", _fake)


def _spy_consent_capture(monkeypatch) -> list:
    """Espía `ConsentService.capture` sin alterar su comportamiento real."""
    calls: list = []
    original_capture = ConsentService.capture

    def _spy(self, *args, **kwargs):
        calls.append(kwargs)
        return original_capture(self, *args, **kwargs)

    monkeypatch.setattr(ConsentService, "capture", _spy)
    return calls


def _seed_awaiting_consent(service: ConversationService):
    """Perfila y acepta la cotización (motor real) hasta `AWAITING_CONSENT`."""
    session = service.create(ConversationCreate())
    session = service.update_profile(session.session_id, FAVORABLE_PROFILE)
    session = service.accept_quote(session.session_id)
    return session


def _scripted_llm(replies: list[GeminiReply]):
    """Fábrica de un `generate_reply` guionado (sin red), mismo patrón que
    `tests/test_card_messages.py`."""

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


# ==============================================================================
# 1) accept_quote -> tarjeta `consent` con el resumen de lo que se va a aceptar
# ==============================================================================


class TestAcceptQuoteConsentCard:
    def test_accept_quote_appends_consent_card_after_text_message(self) -> None:
        service = ConversationService()
        session = service.create(ConversationCreate())
        session = service.update_profile(session.session_id, FAVORABLE_PROFILE)

        recommendation = session.recommendation
        quote = session.quote
        assert recommendation is not None
        assert quote is not None

        updated = service.accept_quote(session.session_id)

        text_message, card_message = updated.messages[-2], updated.messages[-1]
        assert text_message.type == "text"

        assert card_message.role == "assistant"
        assert card_message.type == "consent"
        assert card_message.content

        payload = card_message.payload
        assert payload is not None
        assert payload["product_id"] == recommendation.product_id
        assert payload["product_name"] == recommendation.product_name
        assert payload["monthly_premium"] == quote.monthly_premium
        assert payload["annual_premium"] == quote.annual_premium
        assert payload["currency"] == quote.currency
        assert payload["coverage_details"] == quote.coverage_details


# ==============================================================================
# 2) submit_consent -> email presente pero con formato inválido: ValueError
#    ANTES de crear la solicitud, sin tocar el estado ni enviar correo.
# ==============================================================================


class TestSubmitConsentInvalidEmailFormat:
    def test_invalid_email_format_raises_before_creating_application(
        self, monkeypatch
    ) -> None:
        sent: list = []
        _mock_send_email_ok(monkeypatch, sent)
        capture_calls = _spy_consent_capture(monkeypatch)

        service = ConversationService()
        session = _seed_awaiting_consent(service)

        with pytest.raises(ValueError):
            service.submit_consent(session.session_id, True, email="no-es-correo")

        assert capture_calls == []
        assert sent == []

        # El estado no debe haber avanzado: el consentimiento inválido no
        # cierra la venta.
        untouched = service.get(session.session_id)
        assert untouched is not None
        assert untouched.state == ConversationState.AWAITING_CONSENT

    def test_endpoint_returns_400_and_does_not_send_email(self, monkeypatch) -> None:
        sent: list = []
        _mock_send_email_ok(monkeypatch, sent)

        create_resp = client.post("/api/v1/conversations", json={})
        session_id = create_resp.json()["session_id"]
        client.post(
            f"/api/v1/conversations/{session_id}/profile",
            json=dict(FAVORABLE_ARGS),
        )
        client.post(f"/api/v1/conversations/{session_id}/accept")

        response = client.post(
            f"/api/v1/conversations/{session_id}/consent",
            json={"consent_given": True, "email": "not-an-email"},
        )

        assert response.status_code == 400
        assert sent == []


# ==============================================================================
# 3) submit_consent -> email válido: texto de éxito + tarjeta `application`
#    (sin handoff_token), next_action menciona correo/aseguradora.
# ==============================================================================


class TestSubmitConsentValidEmail:
    def test_success_text_mentions_email_and_never_contactaremos(
        self, monkeypatch
    ) -> None:
        sent: list = []
        _mock_send_email_ok(monkeypatch, sent)

        service = ConversationService()
        session = _seed_awaiting_consent(service)
        recommendation = session.recommendation
        quote = session.quote
        assert recommendation is not None
        assert quote is not None

        service.submit_consent(session.session_id, True, email="cliente@example.com")

        updated = service.get(session.session_id)
        assert updated is not None
        assert updated.state == ConversationState.READY_FOR_PAYMENT

        text_message, card_message = updated.messages[-2], updated.messages[-1]

        assert text_message.type == "text"
        lowered = text_message.content.lower()
        assert "revisa tu correo" in lowered
        assert "contactaremos" not in lowered
        assert "contactanos" not in lowered

        assert card_message.type == "application"
        payload = card_message.payload
        assert payload is not None
        assert "handoff_token" not in payload
        assert payload["product_name"] == recommendation.product_name
        assert payload["monthly_premium"] == quote.monthly_premium
        assert payload["currency"] == quote.currency
        assert payload["insurer_name"] == handoff.insurer_for(
            recommendation.product_id
        )
        assert payload["email"] == "cliente@example.com"
        assert payload["consent_timestamp"]

        next_action_lower = updated.next_action.lower()
        assert "correo" in next_action_lower
        assert "aseguradora" in next_action_lower

        assert len(sent) == 1
        assert sent[0]["to"] == "cliente@example.com"


class TestSubmitConsentNoEmail:
    def test_closes_without_email_and_does_not_promise_email(
        self, monkeypatch
    ) -> None:
        sent: list = []
        _mock_send_email_ok(monkeypatch, sent)

        service = ConversationService()
        session = _seed_awaiting_consent(service)

        service.submit_consent(session.session_id, True, email=None)

        updated = service.get(session.session_id)
        assert updated is not None
        assert updated.state == ConversationState.READY_FOR_PAYMENT

        text_message, card_message = updated.messages[-2], updated.messages[-1]

        assert text_message.type == "text"
        lowered = text_message.content.lower()
        assert "revisa tu correo" not in lowered
        assert "contactaremos" not in lowered
        assert "contactanos" not in lowered

        assert card_message.type == "application"
        payload = card_message.payload
        assert payload is not None
        assert payload["email"] is None
        assert "handoff_token" not in payload

        assert sent == []


# ==============================================================================
# 4) Orquestador: cerrar_venta corre OK -> mensaje `application` en la sesión
# ==============================================================================


class TestOrchestratorClosingCard:
    def test_cerrar_venta_success_leaves_application_card(self, monkeypatch) -> None:
        sid = conversation_service.create(ConversationCreate()).session_id

        sent: list = []
        _mock_send_email_ok(monkeypatch, sent)

        llm = _scripted_llm(
            [
                GeminiReply(
                    kind="tool_call",
                    tool_name="perfilar_cliente",
                    tool_args=dict(FAVORABLE_ARGS),
                ),
                GeminiReply(
                    kind="tool_call", tool_name="recomendar_seguro", tool_args={}
                ),
                GeminiReply(kind="tool_call", tool_name="cotizar", tool_args={}),
                GeminiReply(
                    kind="tool_call",
                    tool_name="cerrar_venta",
                    tool_args={
                        "consentimiento": True,
                        "email": "cliente@example.com",
                    },
                ),
                GeminiReply(
                    kind="text",
                    text="¡Listo! Tu solicitud quedó lista para pago.",
                ),
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "quiero cerrar ya, mi correo es cliente@example.com")

        assert result is not None
        application_cards = [m for m in result.messages if m.type == "application"]
        assert len(application_cards) == 1

        payload = application_cards[0].payload
        assert payload is not None
        assert "handoff_token" not in payload
        assert payload["email"] == "cliente@example.com"
        assert payload["insurer_name"] == handoff.insurer_for("hogar-estandar")
        assert payload["monthly_premium"] is not None
        assert payload["currency"] == "COP"
        assert payload["consent_timestamp"]


# ==============================================================================
# 5) ChannelHandler: flujo completo hasta el cierre sin "contactaremos"
# ==============================================================================


class TestChannelHandlerClosingText:
    def test_full_flow_final_response_has_no_contactaremos_or_contactanos(
        self, monkeypatch
    ) -> None:
        sent: list = []
        _mock_send_email_ok(monkeypatch, sent)

        handler = ChannelHandler()
        user_id = "closing-cards-channel-user"

        handler.handle_incoming("whatsapp", user_id, "hola")
        handler.handle_incoming(
            "whatsapp",
            user_id,
            "30-40, 3, casa, urbana, si, 200000000, si, si, no",
        )
        handler.handle_incoming("whatsapp", user_id, "acepto")
        final_response = handler.handle_incoming("whatsapp", user_id, "consiento")

        lowered = final_response.lower()
        assert "contactaremos" not in lowered
        assert "contactanos" not in lowered
