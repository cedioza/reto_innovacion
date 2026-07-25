"""Tests for `POST /api/v1/conversations/{session_id}/adjustments` — Fase 2 de D3.

Cubre `.claude/analysis/plans/
20260725-d3-tarjetas-recomendacion-cotizacion-comparador.plan.md` (Fase 2):

- Ruta nueva `POST /conversations/{session_id}/adjustments`, body
  `{"adjustments": [codigo, ...]}` -> 200 con `ConversationResponse` (mismo
  shape que `/message`).
- `ConversationService.apply_adjustments` recalcula la cotización desde el
  perfil de la sesión con los ajustes pedidos, deja `session.quote` = la
  propuesta (con `annual_premium`) y agrega/actualiza IN-PLACE el último
  mensaje `type="comparison"` con el payload
  `{actual, propuesta, diferencia_mensual, ajustes_disponibles}` (mismo shape
  que la tool `ajustar_comparar` de `app.services.agent_tools`).
- Negativos: sesión inexistente -> 404; sesión sin perfil/cotización previa
  -> 400; código de ajuste desconocido -> 400; body inválido -> 422.

Ninguno de estos comportamientos existe todavía (la ruta `.../adjustments` no
está registrada): es intencional que estos tests fallen con 404/405 (ruta
inexistente) donde se espera 200/400/422 — salvo el test de sesión
inexistente, que puede "pasar" de gratis porque ya hoy cualquier ruta
desconocida devuelve 404 (se anota en el reporte, no es una falsa señal de
que la Fase 2 esté implementada).

Cero LLM: las sesiones se siembran vía `POST /conversations` +
`POST .../profile` (que ya calcula la cotización base determinista), mismo
patrón de `tests/test_conversations_router.py`.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.conversation import ProfileData
from app.services.quote import QuoteService

client = TestClient(app)

# Perfil favorable (mismo usado en test_card_messages.py): sin recargo por
# edad (26-40 no dispara el multiplicador 1.15), house/urban/estrato 3.
PROFILE_BODY = {
    "property_type": "house",
    "zone": "urban",
    "stratum": 3,
    "age_range": "26-40",
}

PROFILE = ProfileData(
    property_type="house", zone="urban", stratum=3, age_range="26-40"
)


def _create_session() -> str:
    response = client.post("/api/v1/conversations", json={})
    assert response.status_code == 201
    return response.json()["session_id"]


def _create_session_with_quote() -> str:
    """Sesión con perfil ya cargado -> cotización base (sin ajustes)."""
    session_id = _create_session()
    response = client.post(
        f"/api/v1/conversations/{session_id}/profile", json=PROFILE_BODY
    )
    assert response.status_code == 200
    assert response.json()["quote"] is not None
    return session_id


def _comparison_messages(data: dict) -> list[dict]:
    return [m for m in data["messages"] if m.get("type") == "comparison"]


class TestApplyAdjustmentsHappyPath:
    def test_fire_alarm_recalculates_and_yields_comparison_card(self):
        session_id = _create_session_with_quote()

        actual_quote = QuoteService().calculate_quote(PROFILE)
        expected_propuesta = QuoteService().calculate_quote(
            PROFILE, ["fire_alarm"]
        )

        response = client.post(
            f"/api/v1/conversations/{session_id}/adjustments",
            json={"adjustments": ["fire_alarm"]},
        )

        assert response.status_code == 200
        data = response.json()

        # -- la propuesta queda como cotización vigente de la sesión --------
        assert data["quote"]["monthly_premium"] == round(
            actual_quote["monthly_premium"] * 0.85, 2
        )
        assert (
            data["quote"]["monthly_premium"]
            == expected_propuesta["monthly_premium"]
        )
        assert data["quote"]["annual_premium"] == expected_propuesta[
            "annual_premium"
        ]
        assert data["quote"]["annual_premium"] is not None

        # -- tarjeta comparison, única, al final -----------------------------
        comparisons = _comparison_messages(data)
        assert len(comparisons) == 1
        card = data["messages"][-1]
        assert card["type"] == "comparison"

        payload = card["payload"]
        assert payload["actual"] == actual_quote
        assert payload["propuesta"] == expected_propuesta
        expected_diff = round(
            expected_propuesta["monthly_premium"]
            - actual_quote["monthly_premium"],
            2,
        )
        assert payload["diferencia_mensual"] == expected_diff
        assert len(payload["ajustes_disponibles"]) == 3
        codes = {a["code"] for a in payload["ajustes_disponibles"]}
        assert codes == {"fire_alarm", "security_system", "high_value"}


class TestApplyAdjustmentsIdempotentCard:
    def test_two_consecutive_calls_keep_a_single_comparison_card(self):
        session_id = _create_session_with_quote()

        first = client.post(
            f"/api/v1/conversations/{session_id}/adjustments",
            json={"adjustments": ["fire_alarm"]},
        )
        assert first.status_code == 200
        assert len(_comparison_messages(first.json())) == 1

        second = client.post(
            f"/api/v1/conversations/{session_id}/adjustments",
            json={"adjustments": ["security_system"]},
        )
        assert second.status_code == 200
        data = second.json()

        # Sigue habiendo UNA sola tarjeta comparison (actualizada in-place).
        assert len(_comparison_messages(data)) == 1

        # La sesión refleja la última propuesta (security_system, no acumula
        # con fire_alarm: cada llamada recalcula desde el perfil base).
        expected_second_propuesta = QuoteService().calculate_quote(
            PROFILE, ["security_system"]
        )
        assert (
            data["quote"]["monthly_premium"]
            == expected_second_propuesta["monthly_premium"]
        )

        card = data["messages"][-1]
        assert card["type"] == "comparison"
        # "actual" del segundo turno es la propuesta que dejó el primero.
        expected_first_propuesta = QuoteService().calculate_quote(
            PROFILE, ["fire_alarm"]
        )
        assert card["payload"]["actual"] == expected_first_propuesta
        assert card["payload"]["propuesta"] == expected_second_propuesta


class TestApplyAdjustmentsEmptyList:
    def test_empty_adjustments_returns_baseline_quote_with_card(self):
        session_id = _create_session_with_quote()
        baseline = QuoteService().calculate_quote(PROFILE)

        response = client.post(
            f"/api/v1/conversations/{session_id}/adjustments",
            json={"adjustments": []},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["quote"]["monthly_premium"] == baseline["monthly_premium"]
        assert data["quote"]["annual_premium"] == baseline["annual_premium"]

        card = data["messages"][-1]
        assert card["type"] == "comparison"
        assert card["payload"]["actual"] == baseline
        assert card["payload"]["propuesta"] == baseline
        assert card["payload"]["diferencia_mensual"] == 0.0
        assert len(card["payload"]["ajustes_disponibles"]) == 3


class TestApplyAdjustmentsNegatives:
    def test_unknown_session_returns_404(self):
        response = client.post(
            "/api/v1/conversations/no-existe/adjustments",
            json={"adjustments": ["fire_alarm"]},
        )
        # NOTA para el reporte: esta aserción puede pasar "de gratis" incluso
        # sin la ruta implementada, porque una ruta inexistente en FastAPI ya
        # responde 404 por defecto. No es una señal fiable de que la Fase 2
        # esté implementada; las demás clases de este archivo sí lo son.
        assert response.status_code == 404

    def test_session_without_prior_quote_returns_400(self):
        session_id = _create_session()  # sin /profile: sin quote

        response = client.post(
            f"/api/v1/conversations/{session_id}/adjustments",
            json={"adjustments": ["fire_alarm"]},
        )

        assert response.status_code == 400

    def test_unknown_adjustment_code_returns_400(self):
        session_id = _create_session_with_quote()

        response = client.post(
            f"/api/v1/conversations/{session_id}/adjustments",
            json={"adjustments": ["no_existe"]},
        )

        assert response.status_code == 400

    def test_missing_adjustments_field_returns_422(self):
        session_id = _create_session_with_quote()

        response = client.post(
            f"/api/v1/conversations/{session_id}/adjustments",
            json={},
        )

        assert response.status_code == 422

    def test_adjustments_wrong_type_returns_422(self):
        session_id = _create_session_with_quote()

        response = client.post(
            f"/api/v1/conversations/{session_id}/adjustments",
            json={"adjustments": "fire_alarm"},
        )

        assert response.status_code == 422
