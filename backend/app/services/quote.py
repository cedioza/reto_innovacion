from app.schemas.conversation import ProfileData
from app.schemas.product import ProductResponse
from app.services.catalog import CatalogService
from app.models.product import Adjustment


class QuoteService:
    """Deterministic quote engine for any product in the catalog.

    The quote is calculated from a fixed product catalog and the
    user's declared profile. Every call with the same inputs produces
    exactly the same output.

    Risk factors (e.g. age range, vehicle type) come from each
    product's own `factors` block in the catalog and are applied
    generically: for every factor name declared by the product, the
    matching attribute is read off the profile and its declared value
    looked up in the factor's buckets. Profile fields not present, or
    bucket values not listed for that factor, are neutral (x1.0).
    """

    def __init__(self) -> None:
        self._catalog = CatalogService()

    def calculate_quote(
        self,
        profile: ProfileData,
        selected_adjustments: list[str] | None = None,
        product_id: str = "hogar-estandar",
    ) -> dict:
        product = self._catalog.get_product(product_id)
        if not product:
            raise ValueError("Product not found")

        adjustments = selected_adjustments or []

        # -- Catalog-driven risk factors ---------------------------------------
        factor_multiplier = 1.0
        for factor_name, buckets in (product.factors or {}).items():
            value = getattr(profile, factor_name, None)
            if value is not None:
                factor_multiplier *= buckets.get(str(value), 1.0)

        # -- Apply optional adjustments ---------------------------------------
        adjustment_details: list[dict] = []
        modifier = 1.0
        for adj_code in adjustments:
            adj = next(
                (a for a in product.adjustments if a.code == adj_code), None
            )
            if adj:
                modifier *= adj.premium_modifier
                adjustment_details.append({
                    "code": adj.code,
                    "name": adj.name,
                    "description": adj.description,
                    "premium_modifier": adj.premium_modifier,
                })

        base = product.base_price * factor_multiplier
        annual_premium = round(base * modifier, 2)
        monthly_premium = round(annual_premium / 12, 2)

        return {
            "base_amount": round(base, 2),
            "adjustments": adjustment_details,
            "monthly_premium": monthly_premium,
            "annual_premium": annual_premium,
            "currency": "COP",
            "coverage_details": [c.description for c in product.coverages],
            "exclusions": [e.name for e in product.exclusions],
        }
