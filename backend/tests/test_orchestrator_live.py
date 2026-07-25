"""Test LIVE de conversación corta contra Gemini vía el endpoint HTTP.

GATED: la suite normal (`pytest`) NO ejecuta este test. Requiere
`RUN_LIVE_GEMINI_TESTS=1` y una `GEMINI_API_KEY` real en el entorno/`.env`,
porque hace llamadas HTTP reales que gastan créditos. Se corre a propósito y
de forma explícita:

    RUN_LIVE_GEMINI_TESTS=1 pytest tests/test_orchestrator_live.py -q -s

A diferencia de `tests/test_e2e_orchestrator.py` (LLM guionado, sin red),
este test NO monkeypatchea `orchestrator.generate_reply`: conversa de
verdad con Gemini a través del único punto de entrada conversacional
(`POST /{id}/message`). El arco de la conversación (si llega o no a
cotización en 2-3 turnos) lo decide el LLM, así que los asserts finales son
tolerantes; lo único que nunca se tolera es que algún turno responda con el
`FALLBACK_MESSAGE` (señal de error técnico/parseo, no de decisión del LLM).
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.conversation import ProfileData
from app.services.integrations.gemini_client import FALLBACK_MESSAGE
from app.services.quote import QuoteService

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_GEMINI_TESTS") != "1",
    reason="live: requiere RUN_LIVE_GEMINI_TESTS=1 y GEMINI_API_KEY real (gasta créditos)",
)

client = TestClient(app)


def _create_session() -> str:
    response = client.post("/api/v1/conversations", json={})
    assert response.status_code == 201
    return response.json()["session_id"]


def _last_assistant_message(data: dict) -> str:
    assistant_messages = [
        m["content"] for m in data["messages"] if m["role"] == "assistant"
    ]
    assert assistant_messages, f"no hay mensajes de assistant en: {data['messages']}"
    return assistant_messages[-1]


def test_live_conversacion_hasta_cotizacion() -> None:
    session_id = _create_session()

    # -- Turno 1: perfil libre en texto coloquial ----------------------------
    turno_1 = client.post(
        f"/api/v1/conversations/{session_id}/message",
        json={
            "content": (
                "Hola, quiero un seguro para mi casa. Vivo en apartamento "
                "propio, estrato 3, en Bogotá, zona urbana, tengo 35 años."
            )
        },
    )
    assert turno_1.status_code == 200, turno_1.text
    data_1 = turno_1.json()
    reply_1 = _last_assistant_message(data_1)
    assert reply_1 != FALLBACK_MESSAGE, (
        f"turno 1 devolvió el fallback. Estado de la sesión: {data_1}"
    )
    print(f"\n[turno 1] state={data_1['state']!r} assistant={reply_1!r}")

    # -- Turno 2: pide cotización explícita -----------------------------------
    turno_2 = client.post(
        f"/api/v1/conversations/{session_id}/message",
        json={"content": "Sí, cotízame ya por favor, ¿cuánto me cuesta al mes?"},
    )
    assert turno_2.status_code == 200, turno_2.text
    data_2 = turno_2.json()
    reply_2 = _last_assistant_message(data_2)
    assert reply_2 != FALLBACK_MESSAGE, (
        f"turno 2 devolvió el fallback. Estado de la sesión: {data_2}"
    )
    print(f"[turno 2] state={data_2['state']!r} assistant={reply_2!r}")

    get_after_2 = client.get(f"/api/v1/conversations/{session_id}")
    assert get_after_2.status_code == 200
    data_after_2 = get_after_2.json()

    # -- Turno 3 (solo si aún no hay cotización) ------------------------------
    if data_after_2.get("quote") is None:
        turno_3 = client.post(
            f"/api/v1/conversations/{session_id}/message",
            json={"content": "dale, muéstrame el precio"},
        )
        assert turno_3.status_code == 200, turno_3.text
        data_3 = turno_3.json()
        reply_3 = _last_assistant_message(data_3)
        assert reply_3 != FALLBACK_MESSAGE, (
            f"turno 3 devolvió el fallback. Estado de la sesión: {data_3}"
        )
        print(f"[turno 3] state={data_3['state']!r} assistant={reply_3!r}")

    # -- Asserts finales tolerantes: el LLM decide el arco --------------------
    get_final = client.get(f"/api/v1/conversations/{session_id}")
    assert get_final.status_code == 200
    data_final = get_final.json()

    assert len(data_final["messages"]) >= 4, (
        f"se esperaban al menos 4 mensajes (2 turnos), hubo "
        f"{len(data_final['messages'])}: {data_final['messages']}"
    )

    quote = data_final.get("quote")
    if quote is not None:
        profile = data_final["profile"]
        assert profile is not None, (
            f"hay quote pero no profile en la sesión: {data_final}"
        )
        profile_data = ProfileData(**profile)
        expected_premium = QuoteService().calculate_quote(profile_data)[
            "monthly_premium"
        ]
        assert quote["monthly_premium"] == expected_premium
        print(
            f"[final] state={data_final['state']!r} quote alcanzada: "
            f"monthly_premium={quote['monthly_premium']} "
            f"(esperado={expected_premium}) profile={profile}"
        )
    else:
        print(
            f"[final] no se alcanzó cotización en 3 turnos (arco no "
            f"determinista). state={data_final['state']!r} "
            f"profile={data_final.get('profile')!r}"
        )
