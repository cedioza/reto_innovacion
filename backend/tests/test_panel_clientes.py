"""Tests for the panel clientes search + detail endpoints (plan G4, Fase 3 — RED).

Covers, end-to-end via `TestClient`, the two read-only endpoints that the
(not yet existing) `PanelClientesService` will expose:

  GET /api/v1/panel/clientes?q=<texto>
      -> listado buscable de clientes (afiliados con conversación/solicitud
         y prospectos sin serie), agrupados por `cliente_id` (serie si la
         sesión la tiene, si no `session_id`).
  GET /api/v1/panel/clientes/{cliente_id}
      -> ficha de detalle: perfil fusionado con origen (`base`/`sintetico`/
         `conversacion`/`declarado`), funnel ofrecido/cotizado/solicitado y
         conversaciones asociadas.

Ambas rutas y el service que las respalda (`app.services.panel_clientes`)
todavía no existen (Fase 3 del plan G4). Este módulo se escribe antes, así
que se espera que falle en rojo por la razón correcta: la ruta no está
registrada bajo `/api/v1/panel/clientes` (404 en vez de 200) — no por un
error de import o de sintaxis. No se importa `app.services.panel_clientes`
aquí a propósito, para no acoplar la colección de tests a un módulo que aún
no existe.

Fase 1 (serie persistida en `ConversationResponse.serie`) y Fase 2 (métodos
`list_all`/`list_sessions`/`list_applications`/`all_fields` en repos y
services) ya están implementadas — se usan libremente para sembrar datos.

Engine pattern: mirrors `test_panel_trigger.py` / `test_panel_cohorts.py` —
un engine SQLite in-memory aislado por método de test (fresco en cada
`setup_method`), inyectado a los repos explícitamente al sembrar y
monkeypatcheado sobre `app.repositories.db.get_engine` para que el
`TestClient`/los services (que construyen sus propios repos sin engine
explícito, resolviéndolo perezosamente) lean y escriban contra el mismo
engine sembrado.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.models.affiliate_record import AffiliateRecord
from app.repositories import db as db_module
from app.repositories.applications import ApplicationRepository
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
from app.services.enrichment import EnrichmentService
from app.main import app


def _make_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    return engine


def _seed_affiliate(engine, serie: str, **overrides) -> None:
    defaults = dict(
        serie=serie,
        age_range="26-40",
        gender="F",
        household_segment="RHO",
        uses_drogueria=False,
        uses_vivienda=False,
        sint_tiene_vehiculo=False,
    )
    defaults.update(overrides)
    with Session(engine) as session:
        session.add(AffiliateRecord(**defaults))
        session.commit()


def _make_conversation(
    session_id: str,
    *,
    serie: str | None = None,
    messages: list[Message] | None = None,
    profile: ProfileData | None = None,
    recommendation: Recommendation | None = None,
    quote: QuoteDetail | None = None,
    state: ConversationState = ConversationState.COLLECTING_PROFILE,
) -> ConversationResponse:
    return ConversationResponse(
        session_id=session_id,
        state=state,
        messages=messages or [],
        profile=profile,
        recommendation=recommendation,
        quote=quote,
        next_action="siguiente paso",
        serie=serie,
    )


def _save_conversation(engine, session: ConversationResponse) -> None:
    ConversationRepository(engine=engine).save(session.session_id, session)


def _make_application(
    session_id: str,
    *,
    product_id: str = "hogar-estandar",
    email: str | None = None,
    state: ConversationState = ConversationState.READY_FOR_PAYMENT,
) -> ConsentedApplication:
    profile = ProfileData(age_range="26-40")
    recommendation = Recommendation(
        product_id=product_id,
        product_name="Seguro de prueba",
        reasons=[{"factor": "perfil", "detalle": "coincide"}],
    )
    quote = QuoteDetail(
        base_amount=50000,
        monthly_premium=58000,
        annual_premium=696000,
        coverage_details=["cobertura basica"],
        exclusions=["exclusion"],
    )
    return ConsentedApplication(
        session_id=session_id,
        product_id=product_id,
        profile=profile,
        recommendation=recommendation,
        quote=quote,
        consent_timestamp=datetime.now(timezone.utc).isoformat(),
        state=state,
        email=email,
        handoff_token=f"tok-{session_id}",
        insurer_name="Aseguradora Demo",
    )


def _save_application(engine, application: ConsentedApplication, evidence_hash: str = "hash-test") -> None:
    ApplicationRepository(engine=engine).save(application.session_id, evidence_hash, application)


class TestPanelClientesLista:
    def setup_method(self) -> None:
        self.engine = _make_engine()
        self.client = TestClient(app)

    def test_clientes_lista_afiliado_con_conversacion_y_solicitud(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        _seed_affiliate(self.engine, "S001")

        session = _make_conversation(
            "sess-s001",
            serie="S001",
            messages=[Message(role="user", content="hola, quiero un seguro")],
            state=ConversationState.FINALIZED_DEMO,
        )
        _save_conversation(self.engine, session)

        application = _make_application(
            "sess-s001", email="ana@mail.com", state=ConversationState.FINALIZED_DEMO
        )
        _save_application(self.engine, application)

        response = self.client.get("/api/v1/panel/clientes")

        assert response.status_code == 200
        body = response.json()
        by_id = {cliente["cliente_id"]: cliente for cliente in body["clientes"]}
        assert "S001" in by_id

        cliente = by_id["S001"]
        assert cliente["serie"] == "S001"
        assert cliente["afiliado"] is True
        assert cliente["conversaciones"] == 1
        assert cliente["solicitudes"] == 1
        assert cliente["ultimo_estado"] == "finalizada_demo"

    def test_clientes_busqueda_por_serie_exacta(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        _seed_affiliate(self.engine, "S001")
        _seed_affiliate(self.engine, "S002")

        _save_conversation(
            self.engine,
            _make_conversation(
                "sess-s001",
                serie="S001",
                messages=[Message(role="user", content="hola")],
            ),
        )
        _save_conversation(
            self.engine,
            _make_conversation(
                "sess-s002",
                serie="S002",
                messages=[Message(role="user", content="hola")],
            ),
        )

        response = self.client.get("/api/v1/panel/clientes", params={"q": "S001"})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert len(body["clientes"]) == 1
        assert body["clientes"][0]["cliente_id"] == "S001"

    def test_clientes_busqueda_por_email(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        _seed_affiliate(self.engine, "S003")

        _save_conversation(
            self.engine,
            _make_conversation(
                "sess-s003",
                serie="S003",
                messages=[Message(role="user", content="hola")],
            ),
        )
        application = _make_application("sess-s003", email="ana@mail.com")
        _save_application(self.engine, application)

        response = self.client.get("/api/v1/panel/clientes", params={"q": "ana@"})

        assert response.status_code == 200
        body = response.json()
        by_id = {cliente["cliente_id"]: cliente for cliente in body["clientes"]}
        assert "S003" in by_id
        assert by_id["S003"]["email"] == "ana@mail.com"

    def test_clientes_prospecto_sin_serie_aparece(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        session_id = "sess-prospecto-1"

        _save_conversation(
            self.engine,
            _make_conversation(
                session_id,
                serie=None,
                messages=[Message(role="user", content="hola")],
            ),
        )

        response = self.client.get("/api/v1/panel/clientes")

        assert response.status_code == 200
        body = response.json()
        by_id = {cliente["cliente_id"]: cliente for cliente in body["clientes"]}
        assert session_id in by_id
        assert by_id[session_id]["afiliado"] is False
        assert by_id[session_id]["serie"] is None

    def test_clientes_bd_vacia(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)

        response = self.client.get("/api/v1/panel/clientes", params={"q": "zzz-no-match"})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 0
        assert body["clientes"] == []


class TestPanelClientesFicha:
    def setup_method(self) -> None:
        self.engine = _make_engine()
        self.client = TestClient(app)

    def test_ficha_afiliado_perfil_origenes_y_funnel(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        _seed_affiliate(self.engine, "S001", age_range="26-40", sint_tiene_vehiculo=True)

        session_id = "sess-s001-ficha"
        recommendation = Recommendation(
            product_id="movilidad-conductor",
            product_name="Seguro Movilidad Conductor",
            reasons=[{"factor": "vehiculo", "detalle": "tiene vehiculo"}],
        )
        quote = QuoteDetail(
            base_amount=50000,
            monthly_premium=58000,
            annual_premium=696000,
            coverage_details=["cobertura basica"],
            exclusions=["exclusion"],
        )
        session = _make_conversation(
            session_id,
            serie="S001",
            messages=[
                # role="user" primero -> tipo "recomendacion" (no proactivo).
                Message(role="user", content="hola quiero un seguro de auto"),
                Message(role="assistant", content="te recomiendo este producto"),
            ],
            recommendation=recommendation,
            quote=quote,
            state=ConversationState.QUOTE_READY,
        )
        _save_conversation(self.engine, session)

        EnrichmentService(engine=self.engine).record(session_id, "S001", "hijos", "2")

        application = _make_application(
            session_id,
            product_id="movilidad-conductor",
            email="ana@mail.com",
            state=ConversationState.FINALIZED_DEMO,
        )
        _save_application(self.engine, application)

        response = self.client.get("/api/v1/panel/clientes/S001")

        assert response.status_code == 200
        body = response.json()
        assert body["cliente_id"] == "S001"
        assert body["afiliado"] is True
        assert body["fuente_perfil"] == "base"

        origenes = {item["campo"]: item["origen"] for item in body["perfil"]}
        assert origenes.get("age_range") == "base"
        assert origenes.get("sint_tiene_vehiculo") == "sintetico"
        assert origenes.get("hijos") == "conversacion"

        ofertas = body["ofertas"]
        oferta = next((o for o in ofertas if o["session_id"] == session_id), None)
        assert oferta is not None
        assert oferta["product_id"] == "movilidad-conductor"
        assert oferta["tipo"] == "recomendacion"

        cotizaciones = body["cotizaciones"]
        cotizacion = next((c for c in cotizaciones if c["session_id"] == session_id), None)
        assert cotizacion is not None
        assert cotizacion["monthly_premium"] == 58000

        solicitudes = body["solicitudes"]
        solicitud = next((s for s in solicitudes if s["session_id"] == session_id), None)
        assert solicitud is not None
        assert solicitud["estado"] == "finalizada_demo"
        assert solicitud["comprado"] is True
        assert solicitud["email"] == "ana@mail.com"

    def test_ficha_prospecto_declarado(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        session_id = "sess-prospecto-ficha"
        profile = ProfileData(age_range="18-25", property_type="apartamento", source="declarado")

        session = _make_conversation(
            session_id,
            serie=None,
            messages=[Message(role="user", content="hola")],
            profile=profile,
            state=ConversationState.COLLECTING_PROFILE,
        )
        _save_conversation(self.engine, session)

        response = self.client.get(f"/api/v1/panel/clientes/{session_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["cliente_id"] == session_id
        assert body["afiliado"] is False
        assert body["fuente_perfil"] == "declarado"

    def test_ficha_cliente_inexistente_404(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)

        response = self.client.get("/api/v1/panel/clientes/no-existe-xyz")

        assert response.status_code == 404
