"""Generador determinista de columnas sintéticas del complemento `afiliados`.

El dataset real de Colsubsidio no trae vehículo, crédito, hijos ni tipo de
vivienda. Decisión de equipo (2026-07-24): para el hackathon se completan
estas columnas con valores sintéticos, deterministas por SERIE (nunca con
`random`), para que la carga sea reproducible y el resultado defendible ante
una auditoría ("por qué este afiliado tiene sint_tiene_vehiculo=True" siempre
responde lo mismo, sin depender del orden de carga ni de la instancia que lo
calculó). Las distribuciones son verosímiles y calibrables ajustando los
umbrales de este módulo, no un intento de modelar la población real.
"""

from __future__ import annotations

import hashlib

from app.models.affiliate import AffiliateProfile

_HIJOS_SEGMENTOS_ALTOS = ("RHO", "LAMBDA")


def _fraction(serie: str, campo: str) -> float:
    """Fracción estable en [0, 1] derivada de `sha256(f"{serie}:{campo}")`.

    Mismo (serie, campo) -> mismo float siempre. Distintos `campo` para la
    misma serie dan fracciones independientes entre sí (evita que todas las
    columnas sintéticas de un mismo afiliado queden correlacionadas por
    construcción).
    """
    digest = hashlib.sha256(f"{serie}:{campo}".encode()).hexdigest()[:8]
    return int(digest, 16) / 0xFFFFFFFF


def synthetic_for(profile: AffiliateProfile) -> dict:
    """Calcula las columnas sintéticas del complemento para `profile`.

    Devuelve un dict con `sint_tiene_vehiculo`, `sint_tiene_credito`,
    `sint_tiene_hijos` (bool) y `sint_tipo_vivienda`
    ("apartment" | "house" | None).
    """
    serie = profile.document_number

    tiene_vehiculo = _fraction(serie, "vehiculo") < 0.28
    tiene_credito = _fraction(serie, "credito") < 0.35

    hijos_umbral = (
        0.65 if profile.household_segment in _HIJOS_SEGMENTOS_ALTOS else 0.25
    )
    tiene_hijos = _fraction(serie, "hijos") < hijos_umbral

    vivienda_fraccion = _fraction(serie, "vivienda")
    if vivienda_fraccion < 0.40:
        tipo_vivienda = "apartment"
    elif vivienda_fraccion < 0.65:
        tipo_vivienda = "house"
    else:
        tipo_vivienda = None

    return {
        "sint_tiene_vehiculo": tiene_vehiculo,
        "sint_tiene_credito": tiene_credito,
        "sint_tiene_hijos": tiene_hijos,
        "sint_tipo_vivienda": tipo_vivienda,
    }
