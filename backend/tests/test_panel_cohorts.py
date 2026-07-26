"""Tests for the proactive-trigger cohort pipeline (plan G3, Fase 1 — RED).

Covers, bottom-up, the full chain that the panel endpoint will expose:

  AffiliateRepository.count_by_filters / sample_by_filters
    -> AffiliateService.count_cohort / sample_cohort (thin delegation)
    -> app.services.proactive.ProactiveService.list_cohorts (new module)
    -> GET /api/v1/panel/cohortes (new router `panel.py`, registered in main)

This module is written before `app.services.proactive` exists and before
`AffiliateRepository` grows `count_by_filters`/`sample_by_filters`, so
collection is expected to fail with `ModuleNotFoundError:
app.services.proactive` (the top-level import below) until Fase 2 of the
plan implements the repo/service/router chain — mirroring the RED pattern
already used by `test_affiliates_db.py` (plan C2, Fase 1).

Engine pattern mirrors `test_affiliates_db.py` (repo-level tests: explicit
engine injected via the constructor) and `test_agent_tools.py`
(service/endpoint-level tests: `AffiliateService()`/`ProactiveService()`
build their own repo with no engine, resolving it lazily via
`app.repositories.db.get_engine()` — monkeypatched per test to an isolated
SQLite in-memory engine so nothing touches the shared session-scoped engine
from `conftest.py`).

The three cohorts and their exact filter values come from the plan (base
real de afiliados, brain "01-Reto Seguros"):
  a) familias-jovenes-drogueria: age_range "20-35" + household_segment in
     ["LAMBDA", "RHO"] + uses_drogueria True.
  b) interes-vivienda: uses_vivienda True.
  c) movilidad-vehiculo: sint_tiene_vehiculo True.
"""

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine
from fastapi.testclient import TestClient

from app.models.affiliate_record import AffiliateRecord
from app.repositories import db as db_module
from app.repositories.affiliates import AffiliateRepository
from app.repositories.db import init_db
from app.services.affiliate import AffiliateService
from app.services.proactive import COHORTS, ProactiveService  # noqa: F401 (RED trigger)
from app.main import app


def _make_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    return engine


def _seed_cohort_fixtures(engine) -> None:
    """Seeds 9 rows: 2 clean members per cohort + 3 near-misses for (a).

    Near-misses (wrong segment / wrong age / drogueria False) must NOT be
    counted for cohorte (a), and must not accidentally satisfy (b) or (c)
    either (uses_vivienda/sint_tiene_vehiculo left False on them).
    """
    rows = [
        # -- cohorte (a): familias-jovenes-drogueria --------------------
        dict(
            serie="S-A1",
            age_range="20-35",
            household_segment="LAMBDA",
            uses_drogueria=True,
            uses_vivienda=False,
            sint_tiene_vehiculo=False,
        ),
        dict(
            serie="S-A2",
            age_range="20-35",
            household_segment="RHO",
            uses_drogueria=True,
            uses_vivienda=False,
            sint_tiene_vehiculo=False,
        ),
        # near-miss: household_segment fuera de la lista
        dict(
            serie="S-A-miss-segmento",
            age_range="20-35",
            household_segment="OMEGA",
            uses_drogueria=True,
            uses_vivienda=False,
            sint_tiene_vehiculo=False,
        ),
        # near-miss: age_range fuera de rango
        dict(
            serie="S-A-miss-edad",
            age_range="41-55",
            household_segment="LAMBDA",
            uses_drogueria=True,
            uses_vivienda=False,
            sint_tiene_vehiculo=False,
        ),
        # near-miss: no usa drogueria
        dict(
            serie="S-A-miss-drogueria",
            age_range="20-35",
            household_segment="RHO",
            uses_drogueria=False,
            uses_vivienda=False,
            sint_tiene_vehiculo=False,
        ),
        # -- cohorte (b): interes-vivienda -------------------------------
        dict(
            serie="S-B1",
            age_range="41-55",
            household_segment="OMEGA",
            uses_drogueria=False,
            uses_vivienda=True,
            sint_tiene_vehiculo=False,
        ),
        dict(
            serie="S-B2",
            age_range="26-40",
            household_segment="OMEGA",
            uses_drogueria=False,
            uses_vivienda=True,
            sint_tiene_vehiculo=False,
        ),
        # -- cohorte (c): movilidad-vehiculo ------------------------------
        dict(
            serie="S-C1",
            age_range="36-50",
            household_segment="OMEGA",
            uses_drogueria=False,
            uses_vivienda=False,
            sint_tiene_vehiculo=True,
        ),
        dict(
            serie="S-C2",
            age_range="56+",
            household_segment="OMEGA",
            uses_drogueria=False,
            uses_vivienda=False,
            sint_tiene_vehiculo=True,
        ),
    ]
    with Session(engine) as session:
        for row in rows:
            session.add(AffiliateRecord(**row))
        session.commit()


class TestCountByFilters:
    def setup_method(self) -> None:
        self.engine = _make_engine()
        _seed_cohort_fixtures(self.engine)
        self.repo = AffiliateRepository(engine=self.engine, csv_path="Z:\\no\\existe.csv")

    def test_igualdad_simple(self) -> None:
        assert self.repo.count_by_filters({"uses_vivienda": True}) == 2

    def test_lista_in(self) -> None:
        # LAMBDA/RHO aparece en S-A1, S-A2, S-A-miss-edad (LAMBDA) y
        # S-A-miss-drogueria (RHO) -> 4, independientemente de los otros
        # filtros de la cohorte.
        count = self.repo.count_by_filters(
            {"household_segment": ["LAMBDA", "RHO"]}
        )
        assert count == 4

    def test_combinado_cohorte_completa(self) -> None:
        filters = {
            "age_range": "20-35",
            "household_segment": ["LAMBDA", "RHO"],
            "uses_drogueria": True,
        }
        assert self.repo.count_by_filters(filters) == 2

    def test_bd_sin_filas_devuelve_cero(self) -> None:
        empty_engine = _make_engine()
        repo = AffiliateRepository(engine=empty_engine, csv_path="Z:\\no\\existe.csv")

        assert repo.count_by_filters({"uses_vivienda": True}) == 0


class TestSampleByFilters:
    def setup_method(self) -> None:
        self.engine = _make_engine()
        _seed_cohort_fixtures(self.engine)
        self.repo = AffiliateRepository(engine=self.engine, csv_path="Z:\\no\\existe.csv")

    def test_respeta_limit(self) -> None:
        sample = self.repo.sample_by_filters({"household_segment": ["LAMBDA", "RHO"]}, limit=2)

        assert len(sample) == 2

    def test_solo_devuelve_miembros_que_cumplen(self) -> None:
        sample = self.repo.sample_by_filters({"uses_vivienda": True}, limit=5)

        series = {record.serie for record in sample}
        assert series == {"S-B1", "S-B2"}
        assert all(record.uses_vivienda is True for record in sample)

    def test_bd_sin_filas_devuelve_lista_vacia(self) -> None:
        empty_engine = _make_engine()
        repo = AffiliateRepository(engine=empty_engine, csv_path="Z:\\no\\existe.csv")

        assert repo.sample_by_filters({"uses_vivienda": True}) == []


class TestAffiliateServiceCohortMethods:
    """`AffiliateService.count_cohort`/`sample_cohort` solo delegan al repo.

    `AffiliateService()` construye su `AffiliateRepository()` sin engine
    explícito (mismo patrón que `test_agent_tools.py`), así que se
    monkeypatchea `app.repositories.db.get_engine` a un engine sembrado
    propio de cada test.
    """

    def setup_method(self) -> None:
        self.engine = _make_engine()
        _seed_cohort_fixtures(self.engine)

    def test_count_cohort_delega_en_repo(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        service = AffiliateService()

        assert service.count_cohort({"uses_vivienda": True}) == 2

    def test_sample_cohort_delega_en_repo_y_respeta_limit(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        service = AffiliateService()

        sample = service.sample_cohort({"sint_tiene_vehiculo": True}, limit=1)

        assert len(sample) == 1
        assert sample[0].sint_tiene_vehiculo is True


class TestProactiveServiceListCohorts:
    def setup_method(self) -> None:
        self.engine = _make_engine()
        _seed_cohort_fixtures(self.engine)

    def test_list_cohorts_con_datos(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)
        service = ProactiveService()

        result = service.list_cohorts()

        assert result["fuente"] == "postgres"
        assert len(result["cohortes"]) == 3

        by_id = {c["id"]: c for c in result["cohortes"]}
        assert set(by_id) == {
            "familias-jovenes-drogueria",
            "interes-vivienda",
            "movilidad-vehiculo",
        }
        assert by_id["familias-jovenes-drogueria"]["total"] == 2
        assert by_id["interes-vivienda"]["total"] == 2
        assert by_id["movilidad-vehiculo"]["total"] == 2

        cohorte_a = by_id["familias-jovenes-drogueria"]
        assert cohorte_a["nombre"]
        assert cohorte_a["descripcion"]
        assert cohorte_a["criterio_humano"]
        assert len(cohorte_a["muestra"]) <= 5
        assert len(cohorte_a["muestra"]) == 2

        member = cohorte_a["muestra"][0]
        assert {"serie", "age_range", "household_segment", "senales"} <= member.keys()
        assert isinstance(member["senales"], list)
        assert len(member["senales"]) >= 1

        assert cohorte_a["producto"] is not None
        assert cohorte_a["producto"]["product_id"]
        assert cohorte_a["producto"]["product_name"]
        assert cohorte_a["razones"]

    def test_list_cohorts_sin_datos(self, monkeypatch) -> None:
        empty_engine = _make_engine()
        monkeypatch.setattr(db_module, "get_engine", lambda: empty_engine)
        service = ProactiveService()

        result = service.list_cohorts()

        assert result["fuente"] == "sin_datos"
        assert len(result["cohortes"]) == 3
        assert all(c["total"] == 0 for c in result["cohortes"])
        assert all(c["muestra"] == [] for c in result["cohortes"])


class TestPanelCohortesEndpoint:
    def setup_method(self) -> None:
        self.engine = _make_engine()
        _seed_cohort_fixtures(self.engine)
        self.client = TestClient(app)

    def test_endpoint_devuelve_tres_cohortes(self, monkeypatch) -> None:
        monkeypatch.setattr(db_module, "get_engine", lambda: self.engine)

        response = self.client.get("/api/v1/panel/cohortes")

        assert response.status_code == 200
        body = response.json()
        assert len(body["cohortes"]) == 3
        assert body["fuente"] == "postgres"

    def test_ruta_inexistente_404(self) -> None:
        response = self.client.get("/api/v1/panel/noexiste")

        assert response.status_code == 404
