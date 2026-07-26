from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ConversationState(str, Enum):
    COLLECTING_PROFILE = "collecting_profile"
    RECOMMENDATION_READY = "recommendation_ready"
    QUOTE_READY = "quote_ready"
    AWAITING_CONSENT = "awaiting_consent"
    READY_FOR_PAYMENT = "ready_for_payment"
    FINALIZED_DEMO = "finalizada_demo"


class Message(BaseModel):
    role: str
    content: str
    type: str = "text"
    payload: Optional[dict] = None
    # sellado al crear el mensaje (ISO-8601 UTC); en datos persistidos antes de este campo se rellena al leer
    timestamp: Optional[str] = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ProfileData(BaseModel):
    property_type: Optional[str] = None
    zone: Optional[str] = None
    stratum: Optional[int] = None
    age_range: Optional[str] = None
    has_family: Optional[bool] = None
    has_children: Optional[bool] = None
    has_vehicle: Optional[bool] = None
    has_credit: Optional[bool] = None
    # Aditivos (plan B5, Fase 1): de dónde salió el perfil ("base"|"declarado")
    # y género — la base SÍ lo tiene (`AffiliateProfile.gender`), lo usa la
    # Matriz de Perfilamiento (`app.services.profiling_matrix`) para saber qué
    # NO preguntarle a un afiliado.
    source: Optional[str] = None
    gender: Optional[str] = None


class Recommendation(BaseModel):
    product_id: str
    product_name: str
    reasons: list[dict]


class QuoteDetail(BaseModel):
    currency: str = "COP"
    base_amount: float
    adjustments: list[dict] = []
    monthly_premium: float
    annual_premium: Optional[float] = None
    coverage_details: list[str]
    exclusions: list[str]


class ConsentRequest(BaseModel):
    consent_given: bool
    email: Optional[str] = None


class ConsentedApplication(BaseModel):
    session_id: str
    product_id: str
    profile: ProfileData
    recommendation: Recommendation
    quote: QuoteDetail
    consent_timestamp: str
    state: ConversationState = ConversationState.READY_FOR_PAYMENT
    email: Optional[str] = None
    handoff_token: Optional[str] = None
    insurer_name: Optional[str] = None


class ConversationCreate(BaseModel):
    document_number: Optional[str] = None
    message: Optional[Message] = None


class MessageRequest(BaseModel):
    content: str = Field(min_length=1)


class AdjustmentsRequest(BaseModel):
    adjustments: list[str]


class ConversationResponse(BaseModel):
    session_id: str
    state: ConversationState
    messages: list[Message] = []
    profile: Optional[ProfileData] = None
    recommendation: Optional[Recommendation] = None
    quote: Optional[QuoteDetail] = None
    application: Optional[ConsentedApplication] = None
    next_action: str
