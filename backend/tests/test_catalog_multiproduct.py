"""Tests for the full 5-product catalog — TDD RED phase.

These tests describe the target state of `productos.json` once the 4
remaining categories (accidentes, vida, movilidad, credito) are added
alongside the existing `hogar-estandar` product. They are expected to fail
today because only `hogar-estandar` exists in the catalog.
"""

from __future__ import annotations

import pytest

from app.repositories.catalog import CatalogRepository
from app.schemas.conversation import ProfileData
from app.services import handoff
from app.services.quote import QuoteService

EXPECTED_PRODUCT_IDS = {
    "hogar-estandar",
    "accidentes-personales",
    "vida-basico",
    "movilidad-auto",
    "credito-vida-deudor",
}

EXPECTED_CATEGORY_BY_ID = {
    "hogar-estandar": "hogar",
    "accidentes-personales": "accidentes",
    "vida-basico": "vida",
    "movilidad-auto": "movilidad",
    "credito-vida-deudor": "credito",
}

EXPECTED_ANNUAL_BASE_PRICE_BY_ID = {
    "hogar-estandar": 45_000.0,
    "accidentes-personales": 60_000.0,
    "vida-basico": 180_000.0,
    "movilidad-auto": 1_440_000.0,
    "credito-vida-deudor": 300_000.0,
}


class TestCatalogFullLoad:
    def setup_method(self) -> None:
        self.repo = CatalogRepository()

    def test_list_products_has_at_least_five_products(self) -> None:
        products = self.repo.list_products()
        assert len(products) >= 5

    def test_list_products_ids_contain_the_five_expected_ids(self) -> None:
        products = self.repo.list_products()
        ids = {p.id for p in products}
        assert EXPECTED_PRODUCT_IDS <= ids


class TestCatalogProductStructure:
    """Criterio 2 del vault: cada producto del catálogo cumple el esquema
    mínimo (exclusions, coverages, >=2 adjustments numéricos, category y
    currency), sin importar cuántos productos haya (cubre futuros)."""

    @staticmethod
    def _products() -> list:
        return CatalogRepository().list_products()

    def test_every_product_has_non_empty_exclusions(self) -> None:
        for product in self._products():
            assert len(product.exclusions) > 0, product.id

    def test_every_product_has_non_empty_coverages(self) -> None:
        for product in self._products():
            assert len(product.coverages) > 0, product.id

    def test_every_product_has_at_least_two_adjustments_with_numeric_positive_modifier(
        self,
    ) -> None:
        for product in self._products():
            assert len(product.adjustments) >= 2, product.id
            for adjustment in product.adjustments:
                assert isinstance(adjustment.premium_modifier, (int, float)), (
                    product.id,
                    adjustment.code,
                )
                assert adjustment.premium_modifier > 0, (product.id, adjustment.code)

    def test_every_product_has_non_empty_category_string(self) -> None:
        for product in self._products():
            assert isinstance(product.category, str)
            assert product.category != ""

    def test_every_product_currency_is_cop(self) -> None:
        for product in self._products():
            assert product.currency == "COP", product.id


class TestCatalogCategoryById:
    @pytest.mark.parametrize(
        ("product_id", "expected_category"),
        list(EXPECTED_CATEGORY_BY_ID.items()),
    )
    def test_product_category_matches_expected(
        self, product_id: str, expected_category: str
    ) -> None:
        product = CatalogRepository().get_product(product_id)
        assert product is not None, f"missing product: {product_id}"
        assert product.category == expected_category


class TestCatalogAnnualBasePriceById:
    @pytest.mark.parametrize(
        ("product_id", "expected_base_price"),
        list(EXPECTED_ANNUAL_BASE_PRICE_BY_ID.items()),
    )
    def test_product_base_price_matches_expected_annual_amount(
        self, product_id: str, expected_base_price: float
    ) -> None:
        product = CatalogRepository().get_product(product_id)
        assert product is not None, f"missing product: {product_id}"
        assert product.base_price == expected_base_price


# ---------------------------------------------------------------------------
# Fase 2 — QuoteService y handoff ganan soporte multi-producto (RED phase).
#
# `QuoteService.calculate_quote` hoy hardcodea "hogar-estandar" y no acepta
# `product_id`; estos tests deben fallar por
# `TypeError: calculate_quote() got an unexpected keyword argument
# 'product_id'` hasta que la implementación agregue ese parámetro.
# `INSURER_BY_PRODUCT` hoy solo mapea "hogar-estandar"; los tests de
# aseguradora para los 4 productos nuevos deben fallar por AssertionError
# (caen al fallback "la aseguradora aliada") hasta que se agreguen los ids.
# ---------------------------------------------------------------------------


EXPECTED_MONTHLY_PREMIUM_NEUTRAL_BY_ID = {
    "hogar-estandar": 3_750.0,
    "accidentes-personales": 5_000.0,
    "vida-basico": 15_000.0,
    "movilidad-auto": 120_000.0,
    "credito-vida-deudor": 25_000.0,
}


class TestQuoteServiceMultiProduct:
    """Criterio 1 del vault: `calculate_quote` cotiza cualquiera de los 5
    productos del catálogo, no solo "hogar-estandar", vía `product_id`."""

    @pytest.mark.parametrize(
        ("product_id", "expected_monthly"),
        list(EXPECTED_MONTHLY_PREMIUM_NEUTRAL_BY_ID.items()),
    )
    def test_calculate_quote_with_neutral_profile_matches_expected_monthly(
        self, product_id: str, expected_monthly: float
    ) -> None:
        profile = ProfileData(age_range="36-45")

        result = QuoteService().calculate_quote(profile, product_id=product_id)

        assert result["monthly_premium"] > 0
        assert result["monthly_premium"] == expected_monthly

    def test_age_risk_factor_applies_to_any_product(self) -> None:
        """El motor lee `product.factors["age_range"]` de cada producto en
        vez del multiplicador global hardcodeado 1.15 para 18-25/65+: para
        vida-basico el catalogo define 18-25 -> 0.85 (mas barato para
        jovenes en este producto), no un recargo."""
        profile = ProfileData(age_range="18-25")

        result = QuoteService().calculate_quote(profile, product_id="vida-basico")

        assert result["monthly_premium"] == 12_750.0

    def test_product_own_adjustment_is_applied(self) -> None:
        profile = ProfileData(age_range="36-45")

        result = QuoteService().calculate_quote(
            profile, ["low_mileage"], product_id="movilidad-auto"
        )

        assert result["monthly_premium"] == 108_000.0
        adjustment_codes = [a["code"] for a in result["adjustments"]]
        assert "low_mileage" in adjustment_codes

    def test_foreign_adjustment_is_silently_ignored(self) -> None:
        """Comportamiento actual: un código de ajuste que no pertenece al
        producto cotizado no aplica y no lanza error."""
        profile = ProfileData(age_range="36-45")

        result = QuoteService().calculate_quote(
            profile, ["fire_alarm"], product_id="vida-basico"
        )

        assert result["monthly_premium"] == 15_000.0
        assert result["adjustments"] == []

    def test_calculate_quote_with_unknown_product_raises_value_error(self) -> None:
        profile = ProfileData(age_range="36-45")

        with pytest.raises(ValueError, match="Product not found"):
            QuoteService().calculate_quote(profile, product_id="no-existe")


class TestInsurerForNewProducts:
    """Criterio del vault: `INSURER_BY_PRODUCT` cubre los 4 productos nuevos;
    el fallback a "la aseguradora aliada" para ids desconocidos sigue
    intacto (caracterización, no duplica test_handoff.py)."""

    @pytest.mark.parametrize(
        ("product_id", "expected_insurer"),
        [
            ("accidentes-personales", "Seguros Sura"),
            ("vida-basico", "Seguros Bolívar"),
            ("movilidad-auto", "Mapfre"),
            ("credito-vida-deudor", "Aseguradora Solidaria"),
        ],
    )
    def test_insurer_for_new_product_ids(
        self, product_id: str, expected_insurer: str
    ) -> None:
        assert handoff.insurer_for(product_id) == expected_insurer

    def test_insurer_for_unmapped_product_still_falls_back(self) -> None:
        assert handoff.insurer_for("producto-x") == "la aseguradora aliada"
