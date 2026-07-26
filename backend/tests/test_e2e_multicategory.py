"""E2E del funnel REST (sin LLM) sobre el motor de propensión multicategoría.

Fase 3 del plan B3, paso TDD "tests primero" — TDD-light, RED antes de
implementar: `ConversationService.update_profile` todavía hardcodea
"Hogar Estándar" como `product_name` y cotiza siempre contra
"hogar-estandar" (ignorando el `product_id` que ya calcula el motor de
propensión multicategoría), y `apply_adjustments` valida los códigos de
ajuste siempre contra "hogar-estandar" en vez del producto recomendado en
`session.recommendation`. Estos tests describen el comportamiento objetivo
tras la Fase 3 y fallan hoy por la razón correcta (el código de producción
de `app/services/conversation.py` aún no resuelve el producto recomendado).

Estilo: `TestClient` directo sobre `app.main.app`, mismo patrón que
`tests/test_e2e_happy_path.py`.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestFunnelMulticategoriaCreditoVidaDeudor:
    """Perfil con crédito vigente (41-55, sin propiedad) -> credito-vida-deudor."""

    def test_profile_recomienda_y_cotiza_credito_vida_deudor(self) -> None:
        resp = client.post("/api/v1/conversations", json={})
        assert resp.status_code == 201
        session_id = resp.json()["session_id"]

        resp = client.post(
            f"/api/v1/conversations/{session_id}/profile",
            json={"age_range": "41-55", "has_credit": True},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["recommendation"]["product_id"] == "credito-vida-deudor"
        assert (
            data["recommendation"]["product_name"] == "Crédito Vida Deudor"
        )
        assert len(data["recommendation"]["reasons"]) >= 2
        assert data["quote"]["monthly_premium"] == 25000.0

    def test_continua_hasta_consentimiento_con_producto_recomendado(
        self,
    ) -> None:
        resp = client.post("/api/v1/conversations", json={})
        session_id = resp.json()["session_id"]

        client.post(
            f"/api/v1/conversations/{session_id}/profile",
            json={"age_range": "41-55", "has_credit": True},
        )

        resp = client.post(f"/api/v1/conversations/{session_id}/accept")
        assert resp.status_code == 200, resp.text

        resp = client.post(
            f"/api/v1/conversations/{session_id}/consent",
            json={"consent_given": True},
        )
        assert resp.status_code == 200, resp.text
        application_data = resp.json()
        assert application_data["product_id"] == "credito-vida-deudor"


class TestFunnelMulticategoriaAjustesNoCruzanProducto:
    """Un ajuste de hogar no aplica al producto recomendado (movilidad-auto)."""

    def test_ajuste_de_hogar_en_perfil_de_movilidad_devuelve_400(self) -> None:
        resp = client.post("/api/v1/conversations", json={})
        session_id = resp.json()["session_id"]

        resp = client.post(
            f"/api/v1/conversations/{session_id}/profile",
            json={"age_range": "26-40", "has_vehicle": True},
        )
        assert resp.status_code == 200, resp.text

        resp = client.post(
            f"/api/v1/conversations/{session_id}/adjustments",
            json={"adjustments": ["fire_alarm"]},
        )

        assert resp.status_code == 400, resp.text
