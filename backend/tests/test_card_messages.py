"""Tests for typed card messages in the orchestrator — TDD RED phase (Fase 1 de D3).

Cubre `.claude/analysis/plans/
20260725-d3-tarjetas-recomendacion-cotizacion-comparador.plan.md` (Fase 1):

- `Message` gana `type: str = "text"` y `payload: dict | None = None`.
- `QuoteDetail` gana `annual_premium: float | None = None`.
- `orchestrator.respond()` agrega, tras el mensaje de texto final del turno, uno o
  más mensajes-tarjeta (`type` in `recommendation|quote|comparison`) por cada tool
  clave ejecutada en ESE turno (`recomendar_seguro`, `cotizar`, `ajustar_comparar`),
  en ese orden, con el último resultado si una tool corrió varias veces.
- `_contents_from_history` deja de mandar al LLM los mensajes con `type != "text"`.

Ninguno de estos comportamientos existe todavía: es intencional que estos tests
fallen con `AttributeError` (campo `type`/`payload` inexistente en `Message`, o
inexistente en `QuoteDetail`) o por aserción de contenido (falta la tarjeta, el
guard rechaza una cifra real, o el historial filtra el mensaje-tarjeta hacia el
LLM) — nunca por `ImportError` ni por un fixture roto.

El LLM se guioniza vía `monkeypatch` de `orchestrator.generate_reply`, mismo patrón
de `tests/test_orchestrator.py` / `tests/test_guardrails.py`: cero llamadas reales.
"""

from __future__ import annotations

from app.schemas.conversation import (
    ConversationCreate,
    ConversationState,
    Message,
    ProfileData,
    QuoteDetail,
)
from app.services.agent_tools import ToolContext, execute_tool
from app.services.conversation import conversation_service
from app.services.integrations.gemini_client import GeminiReply
from app.services.quote import QuoteService

import app.services.orchestrator as orchestrator


# -- helpers (mismo patrón que test_orchestrator.py / test_guardrails.py) --------


def _scripted_llm(replies: list[GeminiReply]):
    """Fábrica de un `generate_reply` guionado (sin red).

    Devuelve una función con la firma de
    `generate_reply(contents, *, tools=None, system_instruction=None)` que
    responde con `replies` en orden y registra cada llamada en `.calls`. Si el
    guion se agota, falla con AssertionError.
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


def _new_session() -> str:
    session = conversation_service.create(ConversationCreate())
    return session.session_id


FAVORABLE_ARGS = {
    "property_type": "house",
    "zone": "urban",
    "stratum": 3,
    "age_range": "26-40",
}

FAVORABLE_PROFILE = ProfileData(
    age_range="26-40", stratum=3, property_type="house", zone="urban"
)

# Perfil sugerido por la tarea (Fase 1): apartment/urban/estrato 3/26-40, que
# dispara >=2 reglas del motor de propensión (de hecho dispara las 4: homeowner,
# family_profile, income_tier, zone_risk).
RICH_ARGS = {
    "property_type": "apartment",
    "zone": "urban",
    "stratum": 3,
    "age_range": "26-40",
}

RICH_PROFILE = ProfileData(
    age_range="26-40", stratum=3, property_type="apartment", zone="urban"
)


# ==============================================================================
# 1) cotizar -> tarjeta `quote` al final, con las cifras exactas del motor
# ==============================================================================


class TestQuoteCardMessage:
    def test_last_message_after_cotizar_is_a_quote_card(self, monkeypatch) -> None:
        sid = _new_session()
        texto_final = "Tu prima mensual queda calculada con el motor."
        llm = _scripted_llm(
            [
                GeminiReply(
                    kind="tool_call",
                    tool_name="perfilar_cliente",
                    tool_args=dict(FAVORABLE_ARGS),
                ),
                GeminiReply(kind="tool_call", tool_name="cotizar", tool_args={}),
                GeminiReply(kind="text", text=texto_final),
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "quiero cotizar mi casa")

        assert result is not None
        expected_quote = QuoteService().calculate_quote(FAVORABLE_PROFILE)

        # Al menos: user, assistant-texto, tarjeta-quote.
        assert len(result.messages) >= 3
        text_message, card_message = result.messages[-2], result.messages[-1]

        assert text_message.role == "assistant"
        assert text_message.content == texto_final
        # El mensaje de texto sigue siendo `type == "text"` (compatibilidad).
        assert text_message.type == "text"

        assert card_message.role == "assistant"
        assert card_message.type == "quote"
        assert card_message.content  # resumen de una línea, no vacío
        assert card_message.payload == expected_quote


# ==============================================================================
# 2) recomendar_seguro -> tarjeta `recommendation` con >=2 razones
# ==============================================================================


class TestRecommendationCardMessage:
    def test_recommendation_card_has_product_name_and_multiple_reasons(
        self, monkeypatch
    ) -> None:
        sid = _new_session()
        texto_final = "Te recomiendo Hogar Estándar por tu perfil."
        llm = _scripted_llm(
            [
                GeminiReply(
                    kind="tool_call",
                    tool_name="perfilar_cliente",
                    tool_args=dict(RICH_ARGS),
                ),
                GeminiReply(
                    kind="tool_call", tool_name="recomendar_seguro", tool_args={}
                ),
                GeminiReply(kind="text", text=texto_final),
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "quiero una recomendación")

        assert result is not None
        assert len(result.messages) >= 3
        card_message = result.messages[-1]

        assert card_message.role == "assistant"
        assert card_message.type == "recommendation"
        assert card_message.content
        assert card_message.payload["product_name"] == "Hogar Estándar"
        assert len(card_message.payload["reasons"]) >= 2


# ==============================================================================
# 3) ajustar_comparar (tras cotizar) -> tarjeta `comparison`, después de `quote`
# ==============================================================================


class TestComparisonCardMessage:
    def test_ajustar_comparar_yields_comparison_card_after_quote_card(
        self, monkeypatch
    ) -> None:
        sid = _new_session()
        texto_final = "Con la alarma tu prima baja."
        llm = _scripted_llm(
            [
                GeminiReply(
                    kind="tool_call",
                    tool_name="perfilar_cliente",
                    tool_args=dict(FAVORABLE_ARGS),
                ),
                GeminiReply(kind="tool_call", tool_name="cotizar", tool_args={}),
                GeminiReply(
                    kind="tool_call",
                    tool_name="ajustar_comparar",
                    tool_args={"adjustments": ["fire_alarm"]},
                ),
                GeminiReply(kind="text", text=texto_final),
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "quiero comparar con alarma")

        assert result is not None
        # user, assistant-texto, tarjeta-quote, tarjeta-comparison.
        assert len(result.messages) >= 4
        text_message, quote_card, comparison_card = result.messages[-3:]

        assert text_message.type == "text"
        assert quote_card.type == "quote"
        assert comparison_card.type == "comparison"
        assert comparison_card.content

        # Resultado esperado: se replica el mismo cómputo determinista que hace
        # el handler real de la tool, sobre un ToolContext equivalente al del
        # turno (mismo perfil, misma cotización actual sin ajustes).
        expected_actual = QuoteService().calculate_quote(FAVORABLE_PROFILE)
        expected_ctx = ToolContext(
            session_id="expected",
            profile=FAVORABLE_PROFILE.model_copy(),
            quote=dict(expected_actual),
        )
        expected_comparison = execute_tool(
            "ajustar_comparar", {"adjustments": ["fire_alarm"]}, expected_ctx
        )

        assert comparison_card.payload["actual"] == expected_comparison["actual"]
        assert (
            comparison_card.payload["propuesta"] == expected_comparison["propuesta"]
        )
        assert (
            comparison_card.payload["diferencia_mensual"]
            == expected_comparison["diferencia_mensual"]
        )
        assert (
            comparison_card.payload["ajustes_disponibles"]
            == expected_comparison["ajustes_disponibles"]
        )


# ==============================================================================
# 4) Exclusión del historial: los mensajes-tarjeta no llegan al LLM
# ==============================================================================


class TestContentsExcludeCardMessages:
    def test_card_type_message_is_excluded_from_llm_contents(
        self, monkeypatch
    ) -> None:
        """Aísla el filtro `type == "text"` de `_contents_from_history`.

        Se inyecta directamente en el historial persistido un mensaje-tarjeta
        (con los kwargs `type`/`payload` que `Message` todavía no declara —
        hoy Pydantic los ignora en silencio, dejando el mensaje como texto
        plano de rol `assistant`). Así el test es determinista sin depender de
        que las tarjetas ya se autogeneren (Secciones 1-3): hoy debe fallar
        por ASERCIÓN, porque `_contents_from_history` todavía manda cualquier
        mensaje `assistant`/`user` sin filtrar por `type`.
        """
        sid = _new_session()
        session = conversation_service.get(sid)
        assert session is not None

        card_content = "Te recomendamos Hogar Estándar (resumen de tarjeta)."
        session.messages.append(
            Message(
                role="assistant",
                content=card_content,
                type="recommendation",
                payload={"product_id": "hogar-estandar"},
            )
        )
        conversation_service._repo.save(sid, session)

        llm = _scripted_llm([GeminiReply(kind="text", text="Perfecto, sigamos.")])
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "quiero seguir")
        assert result is not None

        contents = llm.calls[0]["contents"]
        texts_sent = [
            part.get("text", "")
            for message in contents
            for part in message.get("parts", [])
            if isinstance(part, dict)
        ]
        assert not any(card_content in text for text in texts_sent), (
            "el contenido de la tarjeta llegó al LLM: los mensajes con "
            "type != 'text' deben excluirse de `_contents_from_history`"
        )


# ==============================================================================
# 5) Guard con prima anual ajustada (bug latente que corrige este plan)
# ==============================================================================


class TestGuardPreservesAdjustedAnnualPremium:
    def test_adjusted_annual_premium_text_is_not_replaced_by_safe_template(
        self, monkeypatch
    ) -> None:
        sid = _new_session()
        session = conversation_service.get(sid)
        assert session is not None

        adjusted = QuoteService().calculate_quote(FAVORABLE_PROFILE, ["fire_alarm"])
        # Cifras del plan: anual 38.250 (0.85 * 45.000), distinta de la base.
        assert adjusted["annual_premium"] == 38250.0
        assert adjusted["annual_premium"] != adjusted["base_amount"]

        session.profile = FAVORABLE_PROFILE.model_copy()
        quote_fields = {
            key: value
            for key, value in adjusted.items()
            if key in QuoteDetail.model_fields
        }
        session.quote = QuoteDetail(**quote_fields)
        session.state = ConversationState.QUOTE_READY
        conversation_service._repo.save(sid, session)

        texto = "Con la alarma tu prima anual queda en $38.250 COP."
        llm = _scripted_llm([GeminiReply(kind="text", text=texto)])
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "¿cuánto me queda con alarma?")
        assert result is not None

        final_text = result.messages[-1].content
        assert final_text == texto, (
            "el guard reemplazó una cifra REAL (prima anual ajustada) por la "
            "plantilla segura: falta `annual_premium` en `QuoteDetail`"
        )

        # Además, el campo debe persistir tal cual en el `QuoteDetail` guardado.
        assert session.quote.annual_premium == 38250.0


# ==============================================================================
# 6) Compatibilidad: los mensajes de texto siguen con type == "text" por defecto
# ==============================================================================


class TestDefaultMessageTypeIsText:
    def test_plain_text_turn_produces_text_type_with_none_payload(
        self, monkeypatch
    ) -> None:
        sid = _new_session()
        llm = _scripted_llm(
            [GeminiReply(kind="text", text="¡Hola! Cuéntame de tu casa")]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "hola")

        assert result is not None
        assert len(result.messages) >= 2
        user_message, assistant_message = result.messages[-2], result.messages[-1]

        assert user_message.type == "text"
        assert user_message.payload is None
        assert assistant_message.type == "text"
        assert assistant_message.payload is None
