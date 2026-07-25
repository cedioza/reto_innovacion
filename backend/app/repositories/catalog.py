from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import TypeAdapter

from app.core.config import settings
from app.models.product import Product

DEFAULT_CATALOG_JSON_PATH = str(
    Path(__file__).resolve().parent.parent / "data" / "catalogo" / "productos.json"
)

_products_adapter = TypeAdapter(list[Product])


@lru_cache
def _load_products(path: str) -> tuple[Product, ...]:
    """Load and validate the product catalog from a JSON file.

    Cached by path so repeated instantiations of ``CatalogRepository``
    with the same path return the exact same (immutable) data.

    Raises:
        pydantic.ValidationError: If the JSON content does not match the
            ``Product`` schema (subclass of ``ValueError``).
    """
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    products = _products_adapter.validate_python(raw)
    return tuple(products)


class CatalogRepository:
    """Catalog repository backed by a JSON file of insurance products.

    Deterministic — same path always returns the same result (cached).
    """

    def __init__(self, path: str | None = None) -> None:
        self._path = path or settings.catalog_json_path or DEFAULT_CATALOG_JSON_PATH

    def get_product(self, product_id: str) -> Product | None:
        for product in _load_products(self._path):
            if product.id == product_id:
                return product
        return None

    def list_products(self) -> list[Product]:
        return list(_load_products(self._path))
