"""Tests for GET /api/v1/panel/metricas (plan G5, Fase de red — funnel de ventas).

Cubre el endpoint nuevo del panel que resume, para las 7 conversaciones de
demo sembradas por `app.scripts.seed_demo.sembrar` (H4), el embudo global
(recomendado -> cotizado -> consentimiento -> comprado) y el mismo embudo
desagregado por producto y por corte de afiliación (`profile.source`).

`app.services.panel_metrics` y la ruta `/api/v1/panel/metricas` todavía no
existen al escribir esta suite, así que TODO el archivo falla hoy con 404 en
cada request al endpoint nuevo (la app sí levanta: `/api/v1/panel/cohortes`
sigue existiendo) — es la razón correcta de fallo hasta que la siguiente
tarea implemente schema + service + router. Por eso cada test verifica
`response.status_code == 200` como primera aserción: así el rojo actual es
inequívocamente por el 404, no por un `KeyError` al leer el body.

Engine pattern: SQLite in-memory fresco por test (`StaticPool`), con
`app.repositories.db.get_engine` parcheado — mismo patrón que
`test_seed_demo.py` / `test_panel_cohorts.py`, necesario porque `sembrar()`
(vía `ConsentService`) y `ConversationRepository()` sin engine explícito
resuelven siempre el engine global.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.main import app
from app.models.conversation import ConversationRecord
from app.repositories import db as db_module
from app.repositories.conversations import ConversationRepository
from app.repositories.db import init_db
from app.schemas.conversation import (
    ConsentedApplication,
    ConversationResponse,
    ConversationState,
    Message,
    ProfileData,
    QuoteDetail,
    Recommendation,
)
from app.scripts.seed_demo import sembrar
from app.services.catalog import CatalogService

ETAPAS_EN_CERO = {
    "recomendado": 0,
    "cotizado": 0,
    "consentimiento": 0,
    "comprado": 0,
}

TASAS_EN_CERO = {
    "cotizado_sobre_recomendado": 0.0,
    "consentimiento_sobre_cotizado": 0.0,
    "comprado_sobre_consentimiento": 0.0,
    "comprado_sobre_recomendado": 0.0,
}


def _make_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    return engine


def _producto_hogar():
    return next(
        p for p in CatalogService().list_products() if p.category == "hogar"
    )


class TestPanelMetricasEndpoint:
    def setup_method(self) -> None:
        self.engine = _make_engine()
        self.client = TestClient(app)

    def test_db_vacia_responde_200_con_ceros(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)

        response = self.client.get("/api/v1/panel/metricas")

        assert response.status_code == 200
        body = response.json()

        assert body["fuente"] == "sin_datos"

        totales = body["totales"]
        assert totales["conversaciones"] == 0
        assert totales["recomendadas"] == 0
        assert totales["cotizadas"] == 0
        assert totales["con_consentimiento"] == 0
        assert totales["compradas"] == 0
        assert totales["conversion_global"] == 0.0

        funnel = body["funnel_por_producto"]
        assert len(funnel) == 5
        for producto in funnel:
            assert producto["etapas"] == ETAPAS_EN_CERO
            assert producto["tasas"] == TASAS_EN_CERO

    def test_con_seed_h4_cuadra_exacto(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        sembrar(engine=self.engine)

        response = self.client.get("/api/v1/panel/metricas")

        assert response.status_code == 200
        body = response.json()

        assert body["fuente"] == "postgres"

        totales = body["totales"]
        assert totales["conversaciones"] == 7
        assert totales["recomendadas"] == 7
        assert totales["cotizadas"] == 7
        assert totales["con_consentimiento"] == 6
        assert totales["compradas"] == 5
        assert totales["conversion_global"] == 0.71

        funnel = body["funnel_por_producto"]
        assert len(funnel) == 5
        for producto in funnel:
            assert producto["etapas"]["comprado"] == 1

        suma_recomendado = sum(p["etapas"]["recomendado"] for p in funnel)
        assert suma_recomendado == 7

    def test_corte_afiliacion_con_seed(self, monkeypatch) -> None:
        """Los perfiles sembrados por `sembrar()` no traen `source="base"`.

        Por semántica del contrato, `None` (lo que dejan los perfiles del
        seed) cae en el bucket "declarado", nunca en "base". Si esto cambiara
        en `seed_demo`, este test lo detectaría (falla en vez de forzar un
        número mágico) — ver nota en la aserción de cierre, que valida
        conservación contra los totales en lugar de asumir la partición.
        """
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        sembrar(engine=self.engine)

        response = self.client.get("/api/v1/panel/metricas")

        assert response.status_code == 200
        body = response.json()
        corte = body["corte_afiliacion"]

        assert corte["base"]["conversaciones"] == 0
        assert corte["declarado"]["conversaciones"] == 7
        assert corte["declarado"]["compradas"] == 5
        assert corte["declarado"]["conversion"] == 0.71

        totales = body["totales"]
        assert (
            corte["base"]["conversaciones"] + corte["declarado"]["conversaciones"]
            == totales["conversaciones"]
        )
        assert (
            corte["base"]["compradas"] + corte["declarado"]["compradas"]
            == totales["compradas"]
        )

    def test_fila_corrupta_no_tumba_el_endpoint(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        sembrar(engine=self.engine)

        with Session(self.engine) as session:
            session.add(
                ConversationRecord(
                    session_id="corrupta-1",
                    estado="collecting_profile",
                    data={"basura": True},
                )
            )
            session.commit()

        response = self.client.get("/api/v1/panel/metricas")

        assert response.status_code == 200
        body = response.json()
        assert body["totales"]["conversaciones"] == 7
        assert body["totales"]["compradas"] == 5

    def test_cinco_productos_siempre_presentes(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)

        producto_hogar = _producto_hogar()

        recommendation = Recommendation(
            product_id=producto_hogar.id,
            product_name=producto_hogar.name,
            reasons=[{"motivo": "perfil compatible con hogar"}],
        )
        quote = QuoteDetail(
            base_amount=45000.0,
            monthly_premium=45000.0,
            coverage_details=["Incendio"],
            exclusions=["Desgaste natural"],
        )
        profile = ProfileData(property_type="house", stratum=3, zone="urban")
        application = ConsentedApplication(
            session_id="hogar-comprado-1",
            product_id=producto_hogar.id,
            profile=profile,
            recommendation=recommendation,
            quote=quote,
            consent_timestamp="2026-07-25T10:00:00+00:00",
            state=ConversationState.FINALIZED_DEMO,
        )
        conversation = ConversationResponse(
            session_id="hogar-comprado-1",
            state=ConversationState.FINALIZED_DEMO,
            messages=[Message(role="user", content="Hola, quiero asegurar mi casa")],
            profile=profile,
            recommendation=recommendation,
            quote=quote,
            application=application,
            next_action="Tu solicitud quedó lista para pago con la aseguradora",
        )
        ConversationRepository(engine=self.engine).save(
            conversation.session_id, conversation
        )

        response = self.client.get("/api/v1/panel/metricas")

        assert response.status_code == 200
        body = response.json()
        funnel = body["funnel_por_producto"]
        assert len(funnel) == 5

        por_id = {p["product_id"]: p for p in funnel}
        assert por_id[producto_hogar.id]["etapas"]["comprado"] == 1

        for product_id, producto in por_id.items():
            if product_id == producto_hogar.id:
                continue
            assert producto["etapas"] == ETAPAS_EN_CERO
            assert producto["tasas"] == TASAS_EN_CERO

    def test_cohortes_sigue_intacto(self, monkeypatch) -> None:
        """Smoke de no-regresión: /panel/cohortes sigue vivo tras el cambio."""
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)

        response = self.client.get("/api/v1/panel/cohortes")

        assert response.status_code == 200
        body = response.json()
        assert "cohortes" in body
