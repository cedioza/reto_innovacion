from dataclasses import dataclass


@dataclass
class AffiliateProfile:
    """Anonymized affiliate profile used for propensity scoring.

    Fields map to the anonymized dataset columns (SERIE-based lookup).
    Non-affiliates receive a declared profile built from conversation.
    """

    document_number: str
    age_range: str
    stratum: int
    city: str | None = None
    property_type: str | None = None
    zone: str | None = None
    household_segment: str | None = None
    population_segment: str | None = None
    salary_range: str | None = None
