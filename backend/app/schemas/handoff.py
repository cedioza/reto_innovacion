"""Schemas del handoff público hacia la aseguradora simulada.

`HandoffSummary` es deliberadamente un subconjunto sanitizado de
`ConsentedApplication`: nunca expone `email`, `profile` ni `session_id` — el
endpoint público de handoff solo debe mostrar lo necesario para que el
cliente confirme su solicitud con la aseguradora simulada.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class HandoffSummary(BaseModel):
    product_id: str
    product_name: str
    insurer_name: Optional[str] = None
    monthly_premium: float
    annual_premium: Optional[float] = None
    currency: str
    coverage_details: list[str]
    exclusions: list[str]
    state: str
    consent_timestamp: str
