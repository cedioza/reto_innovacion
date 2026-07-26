"""Explainable multi-category propensity engine.

Deterministic, rules-as-data scoring across the five catalog categories
(``hogar``, ``vida``, ``accidentes``, ``movilidad``, ``credito``) — the same
profile always produces the same per-category scores, reasons and ranking.
The LLM explains the result; this engine decides it.

``CATEGORY_RULES`` is the single source of truth: each entry declares a
category, a weight, a ``condition`` callable evaluated against the profile
(``ProfileData`` from a declared conversation, or ``AffiliateProfile`` from
the anonymized base — both accessed via ``getattr`` so either shape works),
and a reason builder (``code``/``label``/``evidence``). Adding a signal means
adding an entry here, never growing an ``if`` chain.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, is_dataclass
from typing import Callable

from pydantic import BaseModel

from app.models.affiliate import AffiliateProfile
from app.schemas.conversation import ProfileData
from app.services.catalog import CatalogService

logger = logging.getLogger(__name__)

Profile = ProfileData | AffiliateProfile


# -- Profile field accessors ---------------------------------------------
# ``getattr`` with a default so both ``ProfileData`` (declared, has
# has_children/has_vehicle/has_credit) and ``AffiliateProfile`` (base,
# has household_segment) are accepted without a branch per shape.
def _property_type(p: Profile) -> str | None:
    return getattr(p, "property_type", None)


def _age_range(p: Profile) -> str | None:
    return getattr(p, "age_range", None)


def _stratum(p: Profile) -> int | None:
    return getattr(p, "stratum", None)


def _zone(p: Profile) -> str | None:
    return getattr(p, "zone", None)


def _has_children(p: Profile) -> bool | None:
    return getattr(p, "has_children", None)


def _has_family(p: Profile) -> bool | None:
    return getattr(p, "has_family", None)


def _has_vehicle(p: Profile) -> bool | None:
    return getattr(p, "has_vehicle", None)


def _has_credit(p: Profile) -> bool | None:
    return getattr(p, "has_credit", None)


def _household_segment(p: Profile) -> str | None:
    return getattr(p, "household_segment", None)


@dataclass(frozen=True)
class CategoryRule:
    """A single declarative scoring rule for one category."""

    category: str
    code: str
    weight: float
    condition: Callable[[Profile], bool]
    label: Callable[[Profile], str]
    evidence: Callable[[Profile], str]

    def reason(self, profile: Profile) -> dict:
        return {
            "code": self.code,
            "label": self.label(profile),
            "evidence": self.evidence(profile),
        }


# -- CATEGORY_RULES ---------------------------------------------------------
# Weights are a calibratable starting point (tests fix which category wins
# per profile, not exact scores — except determinism, which compares full
# results). Codes are exact and stable; labels/evidence may be reworded.
CATEGORY_RULES: list[CategoryRule] = [
    # -- hogar ---------------------------------------------------------
    CategoryRule(
        category="hogar",
        code="homeowner",
        weight=0.45,
        condition=lambda p: _property_type(p) in ("house", "apartment"),
        label=lambda p: "Propietario o arrendatario de vivienda",
        evidence=lambda p: f"Tipo de propiedad: {_property_type(p)}",
    ),
    CategoryRule(
        category="hogar",
        code="income_tier",
        weight=0.15,
        condition=lambda p: (
            _property_type(p) is not None
            and _stratum(p) is not None
            and 2 <= _stratum(p) <= 4
        ),
        label=lambda p: "Capacidad económica para prima mensual",
        evidence=lambda p: f"Estrato: {_stratum(p)}",
    ),
    CategoryRule(
        category="hogar",
        code="zone_risk",
        weight=0.10,
        condition=lambda p: _property_type(p) is not None and _zone(p) == "urban",
        label=lambda p: "Zona urbana con mayor exposición a hurto",
        evidence=lambda p: "Zona: urbana",
    ),
    CategoryRule(
        category="hogar",
        code="age_risk",
        weight=-0.10,
        condition=lambda p: _age_range(p) == "18-25",
        label=lambda p: "Perfil joven con menor prioridad en hogar",
        evidence=lambda p: f"Rango de edad: {_age_range(p)}",
    ),
    # -- vida ------------------------------------------------------------
    CategoryRule(
        category="vida",
        code="dependents",
        weight=0.50,
        condition=lambda p: _has_children(p) is True,
        label=lambda p: "Hijos o dependientes a cargo que proteger",
        evidence=lambda p: (
            (
                f"{getattr(p, 'children_count', None)} hijo declarado"
                if getattr(p, "children_count", None) == 1
                else f"{getattr(p, 'children_count', None)} hijos declarados"
            )
            if isinstance(getattr(p, "children_count", None), int)
            and getattr(p, "children_count", None) >= 1
            else "Hijos declarados: sí"
        ),
    ),
    CategoryRule(
        category="vida",
        code="family_profile",
        weight=0.15,
        condition=lambda p: _has_family(p) is True,
        label=lambda p: "Perfil familiar con necesidades de protección",
        evidence=lambda p: "Familia a cargo: sí",
    ),
    CategoryRule(
        category="vida",
        code="life_stage",
        weight=0.15,
        condition=lambda p: _age_range(p) in ("26-40", "41-55"),
        label=lambda p: "Etapa de vida con responsabilidades familiares",
        evidence=lambda p: f"Rango de edad: {_age_range(p)}",
    ),
    CategoryRule(
        category="vida",
        code="family_segment",
        weight=0.10,
        condition=lambda p: _household_segment(p) in ("RHO", "LAMBDA"),
        label=lambda p: "Segmento familiar con consumo activo en droguería",
        evidence=lambda p: (
            f"Segmento {_household_segment(p)}: 21,7% del segmento RHO usa "
            "droguería vs 16,8% de LAMBDA (base real)"
        ),
    ),
    # -- accidentes --------------------------------------------------------
    CategoryRule(
        category="accidentes",
        code="young_profile",
        weight=0.40,
        condition=lambda p: _age_range(p) == "18-25",
        label=lambda p: "Perfil joven con mayor exposición a accidentes",
        evidence=lambda p: "50% de la base de afiliados tiene 20-35 años (base real)",
    ),
    CategoryRule(
        category="accidentes",
        code="no_dependents",
        weight=0.15,
        condition=lambda p: _has_children(p) is False and _has_family(p) is False,
        label=lambda p: "Sin dependientes: prioridad en protección personal",
        evidence=lambda p: "Sin hijos ni familia a cargo declarados",
    ),
    CategoryRule(
        category="accidentes",
        code="urban_exposure",
        weight=0.10,
        condition=lambda p: _zone(p) == "urban",
        label=lambda p: "Zona urbana con mayor accidentalidad",
        evidence=lambda p: "Zona: urbana",
    ),
    # -- movilidad -----------------------------------------------------
    CategoryRule(
        category="movilidad",
        code="vehicle_declared",
        weight=0.75,
        condition=lambda p: _has_vehicle(p) is True,
        label=lambda p: "Vehículo propio declarado que proteger",
        evidence=lambda p: "Vehículo declarado: sí",
    ),
    CategoryRule(
        category="movilidad",
        code="young_driver",
        weight=0.05,
        condition=lambda p: _age_range(p) == "18-25" and _has_vehicle(p) is True,
        label=lambda p: "Conductor joven con mayor riesgo",
        evidence=lambda p: f"Rango de edad: {_age_range(p)}",
    ),
    # Zero-weight, explanatory only: a vehicle is a high-value asset even
    # outside the young-driver bracket — keeps `vehicle_declared`'s weight
    # untouched while giving every vehicle-declared profile a second,
    # traceable reason (not just a single-signal recommendation).
    CategoryRule(
        category="movilidad",
        code="asset_protection",
        weight=0.0,
        condition=lambda p: _has_vehicle(p) is True,
        label=lambda p: "Vehículo como activo de alto valor a proteger financieramente",
        evidence=lambda p: (
            "Pérdida total o hurto del vehículo implica un costo "
            "patrimonial significativo"
        ),
    ),
    # -- credito -------------------------------------------------------------
    CategoryRule(
        category="credito",
        code="credit_declared",
        weight=0.70,
        condition=lambda p: _has_credit(p) is True,
        label=lambda p: "Crédito vigente declarado — proteger la deuda",
        evidence=lambda p: "Crédito declarado: sí",
    ),
    CategoryRule(
        category="credito",
        code="working_age",
        weight=0.10,
        condition=lambda p: (
            _age_range(p) in ("26-40", "41-55") and _has_credit(p) is True
        ),
        label=lambda p: "Edad productiva con obligaciones financieras",
        evidence=lambda p: f"Rango de edad: {_age_range(p)}",
    ),
]


def _score_category(category: str, profile: Profile) -> tuple[float, list[dict]]:
    """Sum the weights of every rule of ``category`` that applies, clamped."""
    score = 0.0
    reasons: list[dict] = []
    for rule in CATEGORY_RULES:
        if rule.category != category:
            continue
        if rule.condition(profile):
            score += rule.weight
            reasons.append(rule.reason(profile))
    return round(max(0.0, min(1.0, score)), 2), reasons


def _profile_summary(profile: Profile) -> dict:
    """Non-null fields of the profile, for the structured log."""
    if isinstance(profile, BaseModel):
        raw = profile.model_dump()
    elif is_dataclass(profile):
        raw = asdict(profile)
    else:  # pragma: no cover - defensive fallback
        raw = dict(vars(profile))
    return {k: v for k, v in raw.items() if v is not None}


class PropensityService:
    """Deterministic, explainable multi-category propensity engine."""

    def evaluate(self, profile: Profile) -> dict:
        """Score every catalog category for ``profile`` and rank them.

        Returns:
            dict with:
              - score, product_id, reasons, recommended — of the **winning**
                category (first entry of ``ranking``), kept for backward
                compatibility with callers that only knew "hogar".
              - ranking: list of ``{category, product_id, score, reasons}``,
                one entry per catalog category, sorted by score descending
                (stable tie-break: catalog order, hogar first).
        """
        products = CatalogService().list_products()

        product_by_category: dict[str, str] = {}
        ordered_categories: list[str] = []
        for product in products:
            if product.category not in product_by_category:
                product_by_category[product.category] = product.id
                ordered_categories.append(product.category)

        entries: list[dict] = []
        scores_by_category: dict[str, float] = {}
        codes_by_category: dict[str, list[str]] = {}
        for category in ordered_categories:
            score, reasons = _score_category(category, profile)
            scores_by_category[category] = score
            codes_by_category[category] = [r["code"] for r in reasons]
            entries.append(
                {
                    "category": category,
                    "product_id": product_by_category[category],
                    "score": score,
                    "reasons": reasons,
                }
            )

        # Stable sort: ties keep the catalog order already in `entries`.
        ranking = sorted(entries, key=lambda entry: -entry["score"])
        winner = ranking[0]

        logger.info(
            json.dumps(
                {
                    "profile": _profile_summary(profile),
                    "scores": scores_by_category,
                    "reason_codes": codes_by_category,
                    "winner": {
                        "category": winner["category"],
                        "product_id": winner["product_id"],
                        "score": winner["score"],
                    },
                },
                ensure_ascii=False,
            )
        )

        return {
            "score": winner["score"],
            "product_id": winner["product_id"],
            "reasons": winner["reasons"],
            "recommended": winner["score"] >= 0.5,
            "ranking": ranking,
        }
