from dataclasses import dataclass


@dataclass(slots=True)
class AffiliateProfile:
    """Anonymized affiliate profile used for propensity scoring.

    Fields map to the real Colsubsidio dataset columns (SERIE-based
    lookup): SERIE, GENERO, RANGO_EDAD, RANGO_SALARIAL, CATEGORIA,
    SEGMENTO_GRUPO_FAMILIAR, SEGMENTO_POBLACIONAL, PIRAMIDE_NUEVA,
    EMPRESA_FOCO, CIUDAD_AFILIADO plus the five consumption marks
    (HOTELES, PISCILAGO, DROGUERIA, AGENCIAS, VIVIENDA).

    The real dataset does not provide `stratum` or `property_type`:
    `stratum` keeps a default of 3 and `property_type` stays `None`
    (both are asked in conversation instead).

    Non-affiliates receive a declared profile built from conversation.
    """

    document_number: str
    age_range: str
    stratum: int = 3
    city: str | None = None
    property_type: str | None = None
    zone: str | None = None
    household_segment: str | None = None
    population_segment: str | None = None
    salary_range: str | None = None
    gender: str | None = None
    category: str | None = None
    pyramid: str | None = None
    empresa_foco: str | None = None
    uses_hoteles: bool | None = None
    uses_piscilago: bool | None = None
    uses_drogueria: bool | None = None
    uses_agencias: bool | None = None
    uses_vivienda: bool | None = None
