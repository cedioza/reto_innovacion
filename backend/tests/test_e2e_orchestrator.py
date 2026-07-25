"""E2E de conversación LIBRE vía HTTP, con LLM guionado — Fase 4 del plan A3.

A diferencia de `tests/test_e2e_happy_path.py` (flujo estructurado por
endpoints dedicados: `/profile`, `/accept`, `/consent`), este e2e ejercita el
único punto de entrada conversacional (`POST /{id}/message`) con texto
coloquial libre y un LLM guionado (sin red, vía monkeypatch de
`orchestrator.generate_reply`), verificando que el precio y la recomendación
que llegan al cliente sean EXACTAMENTE los del motor determinista.
"""

from __future__ import annotations

from pathlib import Path
import tempfile

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.conversation import ProfileData
from app.services.integrations.gemini_client import GeminiReply
from app.services.quote import QuoteService

import app.services.orchestrator as orchestrator

client = TestClient(app)


def _scripted_llm(replies: list[GeminiReply]):
    """Fábrica de un `generate_reply` guionado (sin red).

    Mismo patrón que `tests/test_conversations_router.py` y
    `tests/test_orchestrator.py`: devuelve las `replies` en orden y falla con
    AssertionError si se agota el guion (más llamadas que respuestas).
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


FAVORABLE_ARGS = {
    "property_type": "house",
    "zone": "urban",
    "stratum": 3,
    "age_range": "26-40",
}

FAVORABLE_PROFILE = ProfileData(
    age_range="26-40", stratum=3, property_type="house", zone="urban"
)


def _create_session() -> str:
    response = client.post("/api/v1/conversations", json={})
    assert response.status_code == 201
    return response.json()["session_id"]


class TestProspectoTextoLibreHastaCotizacion:
    def test_prospecto_texto_libre_hasta_cotizacion(self, monkeypatch) -> None:
        session_id = _create_session()

        script = [
            GeminiReply(
                kind="tool_call",
                tool_name="perfilar_cliente",
                tool_args=dict(FAVORABLE_ARGS),
                thought_signature="sig-1",
            ),
            GeminiReply(
                kind="text",
                text="¡Con gusto! Cuéntame, ¿cuánto te gustaría cotizar?",
            ),
            GeminiReply(
                kind="tool_call",
                tool_name="recomendar_seguro",
                tool_args={},
                thought_signature="sig-2",
            ),
            GeminiReply(
                kind="tool_call",
                tool_name="cotizar",
                tool_args={},
                thought_signature="sig-3",
            ),
            GeminiReply(
                kind="text",
                text="Tu prima mensual es la de la cotización",
            ),
        ]
        llm = _scripted_llm(script)
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        turno_1 = client.post(
            f"/api/v1/conversations/{session_id}/message",
            json={
                "content": (
                    "hola, quiero proteger a mi familia, vivimos en casa "
                    "propia en Bogotá"
                )
            },
        )
        assert turno_1.status_code == 200, turno_1.text

        turno_2 = client.post(
            f"/api/v1/conversations/{session_id}/message",
            json={"content": "listo, ¿cuánto me costaría?"},
        )
        assert turno_2.status_code == 200, turno_2.text

        assert len(llm.calls) == 5

        get_resp = client.get(f"/api/v1/conversations/{session_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()

        assert data["state"] == "quote_ready"

        expected_premium = QuoteService().calculate_quote(FAVORABLE_PROFILE)[
            "monthly_premium"
        ]
        assert data["quote"]["monthly_premium"] == expected_premium

        assert data["recommendation"] is not None
        assert len(data["recommendation"]["reasons"]) > 0

        user_messages = [
            m["content"] for m in data["messages"] if m["role"] == "user"
        ]
        assert (
            "hola, quiero proteger a mi familia, vivimos en casa propia en Bogotá"
            in user_messages
        )
        assert "listo, ¿cuánto me costaría?" in user_messages


class TestAfiliadoPorDocumento:
    FIXTURE_CSV = (
        "SERIE;GENERO;RANGO_EDAD;RANGO_SALARIO;SEGMENTO_HOGAR;"
        "SEGMENTO_POBLACION;CIUDAD;SEÑAL_CONSUMO_1;SEÑAL_CONSUMO_2;"
        "SEÑAL_CONSUMO_3;SEÑAL_CONSUMO_4;SEÑAL_CONSUMO_5\n"
        "A001;M;26-40;2-4M;3;TRABAJADOR;Bogotá;1;0;1;0;1\n"
    )

    def setup_method(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        self.tmp.write(self.FIXTURE_CSV)
        self.tmp.close()

    def teardown_method(self) -> None:
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_afiliado_por_documento(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "affiliate_csv_path", self.tmp.name)

        session_id = _create_session()

        script = [
            GeminiReply(
                kind="tool_call",
                tool_name="perfilar_cliente",
                tool_args={"document_number": "A001"},
                thought_signature="sig-1",
            ),
            GeminiReply(
                kind="text",
                text="Te ubico en nuestra base, ya tengo tu perfil",
            ),
        ]
        llm = _scripted_llm(script)
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        response = client.post(
            f"/api/v1/conversations/{session_id}/message",
            json={"content": "hola, mi cédula es A001"},
        )
        assert response.status_code == 200, response.text

        get_resp = client.get(f"/api/v1/conversations/{session_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()

        assert data["profile"] is not None
        assert data["profile"]["stratum"] == 3
        assert data["profile"]["age_range"] == "26-40"


class TestFlujoCompletoHastaCierre:
    def test_flujo_completo_hasta_cierre(self, monkeypatch) -> None:
        session_id = _create_session()

        script = [
            GeminiReply(
                kind="tool_call",
                tool_name="perfilar_cliente",
                tool_args=dict(FAVORABLE_ARGS),
                thought_signature="sig-1",
            ),
            GeminiReply(
                kind="text",
                text="¡Con gusto! Cuéntame, ¿cuánto te gustaría cotizar?",
            ),
            GeminiReply(
                kind="tool_call",
                tool_name="recomendar_seguro",
                tool_args={},
                thought_signature="sig-2",
            ),
            GeminiReply(
                kind="tool_call",
                tool_name="cotizar",
                tool_args={},
                thought_signature="sig-3",
            ),
            GeminiReply(
                kind="text",
                text="Tu prima mensual es la de la cotización",
            ),
            GeminiReply(
                kind="tool_call",
                tool_name="cerrar_venta",
                tool_args={"consentimiento": True},
                thought_signature="sig-4",
            ),
            GeminiReply(
                kind="text",
                text="¡Listo! Tu solicitud quedó lista para pago",
            ),
        ]
        llm = _scripted_llm(script)
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        turno_1 = client.post(
            f"/api/v1/conversations/{session_id}/message",
            json={
                "content": (
                    "hola, quiero proteger a mi familia, vivimos en casa "
                    "propia en Bogotá"
                )
            },
        )
        assert turno_1.status_code == 200, turno_1.text

        turno_2 = client.post(
            f"/api/v1/conversations/{session_id}/message",
            json={"content": "listo, ¿cuánto me costaría?"},
        )
        assert turno_2.status_code == 200, turno_2.text

        turno_3 = client.post(
            f"/api/v1/conversations/{session_id}/message",
            json={"content": "sí, acepto, quiero cerrarlo"},
        )
        assert turno_3.status_code == 200, turno_3.text

        assert len(llm.calls) == 7

        get_resp = client.get(f"/api/v1/conversations/{session_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()

        assert data["state"] == "ready_for_payment"
        assert data["application"] is not None
        assert data["application"]["consent_timestamp"]

        assert (
            data["application"]["quote"]["monthly_premium"]
            == data["quote"]["monthly_premium"]
        )
