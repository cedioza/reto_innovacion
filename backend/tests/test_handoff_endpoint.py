"""Tests de la Fase 1 de E2 (aseguradora simulada): `GET /api/v1/handoff/{token}`.

Cubre `.claude/analysis/plans/20260725-e2-pagina-aseguradora-simulada.plan.md`
(Fase 1). Estos tests FIJAN el comportamiento que la implementación debe dejar
listo:

1. Endpoint público `GET /api/v1/handoff/{token}` -> 200 con un
   `HandoffSummary` **sanitizado** (nunca `email`, `profile` ni `session_id`)
   cuando el token existe, y 404 cuando no existe.
2. Camino REST (`POST /consent` con email) y camino tool (`cerrar_venta` vía
   `execute_tool`, sin LLM real) deben resolver por el MISMO token contra el
   MISMO repositorio — hoy `agent_tools._cerrar_venta` crea un
   `ConsentService()` nuevo por llamada (repo por instancia), así que el test
   del camino tool es el que fija el singleton de módulo `consent_service`
   que el plan pide en `app/services/consent.py`.

RED esperado antes de implementar: la ruta `/api/v1/handoff/{token}` no
existe todavía, así que TODOS los `GET` de este archivo (incluido el del
token inventado) hoy devuelven 404 por defecto de FastAPI — es la razón
correcta de fallo para los tests que esperan 200 (el de 404 "pasa de gratis",
se anota en el reporte, no es señal de que la Fase 1 ya esté hecha).

Convención de mockeo: `resend_client.send_email` SIEMPRE se mockea (cero red
real), mismo patrón que `tests/test_handoff_flow.py`.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.agent_tools import ToolContext, execute_tool
from app.services.integrations import resend_client

client = TestClient(app)


FAVORABLE_ARGS = {
    "property_type": "house",
    "zone": "urban",
    "stratum": 3,
    "age_range": "26-40",
}


def _mock_send_email_ok(monkeypatch):
    monkeypatch.setattr(
        resend_client,
        "send_email",
        lambda to, subject, html: {"ok": True, "id": "re_fake"},
    )


# ---------------------------------------------------------------------------
# 1: camino REST -- POST /consent con email -> GET /handoff/{token} -> 200.
# ---------------------------------------------------------------------------


def _seed_rest_application(monkeypatch) -> dict:
    """Siembra una solicitud vía endpoints estructurados (sin LLM).

    Devuelve el JSON de `ConsentedApplication` (incluye `handoff_token` y la
    `quote` vigente de la sesión, usada para comparar `monthly_premium`).
    """
    _mock_send_email_ok(monkeypatch)

    resp = client.post("/api/v1/conversations", json={})
    assert resp.status_code == 201
    session_id = resp.json()["session_id"]

    profile_resp = client.post(
        f"/api/v1/conversations/{session_id}/profile",
        json=dict(FAVORABLE_ARGS),
    )
    assert profile_resp.status_code == 200
    quote = profile_resp.json()["quote"]
    assert quote is not None

    accept_resp = client.post(f"/api/v1/conversations/{session_id}/accept")
    assert accept_resp.status_code == 200

    consent_resp = client.post(
        f"/api/v1/conversations/{session_id}/consent",
        json={"consent_given": True, "email": "x@y.co"},
    )
    assert consent_resp.status_code == 200, consent_resp.text
    application = consent_resp.json()
    application["_quote"] = quote
    return application


class TestHandoffPorCaminoRest:
    def test_get_handoff_por_token_devuelve_resumen_sanitizado(
        self, monkeypatch
    ):
        application = _seed_rest_application(monkeypatch)
        token = application["handoff_token"]
        assert token

        response = client.get(f"/api/v1/handoff/{token}")

        assert response.status_code == 200, response.text
        data = response.json()

        assert data["product_name"] == "Hogar Estándar"
        assert data["insurer_name"] == "Seguros Bolívar"
        assert (
            data["monthly_premium"]
            == application["_quote"]["monthly_premium"]
        )
        assert data["state"] == "ready_for_payment"


# ---------------------------------------------------------------------------
# 2: camino tool -- cerrar_venta (execute_tool) -> GET /handoff/{token} -> 200.
#
# Este es el test que FIJA el singleton compartido: hoy `_cerrar_venta`
# instancia `ConsentService()` nueva por llamada, con su propio
# `ApplicationRepository` en memoria, así que el token nunca resuelve contra
# el repositorio que usa el router del handoff (el de `conversation_service`).
# ---------------------------------------------------------------------------


def _build_full_funnel_ctx(session_id: str) -> ToolContext:
    ctx = ToolContext(session_id=session_id)
    execute_tool("perfilar_cliente", dict(FAVORABLE_ARGS), ctx)
    execute_tool("recomendar_seguro", {}, ctx)
    execute_tool("cotizar", {}, ctx)
    return ctx


class TestHandoffPorCaminoTool:
    def test_get_handoff_por_token_de_cerrar_venta_devuelve_200(
        self, monkeypatch
    ):
        _mock_send_email_ok(monkeypatch)

        ctx = _build_full_funnel_ctx("sesion-tool-handoff")
        result = execute_tool(
            "cerrar_venta",
            {"consentimiento": True, "email": "x@y.co"},
            ctx,
        )
        assert "error" not in result
        token = result.get("handoff_token")
        assert token

        response = client.get(f"/api/v1/handoff/{token}")

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["product_name"] == "Hogar Estándar"
        assert data["insurer_name"] == "Seguros Bolívar"
        assert data["monthly_premium"] == result["quote"]["monthly_premium"]
        assert data["state"] == "ready_for_payment"


# ---------------------------------------------------------------------------
# 3: privacidad -- la respuesta pública nunca expone email/profile/session_id.
# ---------------------------------------------------------------------------


class TestHandoffEsSanitizado:
    def test_respuesta_no_contiene_email_ni_profile_ni_session_id(
        self, monkeypatch
    ):
        application = _seed_rest_application(monkeypatch)
        token = application["handoff_token"]

        response = client.get(f"/api/v1/handoff/{token}")
        assert response.status_code == 200, response.text

        data = response.json()
        keys = set(data.keys())
        assert "email" not in keys
        assert "profile" not in keys
        assert "session_id" not in keys

        serialized = response.text
        assert "x@y.co" not in serialized
        assert application["session_id"] not in serialized


# ---------------------------------------------------------------------------
# 4: token inventado -> 404 (nunca 500).
# ---------------------------------------------------------------------------


class TestHandoffTokenInventado:
    def test_token_inventado_devuelve_404(self):
        response = client.get("/api/v1/handoff/no-existe-xyz")

        # NOTA para el reporte: mientras la ruta no exista, este assert pasa
        # "de gratis" por el 404 por defecto de FastAPI ante rutas
        # desconocidas -- no es señal de que la Fase 1 ya esté implementada.
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Fase 2: POST /api/v1/handoff/{token}/finalize -> estado `finalizada_demo`,
# idempotente. Cubre
# .claude/analysis/plans/20260725-e2-pagina-aseguradora-simulada.plan.md
# (Fase 2). RED esperado antes de implementar: `POST .../finalize` no existe
# -> 405 (la ruta base `/{token}` sí existe desde la Fase 1, pero solo
# soporta GET) o 404 si `/finalize` no matchea ningun path -- cualquiera de
# los dos es la razón correcta de fallo, ninguno es 200. El GET posterior
# de estos tests que espera `finalizada_demo` falla porque el estado del
# enum `ConversationState.FINALIZED_DEMO` todavía no existe (AttributeError
# en el helper de comparación / el valor jamás aparece en la respuesta).
# ---------------------------------------------------------------------------


class TestHandoffFinalize:
    def test_finalize_feliz_devuelve_200_con_estado_finalizada_demo(
        self, monkeypatch
    ):
        application = _seed_rest_application(monkeypatch)
        token = application["handoff_token"]

        response = client.post(f"/api/v1/handoff/{token}/finalize")

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["state"] == "finalizada_demo"

    def test_finalize_es_idempotente_segundo_post_devuelve_mismo_body(
        self, monkeypatch
    ):
        application = _seed_rest_application(monkeypatch)
        token = application["handoff_token"]

        first = client.post(f"/api/v1/handoff/{token}/finalize")
        assert first.status_code == 200, first.text

        second = client.post(f"/api/v1/handoff/{token}/finalize")
        assert second.status_code == 200, second.text

        assert second.json() == first.json()

    def test_get_handoff_posterior_al_finalize_refleja_finalizada_demo(
        self, monkeypatch
    ):
        application = _seed_rest_application(monkeypatch)
        token = application["handoff_token"]

        finalize_resp = client.post(f"/api/v1/handoff/{token}/finalize")
        assert finalize_resp.status_code == 200, finalize_resp.text

        get_resp = client.get(f"/api/v1/handoff/{token}")

        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["state"] == "finalizada_demo"

    def test_finalize_no_cambia_el_estado_de_la_sesion_de_conversacion(
        self, monkeypatch
    ):
        application = _seed_rest_application(monkeypatch)
        token = application["handoff_token"]
        session_id = application["session_id"]

        finalize_resp = client.post(f"/api/v1/handoff/{token}/finalize")
        assert finalize_resp.status_code == 200, finalize_resp.text

        session_resp = client.get(f"/api/v1/conversations/{session_id}")

        assert session_resp.status_code == 200, session_resp.text
        assert session_resp.json()["state"] == "ready_for_payment"

    def test_finalize_con_token_inventado_devuelve_404(self):
        response = client.post("/api/v1/handoff/no-existe-xyz/finalize")

        assert response.status_code == 404
