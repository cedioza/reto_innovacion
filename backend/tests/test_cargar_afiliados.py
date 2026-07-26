"""Tests for the batch loader script (plan C2, Fase 2 — RED).

`app.scripts.cargar_afiliados` will expose an importable `load_to_db(path,
engine=None, replace=False) -> dict` (summary with `loaded`, `parse_errors`,
`seconds`) and a `main(argv)` CLI entry point. The loader parses with the C1
`AffiliateRepository.load_from_csv`, decorates every profile with the
deterministic `sint_*` columns from `app.services.synthetic.synthetic_for`,
and inserts into the `afiliados` table in batches.

This module is written before `app.scripts.cargar_afiliados` exists, so
collection is expected to fail with an ImportError until Fase 2 implements
it.

Engine pattern mirrors backend/tests/test_affiliates_db.py (SQLite
in-memory, StaticPool, shared connection, `init_db`).
"""

from pathlib import Path
import tempfile

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from app.models.affiliate_record import AffiliateRecord
from app.repositories.affiliates import AffiliateRepository
from app.repositories.db import init_db
from app.scripts.cargar_afiliados import load_to_db, main

# Same real-schema fixture format as backend/tests/test_affiliates.py
# (semicolon CSV, BOM utf-8-sig header): 10 well-formed rows (A001..A010)
# + 2 corrupt rows (missing SERIE).
FIXTURE_CSV = """SERIE;GENERO;RANGO_EDAD;RANGO_SALARIAL;CATEGORIA;SEGMENTO_GRUPO_FAMILIAR;SEGMENTO_POBLACIONAL;PIRAMIDE_NUEVA;EMPRESA_FOCO;CIUDAD_AFILIADO;HOTELES;PISCILAGO;DROGUERIA;AGENCIAS;VIVIENDA
A001;M;26-40;Entre 1 y 1.5 SMLV;SIGMA;LAMBDA;RHO;OMEGA;EMP_000001;Bogotá;SI;SI;SI;SI;SI
A002;F;41-55;Entre 2 y 4 SMLV;LAMBDA;RHO;OMEGA;SIGMA;EMP_000002;Medellín;NO;NO;NO;NO;NO
A003;M;56-65;Más de 5 SMLV;RHO;OMEGA;SIGMA;LAMBDA;EMP_000001;Cali;SI;NO;SI;NO;SI
A004;F;36-45;;OMEGA;SIGMA;LAMBDA;RHO;EMP_000002;;SI;;NO;;SI
A005;M;Más de 55 años;Entre 1.5 y 2 SMLV;SIGMA;LAMBDA;RHO;OMEGA;EMP_000001;Barranquilla;NO;SI;NO;SI;NO
A006;F;20-35;Entre 1 y 1.5 SMLV;LAMBDA;RHO;OMEGA;SIGMA;EMP_000002;Cartagena;SI;SI;NO;NO;SI
A007;M;41-55;Entre 4 y 6 SMLV;RHO;OMEGA;SIGMA;LAMBDA;EMP_000001;Bucaramanga;NO;SI;SI;NO;NO
A008;F;26-40;;SIGMA;LAMBDA;RHO;OMEGA;EMP_000002;;NO;NO;NO;NO;NO
A009;M;56-65;Más de 6 SMLV;LAMBDA;RHO;OMEGA;SIGMA;EMP_000001;Pereira;SI;NO;SI;SI;NO
A010;F;36-45;Entre 2 y 4 SMLV;RHO;OMEGA;SIGMA;LAMBDA;EMP_000002;Manizales;NO;SI;NO;SI;SI
;M;26-40;Entre 1 y 1.5 SMLV;SIGMA;LAMBDA;RHO;OMEGA;EMP_000001;Bogotá;SI;SI;SI;SI;SI
;F;41-55;Entre 2 y 4 SMLV;LAMBDA;RHO;OMEGA;SIGMA;EMP_000002;Medellín;NO;NO;NO;NO;NO
"""


class TestCargarAfiliados:
    def setup_method(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        init_db(self.engine)

        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8-sig"
        )
        self.tmp.write(FIXTURE_CSV)
        self.tmp.close()

    def teardown_method(self) -> None:
        Path(self.tmp.name).unlink(missing_ok=True)

    # -- end-to-end load -------------------------------------------------------

    def test_carga_end_to_end(self) -> None:
        summary = load_to_db(self.tmp.name, engine=self.engine)

        assert summary["loaded"] == 10
        assert summary["parse_errors"] == 2

        repo = AffiliateRepository(engine=self.engine, csv_path="Z:\\no\\existe.csv")
        assert repo.count() == 10

        profile = repo.find_by_document("A001")
        assert profile is not None
        assert profile.document_number == "A001"
        assert profile.age_range == "26-40"
        assert profile.gender == "M"
        assert profile.household_segment == "LAMBDA"

    # -- synthetic columns populated and deterministic -------------------------

    def test_sint_columns_pobladas_y_deterministas(self) -> None:
        load_to_db(self.tmp.name, engine=self.engine)

        with Session(self.engine) as session:
            first = session.get(AffiliateRecord, "A001")
            second = session.get(AffiliateRecord, "A002")

        assert first is not None
        assert second is not None
        assert isinstance(first.sint_tiene_vehiculo, bool)
        assert isinstance(first.sint_tiene_credito, bool)
        assert isinstance(first.sint_tiene_hijos, bool)
        assert isinstance(second.sint_tiene_vehiculo, bool)
        assert isinstance(second.sint_tiene_credito, bool)
        assert isinstance(second.sint_tiene_hijos, bool)

        first_snapshot = (
            first.sint_tiene_vehiculo,
            first.sint_tiene_credito,
            first.sint_tiene_hijos,
            first.sint_tipo_vivienda,
        )
        second_snapshot = (
            second.sint_tiene_vehiculo,
            second.sint_tiene_credito,
            second.sint_tiene_hijos,
            second.sint_tipo_vivienda,
        )

        load_to_db(self.tmp.name, engine=self.engine, replace=True)

        with Session(self.engine) as session:
            first_again = session.get(AffiliateRecord, "A001")
            second_again = session.get(AffiliateRecord, "A002")

        assert first_again is not None
        assert second_again is not None
        assert (
            first_again.sint_tiene_vehiculo,
            first_again.sint_tiene_credito,
            first_again.sint_tiene_hijos,
            first_again.sint_tipo_vivienda,
        ) == first_snapshot
        assert (
            second_again.sint_tiene_vehiculo,
            second_again.sint_tiene_credito,
            second_again.sint_tiene_hijos,
            second_again.sint_tipo_vivienda,
        ) == second_snapshot

    # -- replace does not duplicate ---------------------------------------------

    def test_replace_no_duplica(self) -> None:
        load_to_db(self.tmp.name, engine=self.engine, replace=True)
        load_to_db(self.tmp.name, engine=self.engine, replace=True)

        repo = AffiliateRepository(engine=self.engine, csv_path="Z:\\no\\existe.csv")
        assert repo.count() == 10

    # -- missing file: clear failure, no raw traceback ---------------------------

    def test_archivo_inexistente_falla_claro(self, capsys) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["Z:\\no\\existe.csv"])

        assert exc_info.value.code != 0
        assert exc_info.value.code is not None

        captured = capsys.readouterr()
        combined_output = captured.out + captured.err
        assert combined_output.strip() != ""
        assert "Traceback (most recent call last)" not in combined_output
