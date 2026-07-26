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
