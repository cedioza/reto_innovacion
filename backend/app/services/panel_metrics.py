"""Servicio de métricas del panel: funnel de ventas (plan G5).

Compone `conversation_service` (instancia global, mismo patrón que
`app.services.proactive.ProactiveService`) y `CatalogService` para calcular,
sobre TODAS las conversaciones persistidas, el embudo global
(recomendado -> cotizado -> consentimiento -> comprado), el mismo embudo
desagregado por producto del catálogo y el corte por afiliación
(`profile.source`).

Semántica de las etapas por conversación (contrato exacto, ver
`backend/tests/test_panel_metricas.py`):

  - recomendado: `recommendation is not None`.
  - cotizado: `quote is not None`.
  - consentimiento: `application is not None` o `state` en
    {"awaiting_consent", "ready_for_payment", "finalizada_demo"}.
  - comprado: `state == "finalizada_demo"`.

Una conversación solo cuenta hacia un producto si tiene recomendación
(`recommendation.product_id`); sin recomendación no aporta a ningún producto
del `funnel_por_producto`, aunque sí participa en `totales` y
`corte_afiliacion`.
"""

from __future__ import annotations

from app.services.catalog import CatalogService
from app.services.conversation import conversation_service

_ESTADOS_CONSENTIMIENTO = {"awaiting_consent", "ready_for_payment", "finalizada_demo"}


def _tasa(numerador: int, denominador: int) -> float:
    if denominador == 0:
        return 0.0
    return round(numerador / denominador, 2)


class PanelMetricsService:
    """Calcula las métricas del panel (funnel de ventas) sobre conversaciones."""

    def __init__(self) -> None:
        self._conversation_service = conversation_service
        self._catalog_service = CatalogService()

    def metricas(self) -> dict:
        conversations = self._conversation_service.list_all()
        # Acceso al repo interno del service compartido, mismo patrón que
        # `ProactiveService.trigger` (`conversation_service._repo.save(...)`):
        # se necesita el count crudo de la tabla para distinguir "no hay
        # filas" de "hay filas pero todas corruptas" (borde no cubierto por
        # los tests; se documenta aquí la elección: si hay filas en la
        # tabla, aunque ninguna valide, `fuente` es "postgres" — hay datos,
        # aunque no cuenten).
        total_filas = self._conversation_service._repo.count()

        flags = [self._flags(conv) for conv in conversations]

        conversaciones = len(conversations)
        recomendadas = sum(1 for f in flags if f["recomendado"])
        cotizadas = sum(1 for f in flags if f["cotizado"])
        con_consentimiento = sum(1 for f in flags if f["consentimiento"])
        compradas = sum(1 for f in flags if f["comprado"])

        totales = {
            "conversaciones": conversaciones,
            "recomendadas": recomendadas,
            "cotizadas": cotizadas,
            "con_consentimiento": con_consentimiento,
            "compradas": compradas,
            "conversion_global": _tasa(compradas, conversaciones),
        }

        funnel_por_producto = [
            self._funnel_producto(product, flags)
            for product in self._catalog_service.list_products()
        ]

        corte_afiliacion = self._corte_afiliacion(conversations, flags)

        fuente = "sin_datos" if conversaciones == 0 and total_filas == 0 else "postgres"

        return {
            "fuente": fuente,
            "totales": totales,
            "funnel_por_producto": funnel_por_producto,
            "corte_afiliacion": corte_afiliacion,
        }

    # -- helpers --------------------------------------------------------

    @staticmethod
    def _flags(conversation) -> dict:
        recomendado = conversation.recommendation is not None
        cotizado = conversation.quote is not None
        consentimiento = (
            conversation.application is not None
            or conversation.state.value in _ESTADOS_CONSENTIMIENTO
        )
        comprado = conversation.state.value == "finalizada_demo"
        product_id = (
            conversation.recommendation.product_id if recomendado else None
        )
        return {
            "recomendado": recomendado,
            "cotizado": cotizado,
            "consentimiento": consentimiento,
            "comprado": comprado,
            "product_id": product_id,
            "profile": conversation.profile,
        }

    @staticmethod
    def _funnel_producto(product, flags: list[dict]) -> dict:
        del_producto = [f for f in flags if f["product_id"] == product.id]

        recomendado = len(del_producto)
        cotizado = sum(1 for f in del_producto if f["cotizado"])
        consentimiento = sum(1 for f in del_producto if f["consentimiento"])
        comprado = sum(1 for f in del_producto if f["comprado"])

        return {
            "product_id": product.id,
            "product_name": product.name,
            "categoria": product.category,
            "etapas": {
                "recomendado": recomendado,
                "cotizado": cotizado,
                "consentimiento": consentimiento,
                "comprado": comprado,
            },
            "tasas": {
                "cotizado_sobre_recomendado": _tasa(cotizado, recomendado),
                "consentimiento_sobre_cotizado": _tasa(consentimiento, cotizado),
                "comprado_sobre_consentimiento": _tasa(comprado, consentimiento),
                "comprado_sobre_recomendado": _tasa(comprado, recomendado),
            },
        }

    @staticmethod
    def _corte_afiliacion(conversations, flags: list[dict]) -> dict:
        buckets = {
            "base": {"conversaciones": 0, "compradas": 0},
            "declarado": {"conversaciones": 0, "compradas": 0},
        }

        for f in flags:
            profile = f["profile"]
            bucket = (
                "base"
                if profile is not None and profile.source == "base"
                else "declarado"
            )
            buckets[bucket]["conversaciones"] += 1
            if f["comprado"]:
                buckets[bucket]["compradas"] += 1

        return {
            nombre: {
                "conversaciones": datos["conversaciones"],
                "compradas": datos["compradas"],
                "conversion": _tasa(datos["compradas"], datos["conversaciones"]),
            }
            for nombre, datos in buckets.items()
        }
