"""Tests for the catalog repository — TDD RED phase."""

from app.repositories.catalog import CatalogRepository


class TestCatalogRepository:
    def setup_method(self) -> None:
        self.repo = CatalogRepository()

    def test_get_product_hogar_estandar_exists(self) -> None:
        product = self.repo.get_product("hogar-estandar")
        assert product is not None
        assert product.id == "hogar-estandar"
        assert product.name == "Hogar Estándar"

    def test_product_has_at_least_three_coverages(self) -> None:
        product = self.repo.get_product("hogar-estandar")
        assert product is not None
        assert len(product.coverages) >= 3

    def test_product_has_at_least_three_exclusions(self) -> None:
        product = self.repo.get_product("hogar-estandar")
        assert product is not None
        assert len(product.exclusions) >= 3

    def test_repeated_calls_return_same_product(self) -> None:
        p1 = self.repo.get_product("hogar-estandar")
        p2 = self.repo.get_product("hogar-estandar")
        assert p1 is not None and p2 is not None
        assert p1.base_price == p2.base_price
        assert [c.name for c in p1.coverages] == [c.name for c in p2.coverages]

    def test_get_unknown_product_returns_none(self) -> None:
        product = self.repo.get_product("producto-inexistente")
        assert product is None

    def test_list_products_returns_at_least_one(self) -> None:
        products = self.repo.list_products()
        assert len(products) >= 1
        assert any(p.id == "hogar-estandar" for p in products)
