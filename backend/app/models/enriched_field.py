"""Modelo SQLModel para la tabla `perfil_enriquecido` (perfil enriquecido, A4).

Registro EAV del perfil enriquecido declarado en conversación (A4): un dato
por fila, última escritura gana al leer; `serie` permite memoria cross-sesión
para afiliados identificados.

No se usa `from __future__ import annotations` aquí: SQLModel con `table=True`
necesita resolver los tipos en tiempo de definición para construir las
columnas SQL, y los strings diferidos rompen esa resolución.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class EnrichedFieldRecord(SQLModel, table=True):
    """Un dato del perfil enriquecido, asociado a sesión y (opcionalmente) serie."""

    __tablename__ = "perfil_enriquecido"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    serie: Optional[str] = Field(default=None, index=True)
    campo: str
    valor: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
