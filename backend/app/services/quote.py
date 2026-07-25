from app.schemas.conversation import ProfileData
from app.schemas.product import ProductResponse
from app.services.catalog import CatalogService
from app.models.product import Adjustment


class QuoteService:
    """Deterministic quote engine for Hogar insurance.

    The quote is calculated from a fixed product catalog and the
    user's declared profile. Every call with the same inputs produces
    exactly the same output.
    """

    def __init__(self) -> None:
        self._catalog = CatalogService()

    def calculate_quote(
        self,
        profile: ProfileData,
        selected_adjustments: list[str] | None = None,
    ) -> dict:
        product = self._catalog.get_product("hogar-estandar")
        if not product:
            raise ValueError("Product not found")

        adjustments = selected_adjustments or []

        # -- Age risk factor --------------------------------------------------
        age_multiplier = 1.0
        if profile.age_range:
            if profile.age_range in ("18-25", "65+"):
                age_multiplier = 1.15

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

        base = product.base_price * age_multiplier
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
