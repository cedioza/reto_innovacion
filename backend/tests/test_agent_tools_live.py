"""Tests LIVE contra la API real de Gemini para el contrato de `agent_tools`.

GATED: la suite normal (`pytest`) NO ejecuta estos tests. Requieren
`RUN_LIVE_GEMINI_TESTS=1` y una `GEMINI_API_KEY` real en el entorno/`.env`,
porque hacen llamadas HTTP reales que gastan créditos. Se corren a propósito
y de forma explícita:

    RUN_LIVE_GEMINI_TESTS=1 pytest tests/test_agent_tools_live.py -q

Validan que Gemini acepta las 5 declaraciones de `agent_tools` tal cual se
envían (un schema inválido haría que la API responda 400, que el cliente
traduce a `GeminiReply(kind="error")`) y que el modelo elige tools del
registro cuando el mensaje del cliente lo amerita. No assertan contenido
exacto del texto/args ni qué tool concreta elige el modelo (más allá de que
pertenezca al registro): son tolerantes a la variación del LLM.
"""

import os

import pytest

from app.services.agent_tools import AGENT_TOOLS, tool_declarations
from app.services.integrations.gemini_client import (
    generate_reply,
    text_part,
    user_message,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_GEMINI_TESTS") != "1",
    reason="live: requiere RUN_LIVE_GEMINI_TESTS=1 y GEMINI_API_KEY real (gasta créditos)",
)


def test_live_declarations_accepted_and_tool_from_registry():
    reply = generate_reply(
        [
            user_message(
                text_part(
                    "hola, quiero un seguro para mi casa, mi cédula es 12345"
                )
            )
        ],
        tools=tool_declarations(),
        system_instruction=(
            "Eres un asesor de seguros de Colsubsidio. Usa las herramientas "
            "disponibles cuando apliquen."
        ),
    )

    assert reply.kind != "error"
    if reply.kind == "tool_call":
        assert reply.tool_name in AGENT_TOOLS


def test_live_quote_request_uses_contract_tools():
    reply = generate_reply(
        [
            user_message(
                text_part(
                    "Ya te di mis datos: vivo en casa propia, estrato 3, "
                    "zona urbana, tengo 35 años. Cotízame el seguro de "
                    "hogar ya."
                )
            )
        ],
        tools=tool_declarations(),
        system_instruction=(
            "Eres un asesor de seguros de Colsubsidio. Usa las herramientas "
            "disponibles cuando apliquen. Cuando el cliente pida cotizar, "
            "usa las herramientas."
        ),
    )

    assert reply.kind == "tool_call"
    assert reply.tool_name in AGENT_TOOLS
