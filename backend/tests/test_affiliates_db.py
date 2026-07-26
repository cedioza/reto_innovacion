"""Tests for the DB-backed affiliate lookup (plan C2, Fase 1 — RED).

The repository under test will grow a cascade: in-memory cache -> SELECT
by PK ("serie") against the "afiliados" table -> fallback to the existing
CSV/xlsx path when the table does not exist, is empty, or the connection
fails. This module is written before `app.models.affiliate_record` exists,
so collection is expected to fail with an ImportError until Fase 2/3 of
the plan implement the model and wire the repository to it.

Engine pattern mirrors backend/tests/test_conversation_repository.py
(SQLite in-memory, StaticPool, shared connection).
"""

from pathlib import Path
import tempfile

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from app.models.affiliate_record import AffiliateRecord
from app.repositories.affiliates import AffiliateRepository
from app.repositories.db import init_db

# Same real-schema fixture format as backend/tests/test_affiliates.py
# (semicolon CSV, BOM utf-8-sig header) — a single well-formed row.
FIXTURE_CSV = (
    "SERIE;GENERO;RANGO_EDAD;RANGO_SALARIAL;CATEGORIA;"
    "SEGMENTO_GRUPO_FAMILIAR;SEGMENTO_POBLACIONAL;PIRAMIDE_NUEVA;"
    "EMPRESA_FOCO;CIUDAD_AFILIADO;HOTELES;PISCILAGO;DROGUERIA;AGENCIAS;"
    "VIVIENDA\n"
    "C900;F;20-35;Entre 1 y 1.5 SMLV;SIGMA;LAMBDA;RHO;OMEGA;EMP_000001;"
    "Bogotá;SI;SI;SI;SI;SI\n"
)


class TestAffiliateRepositoryDb:
    def setup_method(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_db(self.engine)

    def _write_fixture_csv(self) -> str:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8-sig"
        )
        tmp.write(FIXTURE_CSV)
        tmp.close()
        return tmp.name

    def _insert(
        self,
        serie: str = "S001",
        age_range: str = "20-35",
        gender: str | None = "F",
        household_segment: str | None = "RHO",
        salary_range: str | None = "1-1.5 SMLV",
        uses_drogueria: bool | None = True,
    ) -> None:
        with Session(self.engine) as session:
            session.add(
                AffiliateRecord(
                    serie=serie,
                    age_range=age_range,
                    gender=gender,
                    household_segment=household_segment,
                    salary_range=salary_range,
                    uses_drogueria=uses_drogueria,
                    sint_tiene_vehiculo=True,
                    sint_tiene_credito=False,
                    sint_tiene_hijos=True,
                    sint_tipo_vivienda="apartment",
                )
            )
            session.commit()

    # -- basic lookup backed by the table ----------------------------------

    def test_find_by_document_desde_bd(self) -> None:
        self._insert()
        repo = AffiliateRepository(engine=self.engine, csv_path="Z:\\no\\existe.csv")

        profile = repo.find_by_document("S001")

        assert profile is not None
        assert profile.document_number == "S001"
        assert profile.age_range == "20-35"
        assert profile.gender == "F"
        assert profile.household_segment == "RHO"
        assert profile.uses_drogueria is True

    def test_serie_inexistente_devuelve_none(self) -> None:
        self._insert()
        repo = AffiliateRepository(engine=self.engine, csv_path="Z:\\no\\existe.csv")

        assert repo.find_by_document("NADIE") is None

    def test_exists_y_count_desde_bd(self) -> None:
        self._insert("S001")
        self._insert("S002")
        repo = AffiliateRepository(engine=self.engine, csv_path="Z:\\no\\existe.csv")

        assert repo.exists("S001") is True
        assert repo.exists("NADIE") is False
        assert repo.count() == 2

    # -- in-memory cache -----------------------------------------------------

    def test_cache_en_memoria(self) -> None:
        self._insert()
        repo = AffiliateRepository(engine=self.engine, csv_path="Z:\\no\\existe.csv")

        first = repo.find_by_document("S001")
        assert first is not None

        with Session(self.engine) as session:
            record = session.exec(
                select(AffiliateRecord).where(AffiliateRecord.serie == "S001")
            ).first()
            assert record is not None
            session.delete(record)
            session.commit()

        second = repo.find_by_document("S001")
        assert second is not None
        assert second.document_number == "S001"

    # -- fallbacks -------------------------------------------------------------

    def test_tabla_vacia_cae_a_csv(self) -> None:
        csv_path = self._write_fixture_csv()
        try:
            repo = AffiliateRepository(engine=self.engine, csv_path=csv_path)

            profile = repo.find_by_document("C900")

            assert profile is not None
            assert profile.document_number == "C900"
            assert profile.gender == "F"
        finally:
            Path(csv_path).unlink(missing_ok=True)

    def test_bd_rota_cae_a_csv_sin_explotar(self) -> None:
        csv_path = self._write_fixture_csv()
        try:
            broken_engine = create_engine("sqlite:///Z:/ruta/invalida/imposible.db")
            repo = AffiliateRepository(engine=broken_engine, csv_path=csv_path)

            profile = repo.find_by_document("C900")

            assert profile is not None
            assert profile.document_number == "C900"
        finally:
            Path(csv_path).unlink(missing_ok=True)
