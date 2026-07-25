"""Tests for the mechanical price guardrail — TDD RED phase (Fase 1 de A5).

Cubre `.claude/analysis/plans/20260725-a5-guardrails-y-confirmaciones.plan.md`
(Fase 1): tres funciones puras nuevas en `app.services.orchestrator` que
todavía NO existen —

    _extract_money_figures(texto: str) -> set
    _allowed_figures(ctx: ToolContext) -> set
    _guard_reply(texto: str, ctx: ToolContext) -> str

— y su integración de una línea en `respond()` (choke point único donde se
asigna `texto_final`). Ninguna de las tres funciones se implementa en esta
tarea: es intencional que los tests unitarios (Secciones A/B) fallen con
`AttributeError` (el atributo no existe en el módulo) y que los tests
end-to-end adversarios (Sección C) fallen por **aserción** — hoy no hay
guard, así que la cifra inventada por el LLM guionado llega intacta al
cliente.

Los tests end-to-end reutilizan el patrón guionado de A3
(`tests/test_orchestrator.py`, `tests/test_e2e_orchestrator.py`):
`generate_reply` se reemplaza con `monkeypatch` por un guion determinista,
sin red.
"""

from __future__ import annotations

import base64
import re

from app.schemas.conversation import ConversationCreate, ProfileData
from app.services.agent_tools import ToolContext
from app.services.conversation import conversation_service
from app.services.integrations.gemini_client import GeminiReply
from app.services.quote import QuoteService

import app.services.orchestrator as orchestrator


# -- helpers (mismo patrón que test_orchestrator.py / test_e2e_orchestrator.py) --


def _scripted_llm(replies: list[GeminiReply]):
    """Fábrica de un `generate_reply` guionado (sin red).

    Devuelve una función con la firma de
    `generate_reply(contents, *, tools=None, system_instruction=None)` que
    responde con `replies` en orden y registra cada llamada en `.calls`. Si
    el guion se agota, falla con AssertionError.
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

# Cifras reales del motor para este perfil (usadas también por
# test_orchestrator.py / test_e2e_orchestrator.py): monthly_premium=3750.0,
# annual_premium=45000.0, base_amount=45000.0.
REAL_QUOTE = QuoteService().calculate_quote(FAVORABLE_PROFILE)
REAL_MONTHLY = REAL_QUOTE["monthly_premium"]
REAL_ANNUAL = REAL_QUOTE["annual_premium"]

# Matchea cualquier formateo razonable ("3750", "3.750", "3,750") de la
# prima mensual o anual reales — usado como oráculo en los asserts e2e, SIN
# pasar por `_extract_money_figures` (que no existe aún): estos tests deben
# fallar por aserción, no por AttributeError.
REAL_PREMIUM_PATTERN = re.compile(r"3[.,]?750|45[.,]?000")


# ==============================================================================
# Sección A — unit tests de `_extract_money_figures`
# ==============================================================================


class TestExtractMoneyFigures:
    def test_dollar_sign_with_dot_thousands_separator(self) -> None:
        assert orchestrator._extract_money_figures("$3.750") == {3750}

    def test_comma_thousands_separator_with_pesos_word(self) -> None:
        assert orchestrator._extract_money_figures("3,750 pesos") == {3750}

    def test_plain_number_with_cop_word(self) -> None:
        assert orchestrator._extract_money_figures("3750 COP") == {3750}

    def test_dollar_space_dot_thousands_comma_decimals(self) -> None:
        assert orchestrator._extract_money_figures("$ 128.550,50") == {128550.5}

    def test_captures_dollar_figure_among_mixed_formats(self) -> None:
        # NOTA de alcance: "120 mil pesos" (número + palabra "mil" en
        # prosa) es un formato opcional que esta suite NO exige cubrir —
        # el mínimo exigido es capturar la cifra con marcador "$"
        # (`$99.999`). Si la implementación también cubre "120 mil" →
        # 120000, es un extra válido, pero no se asserta aquí.
        result = orchestrator._extract_money_figures(
            "cuesta $99.999 y también 120 mil pesos"
        )
        assert 99999 in result

    def test_no_false_positive_on_ages_stratum_and_ranges(self) -> None:
        assert (
            orchestrator._extract_money_figures(
                "tienes 35 años, estrato 3, rango 26-40"
            )
            == set()
        )

    def test_no_false_positive_on_time_reference(self) -> None:
        assert orchestrator._extract_money_figures("en 5 minutos te respondo") == set()


class TestAllowedFigures:
    """Interfaz declarada en el plan (Fase 1) para `_allowed_figures`."""

    def test_collects_the_three_quote_fields(self) -> None:
        ctx = ToolContext(
            session_id="s1",
            quote={
                "monthly_premium": 100.0,
                "annual_premium": 1200.0,
                "base_amount": 1300.0,
                "currency": "COP",
                "adjustments": [],
            },
        )
        assert orchestrator._allowed_figures(ctx) == {100.0, 1200.0, 1300.0}

    def test_empty_set_without_quote(self) -> None:
        ctx = ToolContext(session_id="s1", quote=None)
        assert orchestrator._allowed_figures(ctx) == set()


# ==============================================================================
# Sección B — unit tests de `_guard_reply` con un ToolContext armado a mano
# ==============================================================================


def _ctx_with_quote() -> ToolContext:
    return ToolContext(
        session_id="s1",
        quote={
            "monthly_premium": 3750.0,
            "annual_premium": 45000.0,
            "base_amount": 45000.0,
            "currency": "COP",
            "adjustments": [],
        },
    )


class TestGuardReplyWithQuote:
    def test_honest_figure_from_the_quote_passes_intact(self) -> None:
        ctx = _ctx_with_quote()
        texto = "Tu prima es $3.750 COP al mes"
        assert orchestrator._guard_reply(texto, ctx) == texto

    def test_invented_figure_is_replaced_and_real_premium_is_present(self) -> None:
        ctx = _ctx_with_quote()
        texto = "Te sale en $99.999"
        result = orchestrator._guard_reply(texto, ctx)
        assert "99.999" not in result
        assert "99999" not in result
        assert REAL_PREMIUM_PATTERN.search(result)


class TestGuardReplyWithoutQuote:
    def test_any_monetary_figure_without_quote_is_replaced(self) -> None:
        ctx = ToolContext(session_id="s1", quote=None)
        texto = "cuesta $50.000"
        result = orchestrator._guard_reply(texto, ctx)
        assert "50.000" not in result
        assert "50000" not in result

    def test_text_without_figures_and_without_quote_passes_intact(self) -> None:
        ctx = ToolContext(session_id="s1", quote=None)
        texto = "¡Hola! Cuéntame de tu casa"
        assert orchestrator._guard_reply(texto, ctx) == texto


# ==============================================================================
# Sección C — comportamiento end-to-end guionado (patrón A3, criterio 3 de A5)
# ==============================================================================


def _respond_after_quote(monkeypatch, texto_final: str):
    """Guiona perfilar_cliente -> cotizar -> texto final `texto_final`.

    Mismo guion de `TestRespondChainToQuote` en test_orchestrator.py: dos
    tool_call seguidas de un texto final, sobre una sesión nueva. Devuelve
    la sesión resultante de `orchestrator.respond`.
    """
    sid = _new_session()
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
    return result


# 5 conversaciones honestas: el guion cita EXACTAMENTE la prima del motor
# (3750.0 mensual / 45000.0 anual), en distintos formatos de texto.
HONEST_TEXTS = [
    "Tu prima mensual queda en $3.750 COP, tal como la calculó nuestro motor.",
    "Con tu perfil, la prima es de 3750 COP al mes.",
    "Quedaría en $3.750 mensuales; al año son $45.000 COP.",
    "Tu cotización: 3,750 pesos mensuales según el sistema.",
    "La prima anual es de $45.000 COP, equivalente a $3.750 al mes.",
]

# 5 conversaciones adversarias: el guion "alucina" una cifra que NO existe
# en los outputs de las tools.
ADVERSARIAL_CASES = [
    ("Te sale en $99.999 al mes, una ganga.", "99.999"),
    ("La prima queda en 250.000 COP mensuales.", "250.000"),
    ("Anualmente serían $1.200.000 COP.", "1.200.000"),
    ("Te cobran 88,000 pesos cada mes.", "88,000"),
    ("Con descuento especial, $7.500 COP mensuales.", "7.500"),
]


class TestScriptedConversationsHonest:
    """Las 5 conversaciones honestas del criterio 3 de A5.

    NOTA: hoy (sin guard implementado) estas aserciones PASAN trivialmente,
    porque `texto_final` es literalmente `reply.text` sin ninguna
    intercepción — quedan aquí como regresión para cuando el guard exista:
    debe seguir dejando intactas las respuestas honestas.
    """

    def test_honest_quotes_pass_through_intact(self, monkeypatch) -> None:
        for texto in HONEST_TEXTS:
            result = _respond_after_quote(monkeypatch, texto)
            assert result.messages[-1].role == "assistant"
            assert result.messages[-1].content == texto


class TestScriptedConversationsAdversarial:
    """Las 5 conversaciones adversarias del criterio 3 de A5.

    HOY fallan por ASERCIÓN (no hay guard: la cifra inventada por el LLM
    guionado llega intacta al cliente) — es la razón correcta de fallo
    pedida para esta sección, distinta del AttributeError de las Secciones
    A/B.
    """

    def test_invented_figures_are_intercepted(self, monkeypatch) -> None:
        for texto, cifra_falsa in ADVERSARIAL_CASES:
            result = _respond_after_quote(monkeypatch, texto)
            final_text = result.messages[-1].content
            assert cifra_falsa not in final_text, (
                f"la cifra inventada {cifra_falsa!r} llegó intacta al "
                f"cliente: {final_text!r}"
            )
            assert REAL_PREMIUM_PATTERN.search(final_text), (
                "la respuesta segura debería citar la prima real "
                f"(3.750/45.000): {final_text!r}"
            )


class TestTerremotoInterceptado:
    """Versión guionada del criterio 1 de A5: el cliente pregunta por otra
    cobertura "por el mismo precio" y el LLM guionado inventa que sí, por
    un precio falso — debe interceptarse igual que en Sección C."""

    def test_terremoto_same_fake_price_is_intercepted(self, monkeypatch) -> None:
        sid = _new_session()
        llm_turno_1 = _scripted_llm(
            [
                GeminiReply(
                    kind="tool_call",
                    tool_name="perfilar_cliente",
                    tool_args=dict(FAVORABLE_ARGS),
                ),
                GeminiReply(kind="tool_call", tool_name="cotizar", tool_args={}),
                GeminiReply(
                    kind="text",
                    text="Tu prima mensual queda en $3.750 COP.",
                ),
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm_turno_1)
        first = orchestrator.respond(sid, "quiero cotizar mi casa")
        assert first is not None
        assert first.quote is not None

        llm_turno_2 = _scripted_llm(
            [
                GeminiReply(
                    kind="text",
                    text="Claro, terremoto te lo cubro por los mismos $99.999",
                )
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm_turno_2)

        second = orchestrator.respond(
            sid, "¿me cubre terremoto por el mismo precio?"
        )
        assert second is not None

        final_text = second.messages[-1].content
        assert "99.999" not in final_text, (
            f"la cifra inventada para terremoto llegó intacta: {final_text!r}"
        )
        assert REAL_PREMIUM_PATTERN.search(final_text), (
            f"la respuesta segura debería citar la prima real: {final_text!r}"
        )


class TestFalsoPositivoEndToEnd:
    """Guion sin marcador monetario (edad, estrato) y sin cotización previa:
    el guard NO debe dispararse solo porque hay números en el texto.

    NOTA: hoy pasa trivialmente (sin guard, `texto_final == reply.text`).
    """

    def test_ages_and_stratum_without_money_marker_pass_intact(
        self, monkeypatch
    ) -> None:
        sid = _new_session()
        texto = "Perfecto: 35 años, estrato 3, casa propia. ¿Seguimos?"
        llm = _scripted_llm([GeminiReply(kind="text", text=texto)])
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "hola")

        assert result is not None
        assert result.messages[-1].content == texto


# ==============================================================================
# Fase 2: reglas de dominio y "no entendí" ------------------------------------
# ==============================================================================
#
# Cubre `.claude/analysis/plans/20260725-a5-guardrails-y-confirmaciones.plan.md`
# (Fase 2): las reglas 6 (alcance/fuera de dominio) y 7 (no entendí) deben
# viajar en `SYSTEM_PROMPT` -y por tanto en el `system_instruction` que recibe
# el LLM en cada turno- con conceptos concretos, no como párrafo exacto (la
# redacción final es libre siempre que cubra estos conceptos). Además, una
# respuesta guionada de alcance (sin cifras) debe atravesar el guard de
# precios intacta.


class TestSystemPromptDomainRules:
    """Regla 6 (alcance/fuera de dominio) y regla 7 (no entendí) en el prompt."""

    def test_scope_rule_mentions_out_of_domain_topics_and_referral(self) -> None:
        prompt = orchestrator.SYSTEM_PROMPT
        assert "siniestros" in prompt.lower()
        assert "líneas de atención" in prompt.lower()
        assert "No improvises" in prompt

    def test_misunderstanding_rule_asks_to_repeat_instead_of_assuming(self) -> None:
        prompt = orchestrator.SYSTEM_PROMPT.lower()
        assert "pide que te lo repita" in prompt
        assert "nunca actúes sobre una suposición" in prompt


class TestSystemInstructionCarriesDomainRules:
    """El `system_instruction` capturado en la llamada al LLM trae ambas reglas."""

    def test_system_instruction_of_a_turn_contains_scope_and_misunderstanding_rules(
        self, monkeypatch
    ) -> None:
        sid = _new_session()
        llm = _scripted_llm(
            [GeminiReply(kind="text", text="¡Hola! Cuéntame de tu casa")]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "hola")
        assert result is not None

        system_instruction = llm.calls[0]["system_instruction"].lower()
        assert "siniestros" in system_instruction
        assert "líneas de atención" in system_instruction
        assert "pide que te lo repita" in system_instruction
        assert "nunca actúes sobre una suposición" in system_instruction


class TestScriptedOutOfScopeClaim:
    """Guion "¿cómo reporto un siniestro?" -> respuesta de alcance SIN cifras."""

    def test_scope_reply_without_figures_passes_the_guard_intact(
        self, monkeypatch
    ) -> None:
        sid = _new_session()
        texto = (
            "Eso lo atienden las líneas de atención de Colsubsidio; yo te "
            "acompaño con tu seguro de hogar, ¿seguimos?"
        )
        llm = _scripted_llm([GeminiReply(kind="text", text=texto)])
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "¿cómo reporto un siniestro?")

        assert result is not None
        assert result.messages[-1].content == texto


# ==============================================================================
# Fase 3: turnos de audio con confirmación forzada ----------------------------
# ==============================================================================
#
# Cubre `.claude/analysis/plans/20260725-a5-guardrails-y-confirmaciones.plan.md`
# (Fase 3, criterio 2 de A5): `respond()` todavía NO acepta `audio_data` ni
# `audio_mime` — la interfaz esperada es
#
#     respond(session_id, content, *, audio_data: bytes | None = None,
#             audio_mime: str = "audio/ogg")
#
# Es intencional que los 3 tests que pasan `audio_data=...` fallen HOY con
# `TypeError` (kwarg inexistente en la firma actual de `respond`) — es la
# razón correcta de fallo para esta fase. El test de regresión (turno sin
# audio) NO debe fallar: ya pasa con la firma actual, y debe seguir pasando
# una vez implementada la Fase 3 (cero regresión sobre el flujo de texto).


def _find_inline_data_part(contents: list[dict]) -> dict | None:
    """Busca la primera `part` `inline_data` en el último mensaje de `contents`."""
    if not contents:
        return None
    last_message = contents[-1]
    for part in last_message.get("parts", []):
        if isinstance(part, dict) and "inline_data" in part:
            return part["inline_data"]
    return None


class TestAudioTurnScriptedBehaviour:
    def test_audio_turn_disables_tools_and_injects_voice_rule(self, monkeypatch) -> None:
        sid = _new_session()
        llm = _scripted_llm(
            [
                GeminiReply(
                    kind="text",
                    text=(
                        "Entendí que quieres asegurar tu casa en Bogotá, "
                        "¿es correcto?"
                    ),
                )
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "", audio_data=b"fake-ogg")

        assert result is not None
        assert len(llm.calls) >= 1
        call = llm.calls[0]

        # El turno de audio no debe ofrecer herramientas al modelo: es la
        # garantía "por construcción" de que no puede actuar en este turno.
        assert not call["tools"]

        system_instruction = (call["system_instruction"] or "").lower()
        assert "nota de voz" in system_instruction
        assert "confirma" in system_instruction  # cubre "confirmación"/"confirma"
        assert "no llames herramientas" in system_instruction

        inline_data = _find_inline_data_part(call["contents"])
        assert inline_data is not None
        assert inline_data["mime_type"] == "audio/ogg"
        assert inline_data["data"] == base64.b64encode(b"fake-ogg").decode()

    def test_audio_turn_never_executes_tool_calls(self, monkeypatch) -> None:
        sid = _new_session()
        llm = _scripted_llm(
            [
                GeminiReply(
                    kind="tool_call",
                    tool_name="perfilar_cliente",
                    tool_args={"stratum": 3},
                ),
                GeminiReply(
                    kind="text", text="Entendí tu mensaje, ¿confirmas?"
                ),
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "", audio_data=b"x")

        assert result is not None
        # Aunque el guion (malicioso/con error) devuelva un tool_call, el
        # orquestador NUNCA lo ejecuta en un turno de audio: defensa en
        # profundidad además de la ausencia de `tools` en el payload.
        assert result.profile is None
        assert result.messages[-1].role == "assistant"
        assert result.messages[-1].content != ""

    def test_audio_turn_without_caption_stores_placeholder(self, monkeypatch) -> None:
        llm = _scripted_llm(
            [
                GeminiReply(kind="text", text="¿Es correcto lo que entendí?"),
                GeminiReply(kind="text", text="Entendí, ¿confirmas?"),
            ]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        sid_sin_caption = _new_session()
        result_sin_caption = orchestrator.respond(
            sid_sin_caption, "", audio_data=b"x"
        )
        assert result_sin_caption is not None
        user_messages = [
            m for m in result_sin_caption.messages if m.role == "user"
        ]
        assert user_messages[-1].content == "[nota de voz]"

        sid_con_caption = _new_session()
        result_con_caption = orchestrator.respond(
            sid_con_caption, "esto dije", audio_data=b"x"
        )
        assert result_con_caption is not None
        user_messages = [
            m for m in result_con_caption.messages if m.role == "user"
        ]
        assert user_messages[-1].content == "esto dije"

    def test_text_turn_regression_keeps_tools_and_omits_voice_rule(
        self, monkeypatch
    ) -> None:
        """Turno normal sin audio: comportamiento idéntico al actual.

        A diferencia de los tres tests anteriores de esta sección, este NO
        pasa `audio_data` — usa la firma ya existente de `respond()`, así que
        debe PASAR hoy mismo (no hay TypeError posible aquí).
        """
        sid = _new_session()
        llm = _scripted_llm(
            [GeminiReply(kind="text", text="¡Hola! Cuéntame de tu casa")]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        result = orchestrator.respond(sid, "hola")

        assert result is not None
        call = llm.calls[0]
        assert call["tools"]
        assert "nota de voz" not in (call["system_instruction"] or "").lower()
