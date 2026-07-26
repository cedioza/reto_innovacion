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

    def compare(
        self,
        profile: ProfileData,
        product_id: str,
        adjustments_a: list[str] | None = None,
        adjustments_b: list[str] | None = None,
    ) -> dict:
        """Primitiva única de comparación actual vs. propuesta.

        Centraliza el cálculo que hoy vive duplicado en la tool del bot
        (`_ajustar_comparar` en `agent_tools.py`) y en el endpoint REST
        (`ConversationService.apply_adjustments`): bot, REST y panel deben
        mostrar exactamente el mismo peso para la misma comparación entre
        dos combinaciones de ajustes de un mismo perfil y producto.
        """
        codes_a = adjustments_a or []
        codes_b = adjustments_b or []

        actual = self.calculate_quote(profile, codes_a, product_id)
        propuesta = self.calculate_quote(profile, codes_b, product_id)

        diferencia_mensual = round(
            propuesta["monthly_premium"] - actual["monthly_premium"], 2
        )
        diferencia_anual = round(
            propuesta["annual_premium"] - actual["annual_premium"], 2
        )

        ajustes_activados = [code for code in codes_b if code not in codes_a]
        ajustes_retirados = [code for code in codes_a if code not in codes_b]

        product = self._catalog.get_product(product_id)
        ajustes_disponibles = [
            {"code": adj.code, "name": adj.name, "description": adj.description}
            for adj in (product.adjustments if product else [])
        ]

        return {
            "actual": actual,
            "propuesta": propuesta,
            "diferencia_mensual": diferencia_mensual,
            "diferencia_anual": diferencia_anual,
            "ajustes_activados": ajustes_activados,
            "ajustes_retirados": ajustes_retirados,
            "ajustes_disponibles": ajustes_disponibles,
        }
