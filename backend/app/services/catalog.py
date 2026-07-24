from app.repositories.catalog import CatalogRepository
from app.models.product import Product


class CatalogService:
    """Thin service wrapper around catalog repository."""

    def __init__(self) -> None:
        self._repo = CatalogRepository()

    def get_product(self, product_id: str) -> Product | None:
        return self._repo.get_product(product_id)

    def list_products(self) -> list[Product]:
        return self._repo.list_products()
