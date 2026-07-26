"""Modelo SQLModel para la tabla `afiliados` (fuente primaria de perfiles).

No se usa `from __future__ import annotations` aquí: SQLModel con `table=True`
necesita resolver los tipos en tiempo de definición para construir las
columnas SQL, y los strings diferidos rompen esa resolución.

Las columnas se dividen en dos grupos, claramente separados:

- Columnas reales: espejo 1:1 del dataset real de Colsubsidio (SERIE,
  GENERO, RANGO_EDAD, RANGO_SALARIAL, CATEGORIA, SEGMENTO_GRUPO_FAMILIAR,
  SEGMENTO_POBLACIONAL, PIRAMIDE_NUEVA, EMPRESA_FOCO, CIUDAD_AFILIADO y las
  cinco marcas de consumo HOTELES/PISCILAGO/DROGUERIA/AGENCIAS/VIVIENDA).
- Columnas sintéticas (prefijo `sint_`): atributos generados para el
  hackathon que no existen en el dataset real (vehículo, crédito, hijos,
  tipo de vivienda). Decisión de equipo 2026-07-24: se mantienen separadas
  y explícitamente marcadas para no confundirlas con datos reales del
  dataset al momento de explicar o auditar el scoring.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class AffiliateRecord(SQLModel, table=True):
    """Perfil de afiliado persistido, indexado por `serie` (SERIE del dataset)."""

    __tablename__ = "afiliados"

    # -- columnas reales (espejo del dataset) --------------------------------
    serie: str = Field(primary_key=True)
    age_range: str
    gender: Optional[str] = None
    salary_range: Optional[str] = None
    category: Optional[str] = None
    household_segment: Optional[str] = None
    population_segment: Optional[str] = None
    pyramid: Optional[str] = None
    empresa_foco: Optional[str] = None
    city: Optional[str] = None
    uses_hoteles: Optional[bool] = None
    uses_piscilago: Optional[bool] = None
    uses_drogueria: Optional[bool] = None
    uses_agencias: Optional[bool] = None
    uses_vivienda: Optional[bool] = None

    # -- columnas sintéticas (no vienen del dataset real) --------------------
    sint_tiene_vehiculo: Optional[bool] = None
    sint_tiene_credito: Optional[bool] = None
    sint_tiene_hijos: Optional[bool] = None
    sint_tipo_vivienda: Optional[str] = None

    loaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
