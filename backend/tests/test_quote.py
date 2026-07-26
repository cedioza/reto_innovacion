"""Tests for the quote engine — TDD RED phase."""

import pytest

from app.services.quote import QuoteService
from app.schemas.conversation import ProfileData


class TestQuoteService:
    def setup_method(self) -> None:
        self.service = QuoteService()

    def _make_profile(
        self,
        age_range: str | None = "26-40",
        property_type: str | None = "house",
        zone: str | None = "urban",
        stratum: int | None = 3,
    ) -> ProfileData:
        return ProfileData(
            age_range=age_range,
            property_type=property_type,
            zone=zone,
            stratum=stratum,
        )

    def test_same_profile_same_price(self) -> None:
        profile = self._make_profile()
        q1 = self.service.calculate_quote(profile)
        q2 = self.service.calculate_quote(profile)
        assert q1["monthly_premium"] == q2["monthly_premium"]
        assert q1["annual_premium"] == q2["annual_premium"]

    def test_fire_alarm_reduces_premium(self) -> None:
        profile = self._make_profile()
        base = self.service.calculate_quote(profile)
        adjusted = self.service.calculate_quote(
            profile, selected_adjustments=["fire_alarm"]
        )
        assert adjusted["monthly_premium"] < base["monthly_premium"]

    def test_high_value_increases_premium(self) -> None:
        profile = self._make_profile()
        base = self.service.calculate_quote(profile)
        adjusted = self.service.calculate_quote(
            profile, selected_adjustments=["high_value"]
        )
        assert adjusted["monthly_premium"] > base["monthly_premium"]

    def test_no_adjustments_monthly_is_base_divided_12(self) -> None:
        profile = self._make_profile()
        quote = self.service.calculate_quote(profile)
        expected_monthly = round(quote["annual_premium"] / 12, 2)
        assert quote["monthly_premium"] == expected_monthly

    def test_young_age_increases_premium(self) -> None:
        adult = self._make_profile(age_range="26-40")
        young = self._make_profile(age_range="18-25")
        adult_q = self.service.calculate_quote(adult)
        young_q = self.service.calculate_quote(young)
        assert young_q["annual_premium"] > adult_q["annual_premium"]

    def test_senior_age_increases_premium(self) -> None:
        adult = self._make_profile(age_range="26-40")
        senior = self._make_profile(age_range="60+")
        adult_q = self.service.calculate_quote(adult)
        senior_q = self.service.calculate_quote(senior)
        assert senior_q["annual_premium"] > adult_q["annual_premium"]

    def test_quote_has_coverage_and_exclusions(self) -> None:
        profile = self._make_profile()
        quote = self.service.calculate_quote(profile)
        assert len(quote["coverage_details"]) > 0
        assert len(quote["exclusions"]) > 0
        assert quote["currency"] == "COP"


class TestQuoteMulticategory:
    """Motor de cotización genérico: aplica `product.factors` de forma
    genérica a cualquier producto del catálogo (criterio 1 de B4), en vez
    del multiplicador de edad hardcodeado que solo conocía hogar-estandar.
    """

    PRODUCT_IDS = [
        "hogar-estandar",
        "accidentes-personales",
        "vida-basico",
        "movilidad-auto",
        "credito-vida-deudor",
    ]

    def setup_method(self) -> None:
        self.service = QuoteService()

    def _make_profile(self, age_range: str | None = "36-45") -> ProfileData:
        return ProfileData(age_range=age_range)

    @pytest.mark.parametrize("product_id", PRODUCT_IDS)
    def test_quote_shape_for_every_product(self, product_id: str) -> None:
        profile = self._make_profile()
        quote = self.service.calculate_quote(profile, product_id=product_id)

        for key in (
            "base_amount",
            "adjustments",
            "monthly_premium",
            "annual_premium",
            "currency",
            "coverage_details",
            "exclusions",
        ):
            assert key in quote, key

        assert quote["base_amount"] > 0
        assert quote["annual_premium"] > 0
        assert quote["monthly_premium"] > 0
        assert quote["currency"] == "COP"
        assert quote["monthly_premium"] == round(quote["annual_premium"] / 12, 2)

    @pytest.mark.parametrize("product_id", PRODUCT_IDS)
    def test_same_profile_same_amounts_for_every_product(self, product_id: str) -> None:
        profile = self._make_profile()
        q1 = self.service.calculate_quote(profile, product_id=product_id)
        q2 = self.service.calculate_quote(profile, product_id=product_id)
        assert q1["annual_premium"] == q2["annual_premium"]
        assert q1["monthly_premium"] == q2["monthly_premium"]

    def test_vida_age_factors_from_catalog(self) -> None:
        """vida-basico define en el catalogo age_range 36-45 -> 1.0 y
        60+ -> 1.80; el motor debe leer esos factores del producto en vez
        de aplicar el multiplicador global hardcodeado de 1.15."""
        adult = self._make_profile(age_range="36-45")
        senior = self._make_profile(age_range="60+")

        adult_q = self.service.calculate_quote(adult, product_id="vida-basico")
        senior_q = self.service.calculate_quote(senior, product_id="vida-basico")

        assert senior_q["annual_premium"] > adult_q["annual_premium"]
        assert senior_q["annual_premium"] == round(adult_q["annual_premium"] * 1.8, 2)

    def test_hogar_senior_surcharge_applies(self) -> None:
        """El bucket de hogar para adultos mayores es "60+" (corregido desde
        "65+" en el JSON); hoy el motor no lo reconoce porque hardcodea la
        edad y el catalogo aun dice "65+", por lo que este test falla."""
        adult = self._make_profile(age_range="36-45")
        senior = self._make_profile(age_range="60+")

        adult_q = self.service.calculate_quote(adult, product_id="hogar-estandar")
        senior_q = self.service.calculate_quote(senior, product_id="hogar-estandar")

        assert senior_q["annual_premium"] > adult_q["annual_premium"]

    def test_factor_without_profile_field_is_neutral(self) -> None:
        """movilidad-auto define un factor `vehicle_type` que no existe como
        campo en ProfileData; debe cotizar sin excepcion y de forma neutra
        (x1.0) cuando el campo no esta presente en el perfil."""
        profile = self._make_profile(age_range="36-45")

        quote = self.service.calculate_quote(profile, product_id="movilidad-auto")

        assert quote["annual_premium"] == 1_440_000.0

    def test_unknown_bucket_is_neutral(self) -> None:
        """accidentes-personales solo define factores para 18-25 y 60+; un
        bucket no listado (36-45) debe cotizar sin recargo (neutro x1.0)."""
        profile = self._make_profile(age_range="36-45")

        quote = self.service.calculate_quote(profile, product_id="accidentes-personales")

        assert quote["annual_premium"] == 60_000.0


class TestQuoteCompare:
    """Nueva primitiva `QuoteService.compare` (paso 2 de la Fase 2 de B4):
    hoy la logica actual/propuesta/diferencia vive duplicada en
    `_ajustar_comparar` (agent_tools.py) y `apply_adjustments`
    (conversation.py); `compare` la centraliza en el motor y agrega el
    listado de ajustes activados/retirados entre dos cotizaciones del mismo
    perfil y producto. RED esperado: `QuoteService` aun no define `compare`.
    """

    PRODUCT_ADJUSTMENT = [
        ("hogar-estandar", "fire_alarm"),
        ("accidentes-personales", "family_plan"),
        ("vida-basico", "double_capital"),
        ("movilidad-auto", "zero_deductible"),
        ("credito-vida-deudor", "unemployment_plus"),
    ]

    def setup_method(self) -> None:
        self.service = QuoteService()

    def _make_profile(self, age_range: str | None = "36-45") -> ProfileData:
        return ProfileData(age_range=age_range)

    def test_compare_returns_two_quotes_with_differences(self) -> None:
        profile = self._make_profile()

        result = self.service.compare(
            profile, "hogar-estandar", [], ["high_value"]
        )

        for key in ("actual", "propuesta"):
            for field in (
                "base_amount",
                "adjustments",
                "monthly_premium",
                "annual_premium",
                "currency",
                "coverage_details",
                "exclusions",
            ):
                assert field in result[key], (key, field)

        assert result["diferencia_mensual"] > 0
        assert result["diferencia_anual"] == round(
            result["propuesta"]["annual_premium"]
            - result["actual"]["annual_premium"],
            2,
        )
        assert result["ajustes_activados"] == ["high_value"]
        assert result["ajustes_retirados"] == []

    def test_compare_marks_removed_adjustments(self) -> None:
        profile = self._make_profile()

        result = self.service.compare(
            profile,
            "hogar-estandar",
            ["fire_alarm", "high_value"],
            ["high_value"],
        )

        assert result["ajustes_retirados"] == ["fire_alarm"]
        assert result["ajustes_activados"] == []

    def test_adjust_is_deterministic_roundtrip(self) -> None:
        """Criterio 2 de B4: aplicar un ajuste y luego quitarlo debe volver
        exactamente al peso original de la cotización."""
        profile = self._make_profile()
        original = self.service.calculate_quote(profile, [], "hogar-estandar")

        self.service.compare(profile, "hogar-estandar", [], ["fire_alarm"])
        back = self.service.compare(
            profile, "hogar-estandar", ["fire_alarm"], []
        )

        assert back["propuesta"]["base_amount"] == original["base_amount"]
        assert back["propuesta"]["monthly_premium"] == original["monthly_premium"]
        assert back["propuesta"]["annual_premium"] == original["annual_premium"]

    @pytest.mark.parametrize("product_id, code", PRODUCT_ADJUSTMENT)
    def test_compare_across_catalog(self, product_id: str, code: str) -> None:
        """Criterio 3 de B4: `compare` funciona con cualquier producto del
        catalogo, no solo hogar-estandar."""
        profile = self._make_profile()

        result = self.service.compare(profile, product_id, [], [code])

        for key in (
            "actual",
            "propuesta",
            "diferencia_mensual",
            "diferencia_anual",
            "ajustes_activados",
            "ajustes_retirados",
            "ajustes_disponibles",
        ):
            assert key in result, key

        assert (
            result["propuesta"]["monthly_premium"]
            != result["actual"]["monthly_premium"]
        )
        assert (
            result["propuesta"]["annual_premium"]
            != result["actual"]["annual_premium"]
        )
        assert any(
            adj["code"] == code for adj in result["ajustes_disponibles"]
        )

    def test_compare_unknown_product_raises(self) -> None:
        profile = self._make_profile()

        with pytest.raises(ValueError):
            self.service.compare(profile, "producto-inexistente", [], [])
