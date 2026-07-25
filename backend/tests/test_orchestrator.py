"""Tests for the LLM conversation orchestrator — TDD RED phase.

Covers Fase 2 of the A3 plan (`.claude/analysis/plans/
20260725-a3-orquestador-conversacional-llm.plan.md`): `app/services/
orchestrator.py`, the service that runs the loop `generate_reply` (Gemini) +
`execute_tool` (agent tools) + `conversation_service` (session persistence).

`app.services.orchestrator` does not exist yet — every test here is expected
to fail with a ModuleNotFoundError/ImportError until Fase 2 implements it.
The LLM is always scripted via `monkeypatch` of `orchestrator.generate_reply`
(no network).
"""

from __future__ import annotations

from app.schemas.conversation import ConversationCreate, ConversationState, ProfileData
from app.services.conversation import conversation_service
from app.services.integrations.gemini_client import FALLBACK_MESSAGE, GeminiReply
from app.services.quote import QuoteService

import app.services.orchestrator as orchestrator


# -- helpers -----------------------------------------------------------------


def _scripted_llm(replies: list[GeminiReply]):
    """Fábrica de un `generate_reply` guionado.

    Devuelve una función con la firma de
    `generate_reply(contents, *, tools=None, system_instruction=None)` que
    responde con `replies` en orden y registra cada llamada (contents/tools/
    system_instruction) en `.calls`, accesible desde el test. Si el guion se
    agota (más llamadas que replies disponibles), falla con AssertionError.
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


def _new_session():
    session = conversation_service.create(ConversationCreate())
    return session.session_id


def _find_function_response(contents, name: str) -> dict | None:
    """Busca en `contents` una part `functionResponse` con el `name` dado."""
    for message in contents:
        for part in message.get("parts", []):
            function_response = part.get("functionResponse")
            if function_response and function_response.get("name") == name:
                return function_response
    return None


def _find_function_call_part(contents, name: str) -> dict | None:
    """Busca en `contents` una part `functionCall` con el `name` dado."""
    for message in contents:
        for part in message.get("parts", []):
            function_call = part.get("functionCall")
            if function_call and function_call.get("name") == name:
                return part
    return None


FAVORABLE_ARGS = {
    "property_type": "house",
    "zone": "urban",
    "stratum": 3,
    "age_range": "26-40",
}

FAVORABLE_PROFILE = ProfileData(
    age_range="26-40", stratum=3, property_type="house", zone="urban"
)


# -- tests ---------------------------------------------------------------


class TestRespondDirectText:
    def test_text_reply_appends_user_and_assistant_messages(self, monkeypatch) -> None:
        sid = _new_session()
        llm = _scripted_llm(
            [GeminiReply(kind="text", text="¡Hola! ¿En qué te ayudo?")]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "hola")

        assert result is not None
        assert len(llm.calls) == 1

        last_two = result.messages[-2:]
        assert last_two[0].role == "user"
        assert last_two[0].content == "hola"
        assert last_two[1].role == "assistant"
        assert last_two[1].content == "¡Hola! ¿En qué te ayudo?"

        call = llm.calls[0]
        assert call["tools"]
        assert call["system_instruction"]


class TestRespondSingleTool:
    def test_tool_call_updates_profile_and_reports_function_response(
        self, monkeypatch
    ) -> None:
        sid = _new_session()
        llm = _scripted_llm(
            [
                GeminiReply(
                    kind="tool_call",
                    tool_name="perfilar_cliente",
                    tool_args=dict(FAVORABLE_ARGS),
                ),
                GeminiReply(kind="text", text="Ya te tengo perfilado"),
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "vivo en casa propia, estrato 3")

        assert result is not None
        assert result.profile is not None
        assert result.profile.stratum == 3
        assert len(llm.calls) == 2

        second_call_contents = llm.calls[1]["contents"]
        function_response = _find_function_response(
            second_call_contents, "perfilar_cliente"
        )
        assert function_response is not None

    def test_tool_call_replays_thought_signature_in_next_call_history(
        self, monkeypatch
    ) -> None:
        sid = _new_session()
        llm = _scripted_llm(
            [
                GeminiReply(
                    kind="tool_call",
                    tool_name="perfilar_cliente",
                    tool_args=dict(FAVORABLE_ARGS),
                    thought_signature="sig-abc",
                ),
                GeminiReply(kind="text", text="Ya te tengo perfilado"),
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        orchestrator.respond(sid, "vivo en casa propia, estrato 3")

        second_call_contents = llm.calls[1]["contents"]
        function_call_part = _find_function_call_part(
            second_call_contents, "perfilar_cliente"
        )
        assert function_call_part is not None
        assert function_call_part["thoughtSignature"] == "sig-abc"


class TestRespondChainToQuote:
    def test_chain_perfilar_cotizar_matches_quote_engine_exactly(
        self, monkeypatch
    ) -> None:
        sid = _new_session()
        llm = _scripted_llm(
            [
                GeminiReply(
                    kind="tool_call",
                    tool_name="perfilar_cliente",
                    tool_args=dict(FAVORABLE_ARGS),
                ),
                GeminiReply(kind="tool_call", tool_name="cotizar", tool_args={}),
                GeminiReply(kind="text", text="Tu prima mensual es la cotizada"),
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "quiero cotizar mi casa")

        assert result is not None
        assert result.quote is not None

        expected_premium = QuoteService().calculate_quote(FAVORABLE_PROFILE)[
            "monthly_premium"
        ]
        assert result.quote.monthly_premium == expected_premium
        assert result.state == ConversationState.QUOTE_READY
        assert len(llm.calls) == 3


class TestRespondHallucinatedTool:
    def test_unknown_tool_name_does_not_raise_and_reports_error(
        self, monkeypatch
    ) -> None:
        sid = _new_session()
        llm = _scripted_llm(
            [
                GeminiReply(kind="tool_call", tool_name="tool_fantasma", tool_args={}),
                GeminiReply(kind="text", text="perdón, sigamos"),
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "hazme algo raro")

        assert result is not None
        assert len(llm.calls) == 2

        second_call_contents = llm.calls[1]["contents"]
        function_response = _find_function_response(
            second_call_contents, "tool_fantasma"
        )
        assert function_response is not None
        assert "error" in function_response.get("response", {})


class TestRespondLlmDown:
    def test_error_reply_yields_fallback_message_without_raising(
        self, monkeypatch
    ) -> None:
        sid = _new_session()
        llm = _scripted_llm([GeminiReply(kind="error", text=FALLBACK_MESSAGE)])
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "hola")

        assert result is not None
        assert result.messages[-1].role == "assistant"
        assert result.messages[-1].content == FALLBACK_MESSAGE


class TestRespondAntiLoop:
    def test_more_than_max_tool_rounds_terminates_without_infinite_loop(
        self, monkeypatch
    ) -> None:
        sid = _new_session()
        # 8 tool_calls seguidas, sin reply de texto: margen sobre MAX_TOOL_ROUNDS.
        script = [
            GeminiReply(
                kind="tool_call",
                tool_name="perfilar_cliente",
                tool_args=dict(FAVORABLE_ARGS),
            )
            for _ in range(8)
        ]
        llm = _scripted_llm(script)
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "sigue preguntando cosas")

        assert result is not None
        assert result.messages[-1].role == "assistant"
        assert result.messages[-1].content
        assert len(llm.calls) <= orchestrator.MAX_TOOL_ROUNDS


class TestRespondSessionNotFound:
    def test_unknown_session_returns_none_without_calling_llm(
        self, monkeypatch
    ) -> None:
        llm = _scripted_llm([])
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond("no-existe", "hola")

        assert result is None
        assert len(llm.calls) == 0
