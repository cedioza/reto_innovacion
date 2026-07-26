"""Tests for the full 5-product catalog — TDD RED phase.

These tests describe the target state of `productos.json` once the 4
remaining categories (accidentes, vida, movilidad, credito) are added
alongside the existing `hogar-estandar` product. They are expected to fail
today because only `hogar-estandar` exists in the catalog.
"""

from __future__ import annotations

import pytest

from app.repositories.catalog import CatalogRepository

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
