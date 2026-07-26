"""DTOs de respuesta para el panel de cohortes del disparador proactivo.

Nunca se expone `AffiliateRecord` (SQLModel) directamente: `ProactiveService`
devuelve dicts planos con esta forma, validados aquí antes de salir por la
API.
"""

from pydantic import BaseModel


class CohortMember(BaseModel):
    serie: str
    age_range: str
    household_segment: str | None = None
    senales: list[str]


class CohortProduct(BaseModel):
    product_id: str
    product_name: str


class Cohort(BaseModel):
    id: str
    nombre: str
    descripcion: str
    criterio_humano: str
    total: int
    muestra: list[CohortMember]
    producto: CohortProduct | None = None
    razones: list[str] = []


class CohortsResponse(BaseModel):
    fuente: str
    cohortes: list[Cohort]
