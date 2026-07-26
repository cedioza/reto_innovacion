"""Tests del adaptador de canal WhatsApp/Meta (Fase 2, plan F1 — TDD-light, paso 1).

Este archivo se escribe ANTES de que exista `app.services.channels.meta_whatsapp`
(rojo esperado: `ModuleNotFoundError` al recolectar este módulo). El paso 2 debe
implementar el contrato exactamente como estos tests lo esperan.

## Decisiones de estructura que el paso 2 debe respetar (para que estos tests
## puedan monkeypatchear sin tocar este archivo):

1. `app/services/channels/meta_whatsapp.py` define `MetaWhatsAppAdapter` con:
   - atributo de clase/instancia `channel = "whatsapp"`.
   - método `parse_incoming(payload: dict) -> InboundMessage | None`.
   - método `deliver(user_ref: str, text: str) -> bool`.
   El módulo importa la función de envío como símbolo propio, al estilo de
   `app.services.whatsapp_client`:
       `from app.services.whatsapp_provider import send_whatsapp_message`
   de modo que se pueda monkeypatchear como
   `app.services.channels.meta_whatsapp.send_whatsapp_message` (los tests de
   `TestDeliver` y el smoke de `TestWebhookMetaPorGateway` dependen de este
   punto de parcheo exacto).

2. `app/api/routes/webhooks.py` (paso 2), en el POST `/whatsapp`:
   - importa el gateway como módulo, NO la función suelta:
       `from app.services import channel_gateway`
     así el test puede parchear `webhooks.channel_gateway.handle` sin
     reimportar nada.
   - crea una instancia módulo-level del adaptador:
       `_meta_adapter = MetaWhatsAppAdapter()`
   - el handler pasa a ser:
       `inbound = _meta_adapter.parse_incoming(payload)`
       `if inbound is None: return {"status": "ok"}`
       `response = channel_gateway.handle(inbound.channel, inbound.user_ref, inbound.text)`
       `_meta_adapter.deliver(inbound.user_ref, response)`
     todo envuelto en el mismo `try/except Exception: pass` ya existente, de
     modo que cualquier excepción (incluida una de `channel_gateway.handle`)
     siga devolviendo `{"status": "ok"}` con 200.
   - el GET de verificación y los webhooks de YCloud/Telegram no cambian.

Con esta estructura, los tests de `TestWebhookMetaPorGateway` parchean:
- `app.api.routes.webhooks.channel_gateway.handle` (espía de orquestación).
- `app.services.channels.meta_whatsapp.send_whatsapp_message` (espía de envío,
  ejercitado indirectamente a través de `_meta_adapter.deliver`, que es real).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.channels.base import InboundMessage
from app.services.channels.meta_whatsapp import MetaWhatsAppAdapter

client = TestClient(app)


def _text_payload(phone: str = "595123456789", text: str = "Hola") -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": phone,
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


def _interactive_payload(phone: str = "595123456789", title: str = "Ver planes") -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": phone,
                                    "type": "interactive",
                                    "interactive": {
                                        "button_reply": {"id": "btn-1", "title": title}
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


def _image_payload(phone: str = "595123456789") -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": phone,
                                    "type": "image",
                                    "image": {"id": "media-1"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


class TestParseIncoming:
    def test_text_message_returns_inbound_message(self):
        adapter = MetaWhatsAppAdapter()

        result = adapter.parse_incoming(_text_payload(phone="595111", text="Hola, quiero un seguro"))

        assert result == InboundMessage("whatsapp", "595111", "Hola, quiero un seguro")

    def test_interactive_button_reply_uses_title_as_text(self):
        adapter = MetaWhatsAppAdapter()

        result = adapter.parse_incoming(
            _interactive_payload(phone="595222", title="Cotizar auto")
        )

        assert result == InboundMessage("whatsapp", "595222", "Cotizar auto")

    def test_no_messages_returns_none(self):
        adapter = MetaWhatsAppAdapter()
        payload = {
            "entry": [{"changes": [{"value": {"messages": []}}]}]
        }

        assert adapter.parse_incoming(payload) is None

    def test_empty_payload_returns_none(self):
        adapter = MetaWhatsAppAdapter()

        assert adapter.parse_incoming({}) is None

    def test_empty_entry_list_returns_none(self):
        adapter = MetaWhatsAppAdapter()

        assert adapter.parse_incoming({"entry": []}) is None

    def test_empty_changes_list_returns_none(self):
        adapter = MetaWhatsAppAdapter()

        assert adapter.parse_incoming({"entry": [{"changes": []}]}) is None

    def test_missing_value_returns_none(self):
        adapter = MetaWhatsAppAdapter()

        assert adapter.parse_incoming({"entry": [{"changes": [{}]}]}) is None

    def test_unknown_message_type_without_text_returns_none(self):
        adapter = MetaWhatsAppAdapter()

        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {"from": "595333", "type": "reaction"}
                                ]
                            }
                        }
                    ]
                }
            ]
        }

        assert adapter.parse_incoming(payload) is None

    def test_image_message_without_text_returns_none(self):
        adapter = MetaWhatsAppAdapter()

        assert adapter.parse_incoming(_image_payload(phone="595444")) is None


class _SendSpy:
    """Espía de `send_whatsapp_message`: graba cada llamada y controla el resultado."""

    def __init__(self, results: list[bool] | None = None, default: bool = True):
        self.calls: list[tuple[str, str]] = []
        self._results = list(results) if results is not None else None
        self._default = default

    def __call__(self, to: str, text: str) -> bool:
        self.calls.append((to, text))
        if self._results is not None:
            return self._results.pop(0)
        return self._default


class TestDeliver:
    def test_long_text_is_split_into_ordered_chunks_within_limit(self, monkeypatch):
        spy = _SendSpy(default=True)
        monkeypatch.setattr(
            "app.services.channels.meta_whatsapp.send_whatsapp_message", spy
        )
        adapter = MetaWhatsAppAdapter()
        words = [f"palabra{i}" for i in range(1200)]
        long_text = " ".join(words)
        assert len(long_text) > 9000

        result = adapter.deliver("595555", long_text)

        assert result is True
        assert len(spy.calls) >= 3
        assert all(to == "595555" for to, _ in spy.calls)
        assert all(len(chunk) <= 4096 for _, chunk in spy.calls)
        reconstructed = " ".join(chunk for _, chunk in spy.calls)
        assert reconstructed == long_text

    def test_markdown_bold_is_translated_to_whatsapp_format(self, monkeypatch):
        spy = _SendSpy(default=True)
        monkeypatch.setattr(
            "app.services.channels.meta_whatsapp.send_whatsapp_message", spy
        )
        adapter = MetaWhatsAppAdapter()

        result = adapter.deliver("595666", "Tu plan es **Plan Full**")

        assert result is True
        assert spy.calls == [("595666", "Tu plan es *Plan Full*")]

    def test_first_chunk_failure_stops_remaining_sends(self, monkeypatch):
        spy = _SendSpy(results=[False])
        monkeypatch.setattr(
            "app.services.channels.meta_whatsapp.send_whatsapp_message", spy
        )
        adapter = MetaWhatsAppAdapter()
        words = [f"palabra{i}" for i in range(1200)]
        long_text = " ".join(words)

        result = adapter.deliver("595777", long_text)

        assert result is False
        assert len(spy.calls) == 1

    def test_normal_text_sends_once_and_returns_true(self, monkeypatch):
        spy = _SendSpy(default=True)
        monkeypatch.setattr(
            "app.services.channels.meta_whatsapp.send_whatsapp_message", spy
        )
        adapter = MetaWhatsAppAdapter()

        result = adapter.deliver("595888", "Hola")

        assert result is True
        assert spy.calls == [("595888", "Hola")]

    def test_empty_text_returns_true_without_sending(self, monkeypatch):
        spy = _SendSpy(default=True)
        monkeypatch.setattr(
            "app.services.channels.meta_whatsapp.send_whatsapp_message", spy
        )
        adapter = MetaWhatsAppAdapter()

        result = adapter.deliver("595999", "")

        assert result is True
        assert spy.calls == []


class TestWebhookMetaPorGateway:
    """Smoke del recableado del POST /whatsapp sobre `channel_gateway` + adaptador.

    Puntos de parcheo (ver docstring del módulo): `webhooks.channel_gateway.handle`
    y `app.services.channels.meta_whatsapp.send_whatsapp_message`.
    """

    def test_text_message_calls_gateway_and_delivers_response(self, monkeypatch):
        import app.api.routes.webhooks as webhooks

        calls: list[tuple[str, str, str]] = []

        def fake_handle(channel: str, user_ref: str, text: str) -> str:
            calls.append((channel, user_ref, text))
            return "respuesta del agente"

        monkeypatch.setattr(webhooks.channel_gateway, "handle", fake_handle)

        send_spy = _SendSpy(default=True)
        monkeypatch.setattr(
            "app.services.channels.meta_whatsapp.send_whatsapp_message", send_spy
        )

        response = client.post(
            "/api/v1/webhooks/whatsapp",
            json=_text_payload(phone="595123456789", text="Hola"),
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert calls == [("whatsapp", "595123456789", "Hola")]
        assert send_spy.calls == [("595123456789", "respuesta del agente")]

    def test_malformed_payload_does_not_call_gateway(self, monkeypatch):
        import app.api.routes.webhooks as webhooks

        calls: list[tuple[str, str, str]] = []

        def fake_handle(channel: str, user_ref: str, text: str) -> str:
            calls.append((channel, user_ref, text))
            return "no debería llamarse"

        monkeypatch.setattr(webhooks.channel_gateway, "handle", fake_handle)

        response = client.post("/api/v1/webhooks/whatsapp", json={"entry": []})

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert calls == []

    def test_gateway_exception_is_swallowed_and_still_returns_ok(self, monkeypatch):
        import app.api.routes.webhooks as webhooks

        def failing_handle(channel: str, user_ref: str, text: str) -> str:
            raise RuntimeError("boom")

        monkeypatch.setattr(webhooks.channel_gateway, "handle", failing_handle)

        response = client.post(
            "/api/v1/webhooks/whatsapp",
            json=_text_payload(phone="595123456789", text="Hola"),
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_verify_get_without_token_is_forbidden(self):
        response = client.get("/api/v1/webhooks/whatsapp")

        assert response.status_code == 403
