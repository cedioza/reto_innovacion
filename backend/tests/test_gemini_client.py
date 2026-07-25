"""Tests del cliente de bajo nivel para Gemini (`generate_reply` + helpers).

Fase 1 del plan: solo texto (nada de tools/audio todavía). El módulo bajo
prueba (`app.services.integrations.gemini_client`) no existe aún, así que
estos tests deben fallar con ModuleNotFoundError/ImportError hasta que se
implemente en la siguiente tarea. Eso es intencional (TDD-light).
"""

import base64

import httpx

from app.core.config import settings
from app.services.integrations import gemini_client

_SUCCESS_JSON = {"candidates": [{"content": {"parts": [{"text": "¡Hola!"}]}}]}


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "", json_data: dict | None = None) -> None:
        self.status_code = status_code
        self.text = text
        self.is_success = 200 <= status_code < 300
        self._json_data = json_data

    def json(self):
        if self._json_data is None:
            raise ValueError("respuesta fake sin cuerpo json")
        return self._json_data


class _ScriptedClient:
    """Sustituto de httpx.Client con un guion de respuestas/excepciones.

    `behaviors` y `calls` son listas compartidas entre instancias (la fábrica
    que se le pasa a `monkeypatch.setattr(..., "Client", ...)` puede crear un
    `_ScriptedClient` nuevo en cada llamada, típico si el cliente real se usa
    con `with httpx.Client(...) as client:` dentro de un loop de reintento);
    así el conteo de llamadas y el consumo del guion funcionan sin importar
    si el módulo bajo prueba reutiliza un único cliente o crea uno por intento.
    """

    def __init__(self, behaviors: list, calls: list, captured: list | None = None) -> None:
        self._behaviors = behaviors
        self._calls = calls
        self._captured = captured

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, *args, **kwargs):
        self._calls.append(1)
        if self._captured is not None:
            self._captured.append({"args": args, "kwargs": kwargs})
        behavior = self._behaviors.pop(0)
        if isinstance(behavior, Exception):
            raise behavior
        return behavior


def _patch_client(monkeypatch, behaviors: list, calls: list, captured: list | None = None) -> None:
    monkeypatch.setattr(
        gemini_client.httpx,
        "Client",
        lambda *a, **k: _ScriptedClient(behaviors, calls, captured),
    )


# --- Helpers puros (text_part / user_message / model_message) ---


def test_text_part_builds_text_dict():
    assert gemini_client.text_part("hola") == {"text": "hola"}


def test_user_message_wraps_role_and_parts():
    parts = [gemini_client.text_part("a"), gemini_client.text_part("b")]
    assert gemini_client.user_message(*parts) == {"role": "user", "parts": parts}


def test_model_message_wraps_role_and_parts():
    part = gemini_client.text_part("respuesta")
    assert gemini_client.model_message(part) == {"role": "model", "parts": [part]}


# --- generate_reply: caso feliz ---


def test_generate_reply_success_returns_text(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    calls: list = []
    _patch_client(monkeypatch, [_FakeResponse(200, json_data=_SUCCESS_JSON)], calls)

    reply = gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("hola"))]
    )

    assert reply.kind == "text"
    assert reply.text == "¡Hola!"
    assert len(calls) == 1


def test_generate_reply_concatenates_text_parts_and_tolerates_extra_keys(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    json_data = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Hola "},
                        {"text": "mundo", "thoughtSignature": "abc123"},
                    ]
                }
            }
        ]
    }
    calls: list = []
    _patch_client(monkeypatch, [_FakeResponse(200, json_data=json_data)], calls)

    reply = gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("hola"))]
    )

    assert reply.kind == "text"
    assert reply.text == "Hola mundo"
    assert len(calls) == 1


# --- generate_reply: system_instruction en el payload ---


def test_generate_reply_includes_system_instruction_when_given(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    calls: list = []
    captured: list = []
    _patch_client(monkeypatch, [_FakeResponse(200, json_data=_SUCCESS_JSON)], calls, captured)

    gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("hola"))],
        system_instruction="Eres un asistente útil.",
    )

    assert len(captured) == 1
    sent_payload = captured[0]["kwargs"]["json"]
    assert sent_payload["systemInstruction"] == {
        "parts": [{"text": "Eres un asistente útil."}]
    }


def test_generate_reply_omits_system_instruction_when_not_given(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    calls: list = []
    captured: list = []
    _patch_client(monkeypatch, [_FakeResponse(200, json_data=_SUCCESS_JSON)], calls, captured)

    gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("hola"))]
    )

    assert len(captured) == 1
    sent_payload = captured[0]["kwargs"]["json"]
    assert "systemInstruction" not in sent_payload


# --- generate_reply: fallos de red / reintentos ---


def test_generate_reply_returns_fallback_after_persistent_network_error(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    calls: list = []
    _patch_client(
        monkeypatch,
        [httpx.ConnectError("boom"), httpx.ConnectError("boom")],
        calls,
    )

    reply = gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("hola"))]
    )

    assert reply.kind == "error"
    assert reply.text == gemini_client.FALLBACK_MESSAGE
    assert len(calls) == 2


def test_generate_reply_retries_once_after_network_error_then_succeeds(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    calls: list = []
    _patch_client(
        monkeypatch,
        [httpx.ConnectError("boom"), _FakeResponse(200, json_data=_SUCCESS_JSON)],
        calls,
    )

    reply = gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("hola"))]
    )

    assert reply.kind == "text"
    assert reply.text == "¡Hola!"
    assert len(calls) == 2


def test_generate_reply_returns_fallback_after_persistent_server_error(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    calls: list = []
    _patch_client(
        monkeypatch,
        [
            _FakeResponse(500, text="internal error"),
            _FakeResponse(500, text="internal error"),
        ],
        calls,
    )

    reply = gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("hola"))]
    )

    assert reply.kind == "error"
    assert reply.text == gemini_client.FALLBACK_MESSAGE
    assert len(calls) == 2


def test_generate_reply_status_401_does_not_retry_and_hides_api_key(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "super-secret-key")
    calls: list = []
    _patch_client(monkeypatch, [_FakeResponse(401, text="unauthorized")], calls)

    reply = gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("hola"))]
    )

    assert reply.kind == "error"
    assert len(calls) == 1
    assert "super-secret-key" not in reply.text


def _rate_limit_response(retry_delay: str | None = None) -> _FakeResponse:
    body: dict = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED"}}
    if retry_delay is not None:
        body["error"]["details"] = [
            {
                "@type": "type.googleapis.com/google.rpc.RetryInfo",
                "retryDelay": retry_delay,
            }
        ]
    return _FakeResponse(429, text="rate limited", json_data=body)


def test_generate_reply_retries_after_rate_limit_then_succeeds(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    sleeps: list = []
    monkeypatch.setattr(gemini_client, "_sleep", lambda seconds: sleeps.append(seconds))
    calls: list = []
    _patch_client(
        monkeypatch,
        [_rate_limit_response(), _FakeResponse(200, json_data=_SUCCESS_JSON)],
        calls,
    )

    reply = gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("hola"))]
    )

    assert reply.kind == "text"
    assert reply.text == "¡Hola!"
    assert len(calls) == 2
    assert sleeps == [2.0]


def test_generate_reply_retries_rate_limit_twice_then_succeeds(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    sleeps: list = []
    monkeypatch.setattr(gemini_client, "_sleep", lambda seconds: sleeps.append(seconds))
    calls: list = []
    _patch_client(
        monkeypatch,
        [
            _rate_limit_response(),
            _rate_limit_response(),
            _FakeResponse(200, json_data=_SUCCESS_JSON),
        ],
        calls,
    )

    reply = gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("hola"))]
    )

    assert reply.kind == "text"
    assert len(calls) == 3
    assert sleeps == [2.0, 4.0]


def test_generate_reply_returns_fallback_after_exhausting_rate_limit_retries(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(gemini_client, "_sleep", lambda seconds: None)
    calls: list = []
    _patch_client(
        monkeypatch,
        [_rate_limit_response(), _rate_limit_response(), _rate_limit_response()],
        calls,
    )

    reply = gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("hola"))]
    )

    assert reply.kind == "error"
    assert reply.text == gemini_client.FALLBACK_MESSAGE
    assert len(calls) == 3


def test_generate_reply_uses_retry_delay_from_body_capped(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    sleeps: list = []
    monkeypatch.setattr(gemini_client, "_sleep", lambda seconds: sleeps.append(seconds))
    calls: list = []
    _patch_client(
        monkeypatch,
        [_rate_limit_response(retry_delay="30s"), _FakeResponse(200, json_data=_SUCCESS_JSON)],
        calls,
    )

    reply = gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("hola"))]
    )

    assert reply.kind == "text"
    assert sleeps == [gemini_client.MAX_RATE_LIMIT_DELAY_SECONDS]


def test_generate_reply_without_api_key_makes_no_http_calls(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(
        gemini_client.httpx,
        "Client",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("no debería llamar a httpx.Client sin API key")
        ),
    )

    reply = gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("hola"))]
    )

    assert reply.kind == "error"


# --- generate_reply: function calling (Fase 2 del plan) ---

_COTIZAR_DECLARATION = {
    "name": "cotizar",
    "description": "Cotiza un producto de seguros.",
    "parameters": {
        "type": "object",
        "properties": {"producto": {"type": "string"}},
    },
}

_TOOL_CALL_JSON = {
    "candidates": [
        {
            "content": {
                "parts": [
                    {"functionCall": {"name": "cotizar", "args": {"producto": "hogar"}}}
                ]
            }
        }
    ]
}


def test_generate_reply_includes_tools_in_payload_when_given(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    calls: list = []
    captured: list = []
    _patch_client(monkeypatch, [_FakeResponse(200, json_data=_SUCCESS_JSON)], calls, captured)

    gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("hola"))],
        tools=[_COTIZAR_DECLARATION],
    )

    assert len(captured) == 1
    sent_payload = captured[0]["kwargs"]["json"]
    assert sent_payload["tools"] == [{"functionDeclarations": [_COTIZAR_DECLARATION]}]


def test_generate_reply_omits_tools_when_not_given(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    calls: list = []
    captured: list = []
    _patch_client(monkeypatch, [_FakeResponse(200, json_data=_SUCCESS_JSON)], calls, captured)

    gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("hola"))]
    )

    assert len(captured) == 1
    sent_payload = captured[0]["kwargs"]["json"]
    assert "tools" not in sent_payload


def test_generate_reply_parses_function_call_as_tool_call(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    calls: list = []
    _patch_client(monkeypatch, [_FakeResponse(200, json_data=_TOOL_CALL_JSON)], calls)

    reply = gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("cotiza un seguro de hogar"))],
        tools=[_COTIZAR_DECLARATION],
    )

    assert reply.kind == "tool_call"
    assert reply.tool_name == "cotizar"
    assert reply.tool_args == {"producto": "hogar"}


def test_generate_reply_function_call_wins_over_text_part(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    json_data = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Voy a cotizar eso por ti."},
                        {"functionCall": {"name": "cotizar", "args": {"producto": "hogar"}}},
                    ]
                }
            }
        ]
    }
    calls: list = []
    _patch_client(monkeypatch, [_FakeResponse(200, json_data=json_data)], calls)

    reply = gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("cotiza un seguro de hogar"))],
        tools=[_COTIZAR_DECLARATION],
    )

    assert reply.kind == "tool_call"
    assert reply.tool_name == "cotizar"


def test_generate_reply_function_call_without_args_returns_empty_dict(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    json_data = {
        "candidates": [
            {"content": {"parts": [{"functionCall": {"name": "cotizar"}}]}}
        ]
    }
    calls: list = []
    _patch_client(monkeypatch, [_FakeResponse(200, json_data=json_data)], calls)

    reply = gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("cotiza algo"))],
        tools=[_COTIZAR_DECLARATION],
    )

    assert reply.kind == "tool_call"
    assert reply.tool_name == "cotizar"
    assert reply.tool_args == {}


def test_generate_reply_parses_function_call_with_thought_signature(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    json_data = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "functionCall": {
                                "name": "cotizar",
                                "args": {"producto": "hogar"},
                            },
                            "thoughtSignature": "firma-xyz",
                        }
                    ]
                }
            }
        ]
    }
    calls: list = []
    _patch_client(monkeypatch, [_FakeResponse(200, json_data=json_data)], calls)

    reply = gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("cotiza un seguro de hogar"))],
        tools=[_COTIZAR_DECLARATION],
    )

    assert reply.kind == "tool_call"
    assert reply.thought_signature == "firma-xyz"


def test_generate_reply_function_call_without_thought_signature_defaults_empty(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    calls: list = []
    _patch_client(monkeypatch, [_FakeResponse(200, json_data=_TOOL_CALL_JSON)], calls)

    reply = gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("cotiza un seguro de hogar"))],
        tools=[_COTIZAR_DECLARATION],
    )

    assert reply.thought_signature == ""


def test_generate_reply_with_tools_declared_but_text_response_returns_text(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    calls: list = []
    _patch_client(monkeypatch, [_FakeResponse(200, json_data=_SUCCESS_JSON)], calls)

    reply = gemini_client.generate_reply(
        [gemini_client.user_message(gemini_client.text_part("hola"))],
        tools=[_COTIZAR_DECLARATION],
    )

    assert reply.kind == "text"
    assert reply.text == "¡Hola!"


# --- audio multimodal (Fase 3 del plan) ---


def test_audio_part_builds_inline_data_dict_with_default_mime_type():
    raw_bytes = b"fake-ogg-bytes"

    part = gemini_client.audio_part(raw_bytes)

    assert part == {
        "inline_data": {
            "mime_type": "audio/ogg",
            "data": base64.b64encode(raw_bytes).decode(),
        }
    }


def test_audio_part_respects_custom_mime_type():
    part = gemini_client.audio_part(b"x", mime_type="audio/mpeg")

    assert part["inline_data"]["mime_type"] == "audio/mpeg"


def test_generate_reply_with_audio_part_sends_inline_data_and_returns_text(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    calls: list = []
    captured: list = []
    json_data = {"candidates": [{"content": {"parts": [{"text": "dice hola"}]}}]}
    _patch_client(monkeypatch, [_FakeResponse(200, json_data=json_data)], calls, captured)

    reply = gemini_client.generate_reply(
        [
            gemini_client.user_message(
                gemini_client.audio_part(b"abc"),
                gemini_client.text_part("¿qué dice el audio?"),
            )
        ]
    )

    assert len(captured) == 1
    sent_payload = captured[0]["kwargs"]["json"]
    sent_parts = sent_payload["contents"][0]["parts"]
    assert {
        "inline_data": {
            "mime_type": "audio/ogg",
            "data": base64.b64encode(b"abc").decode(),
        }
    } in sent_parts
    assert {"text": "¿qué dice el audio?"} in sent_parts

    assert reply.kind == "text"
    assert reply.text == "dice hola"


# --- historial de tool-use (Fase 1 del plan A3) ---


def test_function_call_part_builds_function_call_dict():
    part = gemini_client.function_call_part("cotizar", {"producto": "hogar"})

    assert part == {
        "functionCall": {"name": "cotizar", "args": {"producto": "hogar"}}
    }


def test_function_call_part_includes_thought_signature_when_given():
    part = gemini_client.function_call_part("x", {}, "firma123")

    assert part == {
        "functionCall": {"name": "x", "args": {}},
        "thoughtSignature": "firma123",
    }


def test_function_call_part_omits_thought_signature_when_empty():
    part = gemini_client.function_call_part("x", {}, "")

    assert "thoughtSignature" not in part


def test_function_response_part_builds_function_response_dict():
    part = gemini_client.function_response_part(
        "cotizar", {"monthly_premium": 12345.0}
    )

    assert part == {
        "functionResponse": {
            "name": "cotizar",
            "response": {"monthly_premium": 12345.0},
        }
    }


def test_generate_reply_sends_two_turn_tool_use_history_intact(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    calls: list = []
    captured: list = []
    json_data = {"candidates": [{"content": {"parts": [{"text": "Listo, tu cotización es 99."}]}}]}
    _patch_client(monkeypatch, [_FakeResponse(200, json_data=json_data)], calls, captured)

    contents = [
        gemini_client.user_message(gemini_client.text_part("cotiza mi casa")),
        gemini_client.model_message(
            gemini_client.function_call_part("cotizar", {})
        ),
        gemini_client.user_message(
            gemini_client.function_response_part(
                "cotizar", {"monthly_premium": 99.0}
            )
        ),
    ]

    reply = gemini_client.generate_reply(contents)

    assert len(captured) == 1
    sent_payload = captured[0]["kwargs"]["json"]
    assert sent_payload["contents"] == contents

    assert reply.kind == "text"
