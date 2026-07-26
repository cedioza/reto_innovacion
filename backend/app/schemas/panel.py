"""DTOs de respuesta para el panel de cohortes del disparador proactivo.

Nunca se expone `AffiliateRecord` (SQLModel) directamente: `ProactiveService`
devuelve dicts planos con esta forma, validados aquí antes de salir por la
API.
"""

from pydantic import BaseModel, Field


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


class TriggerRequest(BaseModel):
    serie: str = Field(min_length=1)


class TriggerResponse(BaseModel):
    session_id: str
    serie: str
    producto: CohortProduct
    mensaje_apertura: str


# -- Vista de clientes (plan G4, Fase 3): dicts planos de `PanelClientesService`
# validados aquí antes de salir por la API (mismo patrón que las Cohortes). --


class ClienteResumen(BaseModel):
    cliente_id: str
    serie: str | None = None
    afiliado: bool
    nombre: str | None = None
    email: str | None = None
    conversaciones: int
    solicitudes: int
    ultimo_estado: str | None = None
    ultima_actividad: str | None = None


class ClientesResponse(BaseModel):
    total: int
    clientes: list[ClienteResumen]


class PerfilItem(BaseModel):
    campo: str
    valor: str
    origen: str


class OfertaItem(BaseModel):
    session_id: str
    product_id: str
    product_name: str
    tipo: str
    fecha: str | None = None


class CotizacionItem(BaseModel):
    session_id: str
    product_id: str | None = None
    product_name: str | None = None
    monthly_premium: float
    fecha: str | None = None


class SolicitudItem(BaseModel):
    session_id: str
    product_id: str
    estado: str
    comprado: bool
    email: str | None = None
    fecha: str


class ConversacionResumen(BaseModel):
    session_id: str
    canal: str | None = None
    estado: str
    mensajes: int
    inicio: str
    ultima_actividad: str


class ClienteFicha(BaseModel):
    cliente_id: str
    serie: str | None = None
    afiliado: bool
    fuente_perfil: str
    perfil: list[PerfilItem]
    ofertas: list[OfertaItem]
    cotizaciones: list[CotizacionItem]
    solicitudes: list[SolicitudItem]
    conversaciones: list[ConversacionResumen]
