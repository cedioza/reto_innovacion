"""Tests for the enriched-profile persistence (plan A4, Fase 1 — RED).

Cubre la persistencia por sesion/serie del perfil enriquecido: guardar y
leer campos, "ultima escritura gana", precedencia sesion > serie, y
supervivencia a reinicio del servicio/repositorio (mismo engine).

Este modulo se escribe antes de que existan `app.models.enriched_field`,
`app.repositories.enriched_profile` y `app.services.enrichment`, asi que
se espera que la coleccion falle con ImportError hasta que Fase 2/3 del
plan los implementen.

Patron de engine igual a backend/tests/test_conversation_repository.py y
backend/tests/test_affiliates_db.py (SQLite in-memory, StaticPool).
"""

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine

from app.repositories.db import init_db
from app.repositories.enriched_profile import EnrichedProfileRepository
from app.services.enrichment import EnrichmentService


class TestEnrichmentPersistence:
    def setup_method(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_db(self.engine)
        self.service = EnrichmentService(engine=self.engine)

    def test_guardar_y_leer_por_sesion(self) -> None:
        self.service.record("sess-1", None, "hijos", "2")
        self.service.record("sess-1", None, "mascota", "perro")

        assert self.service.fields_for("sess-1") == {
            "hijos": "2",
            "mascota": "perro",
        }

    def test_leer_por_serie(self) -> None:
        self.service.record("sess-1", "S001", "vehiculo", "si")

        assert self.service.fields_for("sess-2", serie="S001") == {
            "vehiculo": "si"
        }

    def test_ultima_escritura_gana(self) -> None:
        self.service.record("sess-1", None, "hijos", "1")
        self.service.record("sess-1", None, "hijos", "2")

        assert self.service.fields_for("sess-1") == {"hijos": "2"}

    def test_sesion_pisa_serie(self) -> None:
        self.service.record("sess-1", "S001", "vehiculo", "si")
        self.service.record("sess-2", "S001", "vehiculo", "no")

        assert self.service.fields_for("sess-2", "S001") == {"vehiculo": "no"}

    def test_sobrevive_reinicio(self) -> None:
        self.service.record("sess-persist", None, "ocupacion", "ingeniero")

        second_service = EnrichmentService(engine=self.engine)
        found = second_service.fields_for("sess-persist")

        assert found == {"ocupacion": "ingeniero"}

    def test_serie_none_no_rompe(self) -> None:
        assert self.service.fields_for("sess-x") == {}


class TestEnrichmentValidation:
    def setup_method(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_db(self.engine)
        self.service = EnrichmentService(engine=self.engine)

    def test_campo_desconocido_valueerror(self) -> None:
        with pytest.raises(ValueError):
            self.service.record("sess-1", None, "color_favorito", "azul")

    def test_valor_invalido_valueerror(self) -> None:
        with pytest.raises(ValueError):
            self.service.record("sess-1", None, "hijos", "perro")

        with pytest.raises(ValueError):
            self.service.record("sess-1", None, "mascota", "dinosaurio")

        with pytest.raises(ValueError):
            self.service.record("sess-1", None, "vehiculo", "tal vez")

        with pytest.raises(ValueError):
            self.service.record("sess-1", None, "ocupacion", "")

    def test_normalizacion(self) -> None:
        assert self.service.record("sess-1", None, "mascota", "  Perro ") == "perro"
        assert self.service.fields_for("sess-1")["mascota"] == "perro"

        assert self.service.record("sess-1", None, "hijos", "2") == "2"
        assert self.service.record("sess-1", None, "hijos", " 3 ") == "3"
        assert self.service.fields_for("sess-1")["hijos"] == "3"


# --- Fase 1 (A6): campo "nombre" como dato enriquecido (personalización) ----
#
# TDD-light, RED antes de implementar: `EnrichmentService.ALLOWED_FIELDS`
# todavía no conoce el campo "nombre". A diferencia del resto de campos
# (hijos, mascota, vehiculo, etc.) que se normalizan a minúsculas, "nombre"
# es un dato de personalización (para el saludo del asistente) y conserva la
# capitalización tal como la declaró el cliente; solo se recorta espacio en
# blanco y se valida que no esté vacío, no exceda 60 caracteres y no
# contenga dígitos.


class TestCampoNombre:
    def setup_method(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_db(self.engine)
        self.service = EnrichmentService(engine=self.engine)

    def test_nombre_valido_persiste(self) -> None:
        assert self.service.record("sess", "S1", "nombre", "Carlos") == "Carlos"
        assert self.service.fields_for("sess")["nombre"] == "Carlos"

    def test_nombre_conserva_capitalizacion_y_trim(self) -> None:
        assert (
            self.service.record("sess", None, "nombre", "  María del Mar ")
            == "María del Mar"
        )

    def test_nombre_vacio_valueerror(self) -> None:
        with pytest.raises(ValueError):
            self.service.record("sess", None, "nombre", "")

        with pytest.raises(ValueError):
            self.service.record("sess", None, "nombre", "   ")

    def test_nombre_con_digitos_valueerror(self) -> None:
        with pytest.raises(ValueError):
            self.service.record("sess", None, "nombre", "C4rlos")

    def test_nombre_muy_largo_valueerror(self) -> None:
        with pytest.raises(ValueError):
            self.service.record("sess", None, "nombre", "a" * 61)

        assert self.service.record("sess", None, "nombre", "a" * 60) == "a" * 60


class TestEnrichedProfileRepositoryListAll:
    """`list_all` (plan G4, Fase 2): todas las filas EAV, orden de `id` asc."""

    def setup_method(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_db(self.engine)
        self.repo = EnrichedProfileRepository(engine=self.engine)

    def test_list_all_returns_rows_in_id_ascending_order(self) -> None:
        self.repo.add("sess-1", None, "hijos", "2")
        self.repo.add("sess-1", "S001", "vehiculo", "si")
        self.repo.add("sess-2", None, "mascota", "perro")

        rows = self.repo.list_all()

        assert [r.campo for r in rows] == ["hijos", "vehiculo", "mascota"]
        assert [r.id for r in rows] == sorted(r.id for r in rows)
        assert rows[0].session_id == "sess-1"
        assert rows[0].serie is None
        assert rows[1].serie == "S001"
        assert rows[2].session_id == "sess-2"

    def test_list_all_empty_returns_empty_list(self) -> None:
        assert self.repo.list_all() == []


class TestEnrichmentServiceAllFields:
    """`EnrichmentService.all_fields` (plan G4, Fase 2): delega en el repo."""

    def setup_method(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_db(self.engine)
        self.service = EnrichmentService(engine=self.engine)

    def test_all_fields_returns_all_repository_rows(self) -> None:
        self.service.record("sess-1", None, "hijos", "2")
        self.service.record("sess-2", "S001", "vehiculo", "si")

        rows = self.service.all_fields()

        assert len(rows) == 2
        assert {r.session_id for r in rows} == {"sess-1", "sess-2"}
        assert {r.campo for r in rows} == {"hijos", "vehiculo"}
