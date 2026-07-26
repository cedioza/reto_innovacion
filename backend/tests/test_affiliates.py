"""Tests for affiliate repository and service — real dataset schema.

The fixture below mirrors the REAL Colsubsidio schema (semicolon CSV,
BOM utf-8-sig header):

  SERIE;GENERO;RANGO_EDAD;RANGO_SALARIAL;CATEGORIA;SEGMENTO_GRUPO_FAMILIAR;
  SEGMENTO_POBLACIONAL;PIRAMIDE_NUEVA;EMPRESA_FOCO;CIUDAD_AFILIADO;
  HOTELES;PISCILAGO;DROGUERIA;AGENCIAS;VIVIENDA

This is a deliberate RED-phase rewrite (plan C1, Fase 1): the loader in
app/repositories/affiliates.py and the model in app/models/affiliate.py
still describe the OLD, invented schema — these tests are expected to
fail until both are rewritten in the next steps of the plan.
"""

from pathlib import Path
import tempfile

from app.core.config import settings
from app.repositories.affiliates import AffiliateRepository
from app.services.affiliate import AffiliateService
from app.schemas.conversation import ProfileData

# Real header (BOM added on write via encoding="utf-8-sig").
# 18 well-formed rows (A001..A018) + 2 corrupt rows (missing SERIE, rows 20/21).
FIXTURE_CSV = """SERIE;GENERO;RANGO_EDAD;RANGO_SALARIAL;CATEGORIA;SEGMENTO_GRUPO_FAMILIAR;SEGMENTO_POBLACIONAL;PIRAMIDE_NUEVA;EMPRESA_FOCO;CIUDAD_AFILIADO;HOTELES;PISCILAGO;DROGUERIA;AGENCIAS;VIVIENDA
A001;M;26-40;Entre 1 y 1.5 SMLV;SIGMA;LAMBDA;RHO;OMEGA;EMP_000001;Bogotá;SI;SI;SI;SI;SI
A002;F;41-55;Entre 2 y 4 SMLV;LAMBDA;RHO;OMEGA;SIGMA;EMP_000002;Medellín;NO;NO;NO;NO;NO
A003;M;56-65;Más de 5 SMLV;RHO;OMEGA;SIGMA;LAMBDA;EMP_000001;Cali;SI;NO;SI;NO;SI
A004;F;36-45 a�os;;OMEGA;SIGMA;LAMBDA;RHO;EMP_000002;;SI;;NO;;SI
A005;M;Más de 55 años;Entre 1.5 y 2 SMLV;SIGMA;LAMBDA;RHO;OMEGA;EMP_000001;Barranquilla;NO;SI;NO;SI;NO
A006;F;20-35;Entre 1 y 1.5 SMLV;LAMBDA;RHO;OMEGA;SIGMA;EMP_000002;Cartagena;SI;SI;NO;NO;SI
A007;M;41-55;Entre 4 y 6 SMLV;RHO;OMEGA;SIGMA;LAMBDA;EMP_000001;Bucaramanga;NO;SI;SI;NO;NO
A008;F;26-40;;SIGMA;LAMBDA;RHO;OMEGA;EMP_000002;;NO;NO;NO;NO;NO
A009;M;56-65;Más de 6 SMLV;LAMBDA;RHO;OMEGA;SIGMA;EMP_000001;Pereira;SI;NO;SI;SI;NO
A010;F;36-45 a�os;Entre 2 y 4 SMLV;RHO;OMEGA;SIGMA;LAMBDA;EMP_000002;Manizales;NO;SI;NO;SI;SI
A011;M;20-35;Entre 1.5 y 2 SMLV;SIGMA;LAMBDA;RHO;OMEGA;EMP_000001;Ibagué;SI;SI;SI;SI;SI
A012;F;Más de 55 años;;LAMBDA;RHO;OMEGA;SIGMA;EMP_000002;;NO;NO;NO;NO;NO
A013;M;41-55;Entre 1 y 1.5 SMLV;RHO;OMEGA;SIGMA;LAMBDA;EMP_000001;Bogotá;SI;NO;NO;SI;NO
A014;F;26-40;Entre 2 y 4 SMLV;SIGMA;LAMBDA;RHO;OMEGA;EMP_000002;Medellín;NO;SI;SI;NO;SI
A015;M;56-65;Más de 5 SMLV;LAMBDA;RHO;OMEGA;SIGMA;EMP_000001;Cali;SI;SI;NO;NO;NO
A016;F;20-35;Entre 1 y 1.5 SMLV;RHO;OMEGA;SIGMA;LAMBDA;EMP_000002;Bogotá;NO;NO;SI;SI;SI
A017;M;36-45;Entre 4 y 6 SMLV;SIGMA;LAMBDA;RHO;OMEGA;EMP_000001;Medellín;SI;NO;NO;NO;SI
A018;F;41-55;Entre 1 y 1.5 SMLV;;;;;EMP_000002;Bogotá;NO;SI;NO;SI;NO
;M;26-40;Entre 1 y 1.5 SMLV;SIGMA;LAMBDA;RHO;OMEGA;EMP_000001;Bogotá;SI;SI;SI;SI;SI
;F;41-55;Entre 2 y 4 SMLV;LAMBDA;RHO;OMEGA;SIGMA;EMP_000002;Medellín;NO;NO;NO;NO;NO
"""


class TestAffiliateRepository:
    def setup_method(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8-sig"
        )
        self.tmp.write(FIXTURE_CSV)
        self.tmp.close()
        self.repo = AffiliateRepository(csv_path=self.tmp.name)
        self.repo.load_from_csv(self.tmp.name)

    def teardown_method(self) -> None:
        Path(self.tmp.name).unlink(missing_ok=True)

    # -- basic lookup -----------------------------------------------------

    def test_find_existing_affiliate(self) -> None:
        profile = self.repo.find_by_document("A001")
        assert profile is not None
        assert profile.document_number == "A001"
        assert profile.age_range == "26-40"

    def test_find_nonexistent_affiliate_returns_none(self) -> None:
        profile = self.repo.find_by_document("ZZ999")
        assert profile is None

    def test_exists_returns_true_for_existing(self) -> None:
        assert self.repo.exists("A001") is True
        assert self.repo.exists("ZZ999") is False

    # -- salary range: two source schemas -> one canonical format ---------

    def test_new_salary_schema_normalizes_to_canonical(self) -> None:
        profile = self.repo.find_by_document("A001")
        assert profile.salary_range == "1-1.5 SMLV"

    def test_old_salary_schema_normalizes_to_canonical(self) -> None:
        profile = self.repo.find_by_document("A002")
        assert profile.salary_range == "2-4 SMLV"

    def test_open_ended_salary_normalizes_to_plus_suffix(self) -> None:
        profile = self.repo.find_by_document("A003")
        assert profile.salary_range == "5+ SMLV"

    def test_empty_salary_range_is_none_but_row_still_loads(self) -> None:
        profile = self.repo.find_by_document("A004")
        assert profile is not None
        assert profile.salary_range is None

    # -- age range: canonicalized by digits, immune to mojibake -----------

    def test_age_range_mojibake_normalizes_to_canonical(self) -> None:
        profile = self.repo.find_by_document("A004")
        assert profile.age_range == "36-45"

    def test_age_range_open_ended_normalizes_to_plus_suffix(self) -> None:
        profile = self.repo.find_by_document("A005")
        assert profile.age_range == "55+"

    # -- consumption marks: SI/NO/empty -> True/False/None ----------------

    def test_marks_all_si_map_to_true(self) -> None:
        profile = self.repo.find_by_document("A001")
        assert profile.uses_hoteles is True
        assert profile.uses_piscilago is True
        assert profile.uses_drogueria is True
        assert profile.uses_agencias is True
        assert profile.uses_vivienda is True

    def test_marks_all_no_map_to_false(self) -> None:
        profile = self.repo.find_by_document("A002")
        assert profile.uses_hoteles is False
        assert profile.uses_piscilago is False
        assert profile.uses_drogueria is False
        assert profile.uses_agencias is False
        assert profile.uses_vivienda is False

    def test_marks_empty_map_to_none(self) -> None:
        profile = self.repo.find_by_document("A004")
        assert profile.uses_hoteles is True
        assert profile.uses_piscilago is None
        assert profile.uses_drogueria is False
        assert profile.uses_agencias is None
        assert profile.uses_vivienda is True

    # -- city / zone --------------------------------------------------------

    def test_empty_city_yields_city_and_zone_none(self) -> None:
        profile = self.repo.find_by_document("A004")
        assert profile.city is None
        assert profile.zone is None

    def test_city_present_yields_zone_urban(self) -> None:
        profile = self.repo.find_by_document("A001")
        assert profile.city == "Bogotá"
        assert profile.zone == "urban"

    # -- greek-coded segments: stored as-is, never interpreted -------------

    def test_greek_segments_stored_as_is(self) -> None:
        profile = self.repo.find_by_document("A001")
        assert profile.category == "SIGMA"
        assert profile.household_segment == "LAMBDA"
        assert profile.population_segment == "RHO"
        assert profile.pyramid == "OMEGA"

    def test_greek_segments_empty_are_none(self) -> None:
        profile = self.repo.find_by_document("A018")
        assert profile.category is None
        assert profile.household_segment is None
        assert profile.population_segment is None
        assert profile.pyramid is None

    # -- gender / empresa_foco: stored as-is ---------------------------------

    def test_gender_and_empresa_foco_stored_as_is(self) -> None:
        profile = self.repo.find_by_document("A001")
        assert profile.gender == "M"
        assert profile.empresa_foco == "EMP_000001"

    # -- fields the real dataset does not provide ---------------------------

    def test_stratum_keeps_default_and_property_type_is_none(self) -> None:
        profile = self.repo.find_by_document("A001")
        assert profile.stratum == 3
        assert profile.property_type is None

    # -- corrupt rows reported, load continues -------------------------------

    def test_corrupt_rows_are_reported_and_do_not_stop_the_load(self) -> None:
        assert self.repo.count() == 18
        assert len(self.repo.load_errors) == 2
        assert any("20" in error for error in self.repo.load_errors)
        assert any("21" in error for error in self.repo.load_errors)

    def test_count_returns_correct_number(self) -> None:
        assert self.repo.count() == 18

    # -- graceful degradation / settings wiring ------------------------------

    def test_empty_csv_graceful(self) -> None:
        repo = AffiliateRepository(csv_path="/tmp/nonexistent.csv")
        result = repo.find_by_document("A001")
        assert result is None

    def test_uses_settings_affiliate_csv_path_when_no_explicit_path(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "affiliate_csv_path", self.tmp.name)
        repo = AffiliateRepository()
        profile = repo.find_by_document("A001")
        assert profile is not None
        assert profile.document_number == "A001"
        assert profile.gender == "M"


class TestAffiliateService:
    def setup_method(self) -> None:
        self.service = AffiliateService()

    def test_build_declared_profile(self) -> None:
        data = ProfileData(
            age_range="26-40",
            property_type="house",
            zone="urban",
            stratum=3,
        )
        profile = self.service.build_declared_profile(data)
        assert profile.document_number == "declared"
        assert profile.age_range == "26-40"
        assert profile.property_type == "house"

    def test_resolve_without_document_uses_declared(self) -> None:
        declared = ProfileData(age_range="26-40", stratum=4)
        profile = self.service.resolve(document_number=None, declared=declared)
        assert profile.document_number == "declared"
        assert profile.age_range == "26-40"

    def test_resolve_without_anything_returns_default(self) -> None:
        profile = self.service.resolve(document_number=None)
        assert profile.document_number == "declared"
        assert profile.age_range == "unknown"
