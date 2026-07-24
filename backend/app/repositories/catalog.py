from app.models.product import Product, Coverage, Exclusion, Adjustment


class CatalogRepository:
    """In-memory catalog repository for Hogar insurance products.

    Deterministic — same query always returns the same result.
    Current implementation holds a single fixed product (hogar-estandar).
    """

    def __init__(self) -> None:
        self._products: dict[str, Product] = {
            "hogar-estandar": Product(
                id="hogar-estandar",
                name="Hogar Estándar",
                description=(
                    "Protección integral para tu hogar: incendio, daños "
                    "eléctricos, rotura de cristales, daños por agua y hurto."
                ),
                coverages=[
                    Coverage(
                        name="Incendio",
                        description="Cobertura ante daños por incendio, rayos y explosiones.",
                    ),
                    Coverage(
                        name="Daños Eléctricos",
                        description="Protección ante cortocircuitos, sobretensión y daños eléctricos.",
                    ),
                    Coverage(
                        name="Rotura de Cristales",
                        description="Cubre rotura de vidrios, espejos y cristales del hogar.",
                    ),
                    Coverage(
                        name="Daños por Agua",
                        description="Cobertura por daños de tuberías, filtraciones y humedad.",
                    ),
                    Coverage(
                        name="Hurto",
                        description="Protección ante robo de bienes del hogar.",
                    ),
                ],
                exclusions=[
                    Exclusion(
                        name="Desgaste Natural",
                        description="Daños por uso normal, deterioro o falta de mantenimiento.",
                    ),
                    Exclusion(
                        name="Actos Intencionales",
                        description="Daños causados intencionalmente por el tomador.",
                    ),
                    Exclusion(
                        name="Eventos Catastróficos",
                        description="Terremotos, inundaciones, erupciones volcánicas.",
                    ),
                    Exclusion(
                        name="Guerra",
                        description="Daños derivados de guerra, terrorismo o conflicto armado.",
                    ),
                ],
                adjustments=[
                    Adjustment(
                        code="fire_alarm",
                        name="Alarma Contra Incendios",
                        description="Instalación de alarma y extintor",
                        premium_modifier=0.85,
                    ),
                    Adjustment(
                        code="security_system",
                        name="Sistema de Seguridad",
                        description="Cámara y alarma perimetral",
                        premium_modifier=0.80,
                    ),
                    Adjustment(
                        code="high_value",
                        name="Contenido de Alto Valor",
                        description="Equipos electrónicos y joyas",
                        premium_modifier=1.25,
                    ),
                ],
                base_price=45_000.0,
            ),
        }

    def get_product(self, product_id: str) -> Product | None:
        return self._products.get(product_id)

    def list_products(self) -> list[Product]:
        return list(self._products.values())
