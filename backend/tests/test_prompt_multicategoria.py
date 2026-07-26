"""Tests del prompt multicategoría + identificación de afiliado — TDD RED
(plan B6, Fase 1, paso 1).

Cubre el contrato del `SYSTEM_PROMPT` que implementará el paso 2 (todavía NO
tocado por este archivo):

- Saludo: ya no ancla el propósito del bot solo a "proteger su hogar" — debe
  mencionar el portafolio completo (hogar, vida, familia, vehículo, créditos).
- Regla 6 (alcance): ya no dice "Tu alcance es acompañar la elección y compra
  de seguros de hogar" — el alcance pasa a ser el portafolio Colsubsidio
  completo (hogar, vida, accidentes personales, movilidad y crédito). Se
  conservan los guardrails textuales de siniestros/líneas de atención/no
  improvises (regresión de A5, Fase 2 — ver `test_guardrails.py`,
  `TestSystemPromptDomainRules`).
- Apertura nueva: al iniciar la conversación, ofrecer con naturalidad
  identificarse con el número de afiliado (una sola vez, sin insistir).

Es intencional que `TestPromptPortafolio` y `TestPromptIdentificacion` fallen
HOY por **aserción** (el texto todavía no existe en `SYSTEM_PROMPT`) — la
razón correcta de fallo pedida para esta tarea. `TestCarroEntraAlFunnel` no
depende del prompt (funnel mecánico guionado, sin LLM real) y debería pasar
ya en verde. `TestPromptLive` queda skipped sin `RUN_LIVE_GEMINI_TESTS=1`
(mismo gate que `test_orchestrator_live.py`): documentación ejecutable del
criterio, no se corre en la suite normal.
"""

from __future__ import annotations

import os

import pytest

from app.schemas.conversation import ConversationCreate
from app.services.conversation import conversation_service
from app.services.integrations.gemini_client import GeminiReply

import app.services.orchestrator as orchestrator


def _new_session() -> str:
    session = conversation_service.create(ConversationCreate())
    return session.session_id


def _scripted_llm(replies: list[GeminiReply]):
    """Copia local del helper de `test_orchestrator.py` / `test_guardrails.py`:
    guion determinista de `generate_reply`, sin red."""

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
# TestPromptPortafolio — sin LLM
# ==============================================================================


class TestPromptPortafolio:
    def test_scope_no_longer_anchored_only_to_hogar(self) -> None:
        prompt = orchestrator.SYSTEM_PROMPT
        assert (
            "Tu alcance es acompañar la elección y compra de seguros de hogar"
            not in prompt
        )

    def test_prompt_mentions_the_five_portfolio_categories(self) -> None:
        prompt = orchestrator.SYSTEM_PROMPT.lower()
        assert "hogar" in prompt
        assert "vida" in prompt
        assert "accidentes" in prompt
        assert "movilidad" in prompt
        assert "crédito" in prompt

    def test_keeps_the_domain_guardrails(self) -> None:
        prompt = orchestrator.SYSTEM_PROMPT
        assert "siniestros" in prompt.lower()
        assert "líneas de atención" in prompt.lower()
        assert "No improvises" in prompt


# ==============================================================================
# TestPromptIdentificacion — sin LLM
# ==============================================================================


class TestPromptIdentificacion:
    def test_offers_affiliate_identification(self) -> None:
        prompt = orchestrator.SYSTEM_PROMPT.lower()
        assert "afiliado" in prompt
        assert "número de afiliado" in prompt

    def test_does_not_insist_if_the_client_declines(self) -> None:
        prompt = orchestrator.SYSTEM_PROMPT.lower()
        assert "sin insistir" in prompt


# ==============================================================================
# TestCarroEntraAlFunnel — guionado (patrón `TestConversacionMovilidadGuionada`
# de `test_runt_simulado.py`), sin LLM real: criterio 2 mecánico.
# ==============================================================================


class TestCarroEntraAlFunnel:
    """"Quiero asegurar mi carro" debe entrar al funnel (consultar_vehiculo ->
    cotizar) sin desviarse a "fuera de dominio", tal como ya hace movilidad
    para RUNT."""

    def test_carro_llega_a_cotizacion_sin_desviarse(self, monkeypatch) -> None:
        sid = _new_session()

        # Turno 1: el cliente pide asegurar su carro; el bot consulta la
        # placa demo (XYZ987 -> Chevrolet Spark 2020) y confirma el vehículo.
        llm_turno_1 = _scripted_llm(
            [
                GeminiReply(
                    kind="tool_call",
                    tool_name="consultar_vehiculo",
                    tool_args={"placa": "XYZ987"},
                ),
                GeminiReply(
                    kind="text",
                    text=(
                        "Encontré tu vehículo: Chevrolet Spark 2020. "
                        "¿Seguimos con la cotización?"
                    ),
                ),
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm_turno_1)

        resultado_1 = orchestrator.respond(sid, "quiero asegurar mi carro")

        assert resultado_1 is not None
        mensaje_intermedio = resultado_1.messages[-1]
        assert mensaje_intermedio.role == "assistant"
        assert "líneas de atención" not in mensaje_intermedio.content.lower()

        # Turno 2: el cliente confirma, el bot cotiza.
        llm_turno_2 = _scripted_llm(
            [
                GeminiReply(kind="tool_call", tool_name="cotizar", tool_args={}),
                GeminiReply(kind="text", text="Tu cotización ya está lista."),
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm_turno_2)

        resultado_2 = orchestrator.respond(sid, "sí, cotiza")

        assert resultado_2 is not None
        assert resultado_2.quote is not None
        assert "líneas de atención" not in resultado_2.messages[-1].content.lower()


# ==============================================================================
# TestPromptLive — gateado, mismo skipif que `test_orchestrator_live.py`
# ==============================================================================


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_GEMINI_TESTS") != "1",
    reason="live: requiere RUN_LIVE_GEMINI_TESTS=1 y GEMINI_API_KEY real (gasta créditos)",
)
class TestPromptLive:
    """Documentación ejecutable del criterio, contra Gemini real. NO corre en
    la suite normal (`pytest`): requiere `RUN_LIVE_GEMINI_TESTS=1`."""

    def test_live_primer_turno_ofrece_identificacion(self) -> None:
        sid = _new_session()

        result = orchestrator.respond(sid, "hola, quiero información de seguros")

        assert result is not None
        assistant_messages = [
            m.content
            for m in result.messages
            if m.role == "assistant" and m.type == "text"
        ]
        assert assistant_messages, "no hubo respuesta de texto del assistant"
        texto = assistant_messages[-1]
        assert "afiliado" in texto.lower()

    def test_live_carro_no_se_desvia(self) -> None:
        sid = _new_session()

        result = orchestrator.respond(sid, "quiero asegurar mi carro")

        assert result is not None
        assistant_messages = [
            m.content
            for m in result.messages
            if m.role == "assistant" and m.type == "text"
        ]
        assert assistant_messages, "no hubo respuesta de texto del assistant"
        texto = assistant_messages[-1]
        assert "líneas de atención" not in texto.lower()
