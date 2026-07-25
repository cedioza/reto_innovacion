"""Tests for the JSON-backed multi-product catalog — TDD RED phase.

These tests describe the target behaviour of `CatalogRepository` once it
loads products from `backend/app/data/catalogo/productos.json` (via
`pydantic.TypeAdapter(list[Product])`, cached by path) instead of the
hardcoded dict. They are expected to fail today because `CatalogRepository`
does not yet accept a `path` argument nor validate/load JSON.
"""

import json

import pytest

from app.repositories.catalog import CatalogRepository


def _write_catalog(path, products: list[dict]) -> None:
    path.write_text(json.dumps(products, ensure_ascii=False), encoding="utf-8")


def _dummy_product(product_id: str = "viaje-test") -> dict:
    return {
        "id": product_id,
        "name": "Viaje Test",
        "description": "Producto dummy de viaje para pruebas de catálogo.",
        "category": "viaje",
        "coverages": [
            {
                "name": "Cancelación de Viaje",
                "description": "Cubre gastos por cancelación del viaje.",
            },
        ],
        "exclusions": [
            {
                "name": "Viajes No Declarados",
                "description": "No cubre viajes no informados a la aseguradora.",
            },
        ],
        "adjustments": [
            {
                "code": "frequent_traveler",
                "name": "Viajero Frecuente",
                "description": "Descuento por historial de viajes frecuentes",
                "premium_modifier": 0.9,
            },
        ],
        "base_price": 20_000.0,
        "currency": "COP",
        "factors": {"age_range": {"18-25": 1.1}},
    }


class TestCatalogRepositoryNewProductFromJson:
    """Criterio 2: agregar un producto nuevo no requiere tocar código."""

    def test_new_product_without_code_is_returned_by_get_product(self, tmp_path) -> None:
        catalog_path = tmp_path / "productos_new_product.json"
        _write_catalog(catalog_path, [_dummy_product("viaje-test")])

        repo = CatalogRepository(path=str(catalog_path))
        product = repo.get_product("viaje-test")

        assert product is not None
        assert product.id == "viaje-test"
        assert product.category == "viaje"

    def test_new_product_without_code_appears_in_list_products(self, tmp_path) -> None:
        catalog_path = tmp_path / "productos_new_product_list.json"
        _write_catalog(catalog_path, [_dummy_product("viaje-test")])

        repo = CatalogRepository(path=str(catalog_path))
        products = repo.list_products()

        assert any(p.id == "viaje-test" for p in products)


class TestCatalogRepositoryMigrationParity:
    """Criterio: la migración a JSON preserva exactamente hogar-estandar."""

    def setup_method(self) -> None:
        self.repo = CatalogRepository()

    def test_hogar_estandar_base_price_and_currency(self) -> None:
        product = self.repo.get_product("hogar-estandar")
        assert product is not None
        assert product.base_price == 45_000.0
        assert product.currency == "COP"

    def test_hogar_estandar_coverages_and_exclusions_count(self) -> None:
        product = self.repo.get_product("hogar-estandar")
        assert product is not None
        assert len(product.coverages) == 5
        assert len(product.exclusions) == 4

    def test_hogar_estandar_adjustments_modifiers(self) -> None:
        product = self.repo.get_product("hogar-estandar")
        assert product is not None
        assert len(product.adjustments) == 3
        modifiers = {a.premium_modifier for a in product.adjustments}
        assert modifiers == {0.85, 0.80, 1.25}


class TestCatalogRepositoryNewFields:
    """Criterio 3: campos nuevos category y factors en el producto migrado."""

    def setup_method(self) -> None:
        self.repo = CatalogRepository()

    def test_hogar_estandar_category_is_hogar(self) -> None:
        product = self.repo.get_product("hogar-estandar")
        assert product is not None
        assert product.category == "hogar"

    def test_hogar_estandar_factors_age_range(self) -> None:
        product = self.repo.get_product("hogar-estandar")
        assert product is not None
        assert "age_range" in product.factors
        age_range = product.factors["age_range"]
        assert age_range["18-25"] == 1.15
        assert age_range["65+"] == 1.15


class TestCatalogRepositoryInvalidJson:
    """Criterio 4: JSON inválido debe fallar de forma explícita al cargar."""

    def test_missing_required_field_raises(self, tmp_path) -> None:
        catalog_path = tmp_path / "productos_missing_field.json"
        broken_product = _dummy_product("broken-missing-field")
        del broken_product["base_price"]
        _write_catalog(catalog_path, [broken_product])

        repo = CatalogRepository(path=str(catalog_path))
        with pytest.raises((ValueError, TypeError)):
            repo.list_products()

    def test_non_numeric_modifier_raises(self, tmp_path) -> None:
        catalog_path = tmp_path / "productos_bad_modifier.json"
        broken_product = _dummy_product("broken-bad-modifier")
        broken_product["adjustments"][0]["premium_modifier"] = "not-a-number"
        _write_catalog(catalog_path, [broken_product])

        repo = CatalogRepository(path=str(catalog_path))
        with pytest.raises((ValueError, TypeError)):
            repo.list_products()


class TestCatalogRepositoryDeterminism:
    """Criterio 5: misma ruta -> mismos datos entre instancias (caché)."""

    def test_same_path_returns_same_product_data(self, tmp_path) -> None:
        catalog_path = tmp_path / "productos_determinism.json"
        _write_catalog(catalog_path, [_dummy_product("viaje-test")])

        repo1 = CatalogRepository(path=str(catalog_path))
        repo2 = CatalogRepository(path=str(catalog_path))

        p1 = repo1.get_product("viaje-test")
        p2 = repo2.get_product("viaje-test")

        assert p1 is not None and p2 is not None
        assert p1.id == p2.id
        assert p1.base_price == p2.base_price
        assert p1.factors == p2.factors
        assert [c.name for c in p1.coverages] == [c.name for c in p2.coverages]
