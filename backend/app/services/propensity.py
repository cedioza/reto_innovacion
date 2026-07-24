"""Explainable propensity engine for Hogar insurance.

Deterministic rules-based scoring — every call with the same profile
produces the same score and reasons. The LLM explains the result;
the engine decides it.
"""

from app.schemas.conversation import ProfileData
from app.models.affiliate import AffiliateProfile


def _score_for_profile(
    profile: ProfileData | AffiliateProfile,
) -> tuple[float, list[dict]]:
    """Return (score 0..1, reasons) for the given profile."""
    reasons: list[dict] = []
    score = 0.0

    # -- Rule 1: Homeowner / property type --------------------------------
    pt = getattr(profile, "property_type", None)
    if pt in ("house", "apartment"):
        score += 0.25
        reasons.append({
            "code": "homeowner",
            "label": "Propietario o arrendatario de vivienda",
            "evidence": f"Tipo de propiedad: {pt}",
        })

    # -- Rule 2: Family / household ---------------------------------------
    age = getattr(profile, "age_range", "unknown")
    family_ages = ("26-40", "41-55")
    if age in family_ages:
        score += 0.25
        reasons.append({
            "code": "family_profile",
            "label": "Perfil familiar con necesidades de protección",
            "evidence": f"Rango de edad: {age}",
        })

    # -- Rule 3: Income tier ----------------------------------------------
    stratum = getattr(profile, "stratum", None)
    if stratum and 2 <= stratum <= 4:
        score += 0.20
        reasons.append({
            "code": "income_tier",
            "label": "Capacidad económica para prima mensual",
            "evidence": f"Estrato: {stratum}",
        })
    elif stratum and stratum >= 5:
        score += 0.10
        reasons.append({
            "code": "income_tier",
            "label": "Capacidad económica para prima mensual",
            "evidence": f"Estrato: {stratum}",
        })

    # -- Rule 4: Zone risk ------------------------------------------------
    zone = getattr(profile, "zone", None)
    if zone == "urban":
        score += 0.15
        reasons.append({
            "code": "zone_risk",
            "label": "Zona urbana con mayor exposición a hurto",
            "evidence": "Zona: urbana",
        })

    # -- Rule 5: Age extremes (lower score = higher risk) ------------------
    if age in ("18-25",):
        score -= 0.10
        reasons.append({
            "code": "age_risk",
            "label": "Perfil joven con menor prioridad en seguros de hogar",
            "evidence": f"Rango de edad: {age}",
        })

    # Clamp to [0, 1]
    score = max(0.0, min(1.0, score))
    return score, reasons


class PropensityService:
    """Deterministic, explainable propensity engine."""

    def evaluate(
        self, profile: ProfileData | AffiliateProfile
    ) -> dict:
        """Evaluate propensity for Hogar insurance.

        Returns:
            dict with:
              - score (float 0..1)
              - product_id (str)
              - reasons (list of {code, label, evidence})
              - recommended (bool) — True when score >= 0.5
        """
        score, reasons = _score_for_profile(profile)
        return {
            "score": round(score, 2),
            "product_id": "hogar-estandar",
            "reasons": reasons,
            "recommended": score >= 0.5,
        }
