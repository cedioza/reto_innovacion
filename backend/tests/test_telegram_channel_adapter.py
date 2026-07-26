"""Tests del adaptador de canal Telegram (Fase 1, plan F5 — TDD-light, paso 1).

Este archivo se escribe ANTES de que exista `app.services.channels.telegram`
(rojo esperado: `ModuleNotFoundError` al recolectar este módulo). El paso 2
debe implementar el contrato exactamente como estos tests lo esperan, sobre
el mismo patrón que `app.services.channels.meta_whatsapp` /
`tests/test_meta_channel_adapter.py` (Fase 2, plan F1).

## Decisiones de estructura que el paso 2 debe respetar (para que estos tests
## puedan monkeypatchear sin tocar este archivo):

1. `app/services/channels/telegram.py` define `TelegramAdapter` con:
   - atributo de clase/instancia `channel = "telegram"`.
   - método `parse_incoming(payload: dict) -> InboundMessage | None`:
     lee `message.chat.id` con fallback a `message.from.id`; requiere
     también `message.text`; cualquier ausencia o payload basura devuelve
     `None` sin lanzar excepciones. El `user_ref` resultante es siempre
     `str(chat_id)` (aunque Telegram mande el id como entero).
   - método `deliver(user_ref: str, text: str) -> bool`: aplica
     `markdown_bold_to_whatsapp` (Telegram también solo reconoce un
     asterisco para negrita) y `split_text(text, 4096)`, enviando cada
     fragmento en orden vía `send_telegram_message(user_ref, chunk)`. Si un
     fragmento falla, reintenta ESE MISMO fragmento con
     `parse_mode=None` (texto plano, sin negritas) antes de darse por
     vencido; si el reintento también falla, `deliver` devuelve `False` y
     corta sin enviar el resto. Si todos los fragmentos (con o sin
     reintento) salen bien, devuelve `True`. Texto vacío no envía nada y
     devuelve `True`.
   El módulo importa la función de envío como símbolo propio, al estilo de
   `app.services.channels.meta_whatsapp`:
       `from app.services.telegram_client import send_telegram_message`
   de modo que se pueda monkeypatchear como
   `app.services.channels.telegram.send_telegram_message` (los tests de
   `TestDeliver` y el smoke de `TestWebhookTelegramPorGateway` dependen de
   este punto de parcheo exacto).

2. `app/services/telegram_client.py` (paso 2) le agrega a
   `send_telegram_message` un parámetro opcional
   `parse_mode: str | None = "Markdown"`: el valor por defecto conserva el
   comportamiento actual; `parse_mode=None` arma el payload SIN la clave
   `parse_mode` (para que Telegram no intente parsear Markdown roto en el
   reintento). Ese cambio de `telegram_client` no lo cubre este archivo
   (paso 1 solo toca el adaptador nuevo) — lo cubre `test_telegram_client.py`
   si existe, o el propio paso 2.

3. `app/api/routes/webhooks.py` (paso 2), en el POST `/telegram`:
   - crea una instancia módulo-level del adaptador:
       `_telegram_adapter = TelegramAdapter()`
   - dentro del mismo `try/except Exception: pass` ya existente (después de
     la validación del secret, que no cambia):
       `inbound = _telegram_adapter.parse_incoming(payload)`
       `if inbound is None: return {"status": "ok"}` (implícito: si no hay
       inbound, no se llama al gateway)
       `response = await run_in_threadpool(channel_gateway.handle, inbound.channel, inbound.user_ref, inbound.text)`
       `await run_in_threadpool(_telegram_adapter.deliver, inbound.user_ref, response)`
   - la validación del secret (`X-Telegram-Bot-Api-Secret-Token`) sigue
     ANTES del try, sin cambios.

Con esta estructura, los tests de `TestWebhookTelegramPorGateway` parchean:
- `app.api.routes.webhooks.channel_gateway.handle` (espía de orquestación).
- `app.services.channels.telegram.send_telegram_message` (espía de envío,
  ejercitado indirectamente a través de `_telegram_adapter.deliver`, que es
  real).

El archivo legacy `tests/test_telegram_webhook.py` (que hoy monkeypatchea
`webhooks._handler.handle_incoming` y `webhooks.send_telegram_message`) se
adapta en el paso 2 al recableado sobre `channel_gateway` + adaptador; aquí
solo se agrega un smoke equivalente sobre la estructura nueva.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.channels.base import InboundMessage
from app.services.channels.telegram import TelegramAdapter

client = TestClient(app)


def _telegram_payload(chat_id: int = 12345, text: str = "Hola") -> dict:
    return {
        "message": {
            "chat": {"id": chat_id},
            "from": {"id": chat_id},
            "text": text,
        }
    }


class TestParseIncoming:
    def test_message_with_chat_id_and_text_returns_inbound_message(self):
        adapter = TelegramAdapter()

        result = adapter.parse_incoming(_telegram_payload(chat_id=12345, text="Hola"))

        assert result == InboundMessage("telegram", "12345", "Hola")

    def test_user_ref_is_string_even_when_chat_id_is_numeric(self):
        adapter = TelegramAdapter()

        result = adapter.parse_incoming(_telegram_payload(chat_id=98765, text="Hola"))

        assert isinstance(result.user_ref, str)
        assert result.user_ref == "98765"

    def test_falls_back_to_from_id_when_chat_missing(self):
        adapter = TelegramAdapter()
        payload = {
            "message": {
                "from": {"id": 555},
                "text": "Hola sin chat",
            }
        }

        result = adapter.parse_incoming(payload)

        assert result == InboundMessage("telegram", "555", "Hola sin chat")

    def test_missing_text_returns_none(self):
        adapter = TelegramAdapter()
        payload = {"message": {"chat": {"id": 111}, "from": {"id": 111}}}

        assert adapter.parse_incoming(payload) is None

    def test_missing_chat_id_and_from_id_returns_none(self):
        adapter = TelegramAdapter()
        payload = {"message": {"text": "Hola sin remitente"}}

        assert adapter.parse_incoming(payload) is None

    def test_empty_payload_returns_none(self):
        adapter = TelegramAdapter()

        assert adapter.parse_incoming({}) is None

    def test_garbage_payload_returns_none_without_raising(self):
        adapter = TelegramAdapter()

        assert adapter.parse_incoming({"foo": "bar"}) is None

    def test_empty_message_returns_none(self):
        adapter = TelegramAdapter()

        assert adapter.parse_incoming({"message": {}}) is None


class _SendSpy:
    """Espía de `send_telegram_message`: graba cada llamada (con kwargs) y controla el resultado."""

    def __init__(self, results: list[bool] | None = None, default: bool = True):
        self.calls: list[tuple[str, str, dict]] = []
        self._results = list(results) if results is not None else None
        self._default = default

    def __call__(self, chat_id, text: str, **kwargs) -> bool:
        self.calls.append((chat_id, text, kwargs))
        if self._results is not None:
            return self._results.pop(0)
        return self._default


class TestDeliver:
    def test_long_text_is_split_into_ordered_chunks_within_limit(self, monkeypatch):
        spy = _SendSpy(default=True)
        monkeypatch.setattr(
            "app.services.channels.telegram.send_telegram_message", spy
        )
        adapter = TelegramAdapter()
        words = [f"palabra{i}" for i in range(1200)]
        long_text = " ".join(words)
        assert len(long_text) > 9000

        result = adapter.deliver("12345", long_text)

        assert result is True
        assert len(spy.calls) >= 3
        assert all(chat_id == "12345" for chat_id, _, _ in spy.calls)
        assert all(len(chunk) <= 4096 for _, chunk, _ in spy.calls)
        reconstructed = " ".join(chunk for _, chunk, _ in spy.calls)
        assert reconstructed == long_text

    def test_markdown_bold_is_translated_to_single_asterisk(self, monkeypatch):
        spy = _SendSpy(default=True)
        monkeypatch.setattr(
            "app.services.channels.telegram.send_telegram_message", spy
        )
        adapter = TelegramAdapter()

        result = adapter.deliver("54321", "Tu plan es **Plan Full**")

        assert result is True
        assert len(spy.calls) == 1
        chat_id, text, kwargs = spy.calls[0]
        assert (chat_id, text) == ("54321", "Tu plan es *Plan Full*")
        assert kwargs == {}

    def test_chunk_failure_retries_same_chunk_without_parse_mode(self, monkeypatch):
        spy = _SendSpy(results=[False, True])
        monkeypatch.setattr(
            "app.services.channels.telegram.send_telegram_message", spy
        )
        adapter = TelegramAdapter()

        result = adapter.deliver("111", "Hola **mundo**")

        assert result is True
        assert len(spy.calls) == 2
        first_chat_id, first_text, first_kwargs = spy.calls[0]
        second_chat_id, second_text, second_kwargs = spy.calls[1]
        assert first_chat_id == second_chat_id == "111"
        assert first_text == second_text == "Hola *mundo*"
        assert first_kwargs == {}
        assert second_kwargs == {"parse_mode": None}

    def test_retry_continues_with_remaining_chunks_after_recovering(self, monkeypatch):
        spy = _SendSpy(results=[False, True, True])
        monkeypatch.setattr(
            "app.services.channels.telegram.send_telegram_message", spy
        )
        adapter = TelegramAdapter()
        words = [f"palabra{i}" for i in range(600)]
        long_text = " ".join(words)

        result = adapter.deliver("222", long_text)

        assert result is True
        assert len(spy.calls) == 3

    def test_chunk_failure_and_retry_failure_stops_remaining_sends(self, monkeypatch):
        spy = _SendSpy(results=[False, False])
        monkeypatch.setattr(
            "app.services.channels.telegram.send_telegram_message", spy
        )
        adapter = TelegramAdapter()
        words = [f"palabra{i}" for i in range(1200)]
        long_text = " ".join(words)

        result = adapter.deliver("333", long_text)

        assert result is False
        assert len(spy.calls) == 2

    def test_normal_text_sends_once_and_returns_true(self, monkeypatch):
        spy = _SendSpy(default=True)
        monkeypatch.setattr(
            "app.services.channels.telegram.send_telegram_message", spy
        )
        adapter = TelegramAdapter()

        result = adapter.deliver("444", "Hola")

        assert result is True
        assert [(chat_id, text) for chat_id, text, _ in spy.calls] == [("444", "Hola")]

    def test_empty_text_returns_true_without_sending(self, monkeypatch):
        spy = _SendSpy(default=True)
        monkeypatch.setattr(
            "app.services.channels.telegram.send_telegram_message", spy
        )
        adapter = TelegramAdapter()

        result = adapter.deliver("555", "")

        assert result is True
        assert spy.calls == []


class TestWebhookTelegramPorGateway:
    """Smoke del recableado del POST /telegram sobre `channel_gateway` + adaptador.

    Puntos de parcheo (ver docstring del módulo): `webhooks.channel_gateway.handle`
    y `app.services.channels.telegram.send_telegram_message`.
    """

    def test_valid_update_calls_gateway_and_delivers_response(self, monkeypatch):
        import app.api.routes.webhooks as webhooks

        calls: list[tuple[str, str, str]] = []

        def fake_handle(channel: str, user_ref: str, text: str) -> str:
            calls.append((channel, user_ref, text))
            return "respuesta del agente"

        monkeypatch.setattr(webhooks.channel_gateway, "handle", fake_handle)

        send_spy = _SendSpy(default=True)
        monkeypatch.setattr(
            "app.services.channels.telegram.send_telegram_message", send_spy
        )

        response = client.post(
            "/api/v1/webhooks/telegram",
            json=_telegram_payload(chat_id=12345, text="Hola"),
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert calls == [("telegram", "12345", "Hola")]
        assert [(c, t) for c, t, _ in send_spy.calls] == [
            ("12345", "respuesta del agente")
        ]

    def test_garbage_payload_does_not_call_gateway(self, monkeypatch):
        import app.api.routes.webhooks as webhooks

        calls: list[tuple[str, str, str]] = []

        def fake_handle(channel: str, user_ref: str, text: str) -> str:
            calls.append((channel, user_ref, text))
            return "no debería llamarse"

        monkeypatch.setattr(webhooks.channel_gateway, "handle", fake_handle)

        response = client.post("/api/v1/webhooks/telegram", json={"message": {}})

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert calls == []

    def test_gateway_exception_is_swallowed_and_still_returns_ok(self, monkeypatch):
        import app.api.routes.webhooks as webhooks

        def failing_handle(channel: str, user_ref: str, text: str) -> str:
            raise RuntimeError("boom")

        monkeypatch.setattr(webhooks.channel_gateway, "handle", failing_handle)

        response = client.post(
            "/api/v1/webhooks/telegram",
            json=_telegram_payload(chat_id=12345, text="Hola"),
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_secret_configured_and_correct_header_calls_gateway(self, monkeypatch):
        import app.api.routes.webhooks as webhooks
        from app.core.config import settings

        monkeypatch.setattr(settings, "telegram_webhook_secret", "s3cret")
        calls: list[tuple[str, str, str]] = []

        def fake_handle(channel: str, user_ref: str, text: str) -> str:
            calls.append((channel, user_ref, text))
            return "respuesta"

        monkeypatch.setattr(webhooks.channel_gateway, "handle", fake_handle)
        monkeypatch.setattr(
            "app.services.channels.telegram.send_telegram_message",
            _SendSpy(default=True),
        )

        response = client.post(
            "/api/v1/webhooks/telegram",
            json=_telegram_payload(chat_id=42, text="hola"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"},
        )

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert calls == [("telegram", "42", "hola")]

    def test_secret_configured_missing_header_is_unauthorized(self, monkeypatch):
        import app.api.routes.webhooks as webhooks
        from app.core.config import settings

        monkeypatch.setattr(settings, "telegram_webhook_secret", "s3cret")
        calls: list[tuple[str, str, str]] = []
        monkeypatch.setattr(
            webhooks.channel_gateway,
            "handle",
            lambda channel, user_ref, text: calls.append((channel, user_ref, text)),
        )

        response = client.post(
            "/api/v1/webhooks/telegram",
            json=_telegram_payload(chat_id=42, text="hola"),
        )

        assert response.status_code == 401
        assert calls == []

    def test_secret_configured_incorrect_header_is_unauthorized(self, monkeypatch):
        import app.api.routes.webhooks as webhooks
        from app.core.config import settings

        monkeypatch.setattr(settings, "telegram_webhook_secret", "s3cret")
        calls: list[tuple[str, str, str]] = []
        monkeypatch.setattr(
            webhooks.channel_gateway,
            "handle",
            lambda channel, user_ref, text: calls.append((channel, user_ref, text)),
        )

        response = client.post(
            "/api/v1/webhooks/telegram",
            json=_telegram_payload(chat_id=42, text="hola"),
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        )

        assert response.status_code == 401
        assert calls == []
