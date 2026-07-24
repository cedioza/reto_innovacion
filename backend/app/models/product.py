from dataclasses import dataclass, field


@dataclass
class Coverage:
    name: str
    description: str


@dataclass
class Exclusion:
    name: str
    description: str


@dataclass
class Adjustment:
    code: str
    name: str
    description: str
    premium_modifier: float


@dataclass
class Product:
    id: str
    name: str
    description: str
    coverages: list[Coverage]
    exclusions: list[Exclusion]
    adjustments: list[Adjustment]
    base_price: float
    currency: str = "COP"
