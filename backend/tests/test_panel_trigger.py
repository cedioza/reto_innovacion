"""Tests for the proactive-trigger endpoint (plan G3, Fase 2 — RED).

Covers `ProactiveService.trigger` (new method) and the endpoint that exposes
it:

  ProactiveService.trigger(cohorte_id, serie)
    -> valida cohorte (COHORTS) y afiliado (AffiliateService.lookup)
    -> conversation_service.create(ConversationCreate(document_number=serie))
       (perfil precargado desde la base real)
    -> corre PropensityService sobre el perfil, setea `recommendation`
    -> agrega 2 mensajes assistant deterministas: apertura de texto (incluye
       el `criterio_humano` de la cohorte y el nombre del producto) y una
       tarjeta `type="recommendation"` con {product_id, product_name, reasons}
    -> POST /api/v1/panel/cohortes/{cohorte_id}/disparar, body {"serie": ...}

This module is written before `ProactiveService.trigger` exists (Fase 1 only
shipped `list_cohorts`) and before the `/disparar` route is added to
`app.api.routes.panel`, so it is expected to fail RED with:
  - `AttributeError: 'ProactiveService' object has no attribute 'trigger'`
    for the service-level tests, and
  - 404/405 (route not registered yet) for the endpoint tests —
    until Fase 2 implements the trigger chain.

Engine pattern mirrors `test_panel_cohorts.py`: an isolated, seeded SQLite
in-memory engine injected via `monkeypatch.setattr(db_module, "get_engine",
...)`, since `ProactiveService`/`AffiliateService`/`conversation_service` all
build their repositories with no explicit engine and resolve it lazily via
`app.repositories.db.get_engine()` on every call.
"""

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine
from fastapi.testclient import TestClient

from app.models.affiliate_record import AffiliateRecord
from app.repositories import db as db_module
from app.repositories.db import init_db
from app.services.proactive import COHORTS, ProactiveService
from app.services.conversation import conversation_service
from app.main import app

COHORT_ID = "familias-jovenes-drogueria"
SERIE = "S-A1"


def _make_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    return engine


def _seed_affiliate(engine) -> None:
    """Seeds a single affiliate matching the `familias-jovenes-drogueria` cohort."""
    with Session(engine) as session:
        session.add(
            AffiliateRecord(
                serie=SERIE,
                age_range="20-35",
                household_segment="LAMBDA",
                uses_drogueria=True,
                uses_vivienda=False,
                sint_tiene_vehiculo=False,
            )
        )
        session.commit()


def _criterio_humano(cohorte_id: str) -> str:
    return next(c["criterio_humano"] for c in COHORTS if c["id"] == cohorte_id)


class TestProactiveServiceTrigger:
    def setup_method(self) -> None:
        self.engine = _make_engine()
        _seed_affiliate(self.engine)

    def test_trigger_returns_session_and_product(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        service = ProactiveService()

        result = service.trigger(COHORT_ID, SERIE)

        assert result["session_id"]
        assert result["serie"] == SERIE
        assert result["producto"]["product_id"]
        assert result["producto"]["product_name"]
        assert result["mensaje_apertura"]

    def test_trigger_session_has_profile_and_recommendation(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        service = ProactiveService()

        result = service.trigger(COHORT_ID, SERIE)
        session = conversation_service.get(result["session_id"])

        assert session is not None
        assert session.profile is not None
        assert session.recommendation is not None

    def test_trigger_opening_message_includes_cohort_reason(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        service = ProactiveService()

        result = service.trigger(COHORT_ID, SERIE)
        session = conversation_service.get(result["session_id"])

        assert session is not None
        assert len(session.messages) >= 2

        opening = session.messages[0]
        assert opening.role == "assistant"
        assert opening.type == "text"
        assert _criterio_humano(COHORT_ID) in opening.content
        assert result["producto"]["product_name"] in opening.content
        assert all(msg.timestamp for msg in session.messages)

    def test_trigger_appends_recommendation_card(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        service = ProactiveService()

        result = service.trigger(COHORT_ID, SERIE)
        session = conversation_service.get(result["session_id"])

        assert session is not None
        card = next((m for m in session.messages if m.type == "recommendation"), None)

        assert card is not None
        assert card.role == "assistant"
        assert card.payload is not None
        assert {"product_id", "product_name", "reasons"} <= card.payload.keys()
        assert card.payload["product_id"] == result["producto"]["product_id"]

    def test_trigger_unknown_cohort_raises(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        service = ProactiveService()

        with pytest.raises(ValueError, match="Cohort not found"):
            service.trigger("no-existe", SERIE)

    def test_trigger_unknown_serie_raises(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        service = ProactiveService()

        with pytest.raises(ValueError, match="Affiliate not found"):
            service.trigger(COHORT_ID, "NO-EXISTE")


class TestPanelTriggerEndpoint:
    def setup_method(self) -> None:
        self.engine = _make_engine()
        _seed_affiliate(self.engine)
        self.client = TestClient(app)

    def test_trigger_endpoint_happy(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)

        response = self.client.post(
            f"/api/v1/panel/cohortes/{COHORT_ID}/disparar",
            json={"serie": SERIE},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["session_id"]
        assert body["serie"] == SERIE
        assert body["producto"]["product_id"]
        assert body["producto"]["product_name"]
        assert body["mensaje_apertura"]

        follow_up = self.client.get(f"/api/v1/conversations/{body['session_id']}")
        assert follow_up.status_code == 200

    def test_trigger_unknown_cohort_endpoint_404(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)

        response = self.client.post(
            "/api/v1/panel/cohortes/no-existe/disparar",
            json={"serie": SERIE},
        )

        assert response.status_code == 404

    def test_trigger_unknown_serie_endpoint_404(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)

        response = self.client.post(
            f"/api/v1/panel/cohortes/{COHORT_ID}/disparar",
            json={"serie": "NO-EXISTE"},
        )

        assert response.status_code == 404

    def test_trigger_missing_serie_body_endpoint_422(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)

        response = self.client.post(
            f"/api/v1/panel/cohortes/{COHORT_ID}/disparar",
            json={},
        )

        assert response.status_code == 422
