from pydantic import BaseModel


class Coverage(BaseModel):
    name: str
    description: str


class Exclusion(BaseModel):
    name: str
    description: str


class Adjustment(BaseModel):
    code: str
    name: str
    description: str
    premium_modifier: float


class ProductResponse(BaseModel):
    id: str
    name: str
    description: str
    coverages: list[Coverage]
    exclusions: list[Exclusion]
    adjustments: list[Adjustment]
    base_price: float
    currency: str = "COP"
