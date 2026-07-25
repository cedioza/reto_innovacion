"""Tests for affiliate repository and service — TDD RED phase."""

from pathlib import Path
import tempfile

from app.core.config import settings
from app.repositories.affiliates import AffiliateRepository
from app.services.affiliate import AffiliateService
from app.schemas.conversation import ProfileData

FIXTURE_CSV = """SERIE;GENERO;RANGO_EDAD;RANGO_SALARIO;SEGMENTO_HOGAR;SEGMENTO_POBLACION;CIUDAD;SEÑAL_CONSUMO_1;SEÑAL_CONSUMO_2;SEÑAL_CONSUMO_3;SEÑAL_CONSUMO_4;SEÑAL_CONSUMO_5
A001;M;26-40;2-4M;3;TRABAJADOR;Bogotá;1;0;1;0;1
A002;F;41-55;1-2M;2;HOGAR;Medellín;0;1;0;1;0
A003;M;56-65;4M+;4;JUBILADO;Cali;0;0;0;0;0
"""


class TestAffiliateRepository:
    def setup_method(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        self.tmp.write(FIXTURE_CSV)
        self.tmp.close()
        self.repo = AffiliateRepository(csv_path=self.tmp.name)
        self.repo.load_from_csv(self.tmp.name)

    def teardown_method(self) -> None:
        Path(self.tmp.name).unlink(missing_ok=True)

    def test_find_existing_affiliate(self) -> None:
        profile = self.repo.find_by_document("A001")
        assert profile is not None
        assert profile.document_number == "A001"
        assert profile.age_range == "26-40"
        assert profile.stratum == 3
        assert profile.city == "Bogotá"

    def test_find_nonexistent_affiliate_returns_none(self) -> None:
        profile = self.repo.find_by_document("ZZ999")
        assert profile is None

    def test_exists_returns_true_for_existing(self) -> None:
        assert self.repo.exists("A001") is True
        assert self.repo.exists("ZZ999") is False

    def test_count_returns_correct_number(self) -> None:
        assert self.repo.count() == 3

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
