"""Componente de disparador proactivo (Reto Seguros — plan G3).

En vez de esperar a que el afiliado inicie la conversación, este servicio
identifica cohortes de afiliados con una señal de propensión clara y
calcula, para cada una, cuántos afiliados la componen (contra la base
real, tabla `afiliados`), una muestra ilustrativa y el producto que el
motor de propensión (`app.services.propensity.PropensityService`)
recomendaría para un miembro representativo de la cohorte.

`COHORTS` declara, para cada cohorte, su id, nombre, descripción,
criterio humano legible y los filtros exactos que se aplican sobre
`AffiliateRecord` vía `AffiliateService.count_cohort`/`sample_cohort`.
Las tres cohortes fueron validadas contra la base real de afiliados
(2026-07-25):

  a) familias-jovenes-drogueria: 20-35 años + segmento familiar
     LAMBDA/RHO + señal de compra en droguería (~52.428 afiliados).
  b) interes-vivienda: señal directa de interés en vivienda — cohorte
     pequeña y de alta intención (~36 afiliados).
  c) movilidad-vehiculo: atributo `sint_tiene_vehiculo`, que es un dato
     SINTÉTICO (no viene del dataset real de Colsubsidio, ver
     `app.models.affiliate_record`) etiquetado para el hackathon
     (~140.773 afiliados) — se declara así explícitamente por
     transparencia.
"""

from app.models.affiliate_record import AffiliateRecord
from app.repositories.affiliates import AffiliateRepository
from app.services.affiliate import AffiliateService
from app.services.catalog import CatalogService
from app.services.propensity import PropensityService

COHORTS = [
    {
        "id": "familias-jovenes-drogueria",
        "nombre": "Familias jóvenes con consumo en droguería",
        "descripcion": (
            "Afiliados de 20 a 35 años en el segmento familiar LAMBDA o "
            "RHO, con señal de compra en droguería (~52.428 afiliados en "
            "la base real)."
        ),
        "criterio_humano": (
            "Afiliados de 20-35 años, segmento familiar (LAMBDA/RHO), con "
            "señal de compra en droguería"
        ),
        "filtros": {
            "age_range": "20-35",
            "household_segment": ["LAMBDA", "RHO"],
            "uses_drogueria": True,
        },
    },
    {
        "id": "interes-vivienda",
        "nombre": "Interés directo en vivienda",
        "descripcion": (
            "Afiliados con señal directa de interés en vivienda: cohorte "
            "pequeña y de alta intención (~36 afiliados en la base real)."
        ),
        "criterio_humano": "Afiliados con señal directa de interés en vivienda",
        "filtros": {"uses_vivienda": True},
    },
    {
        "id": "movilidad-vehiculo",
        "nombre": "Movilidad: tenencia de vehículo",
        "descripcion": (
            "Afiliados marcados con tenencia de vehículo (~140.773 en la "
            "base real). Este atributo es SINTÉTICO: no proviene del "
            "dataset real de Colsubsidio, fue etiquetado para el "
            "hackathon (ver `app.models.affiliate_record`)."
        ),
        "criterio_humano": "Afiliados con dato sintético de tenencia de vehículo",
        "filtros": {"sint_tiene_vehiculo": True},
    },
]

# Marcas booleanas legibles para la muestra de cada cohorte (solo se listan
# las que estén en True en el registro).
_SENAL_LABELS: dict[str, str] = {
    "uses_hoteles": "hoteles",
    "uses_piscilago": "piscilago",
    "uses_drogueria": "droguería",
    "uses_agencias": "agencias",
    "uses_vivienda": "vivienda",
    "sint_tiene_vehiculo": "vehículo (sintético)",
    "sint_tiene_credito": "crédito (sintético)",
    "sint_tiene_hijos": "hijos (sintético)",
}


def _record_to_member(record: AffiliateRecord) -> dict:
    senales = [
        label
        for field, label in _SENAL_LABELS.items()
        if getattr(record, field, None) is True
    ]
    return {
        "serie": record.serie,
        "age_range": record.age_range,
        "household_segment": record.household_segment,
        "senales": senales,
    }


class ProactiveService:
    """Resuelve las cohortes proactivas contra la base real de afiliados."""

    def __init__(self) -> None:
        self._affiliate_service = AffiliateService()
        self._propensity_service = PropensityService()
        self._catalog_service = CatalogService()

    def list_cohorts(self) -> dict:
        cohortes = []
        alguna_con_datos = False

        for cohort in COHORTS:
            filtros = cohort["filtros"]
            total = self._affiliate_service.count_cohort(filtros)
            if total > 0:
                alguna_con_datos = True

            muestra_registros = self._affiliate_service.sample_cohort(
                filtros, limit=5
            )
            muestra = [_record_to_member(record) for record in muestra_registros]

            producto = None
            razones: list[str] = []
            if muestra_registros:
                perfil = AffiliateRepository._record_to_profile(muestra_registros[0])
                evaluacion = self._propensity_service.evaluate(perfil)
                product = self._catalog_service.get_product(
                    evaluacion["product_id"]
                )
                producto = {
                    "product_id": evaluacion["product_id"],
                    "product_name": product.name if product else evaluacion["product_id"],
                }
                razones = [reason["label"] for reason in evaluacion["reasons"]]

            cohortes.append(
                {
                    "id": cohort["id"],
                    "nombre": cohort["nombre"],
                    "descripcion": cohort["descripcion"],
                    "criterio_humano": cohort["criterio_humano"],
                    "total": total,
                    "muestra": muestra,
                    "producto": producto,
                    "razones": razones,
                }
            )

        return {
            "fuente": "postgres" if alguna_con_datos else "sin_datos",
            "cohortes": cohortes,
        }
