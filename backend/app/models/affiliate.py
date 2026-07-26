from dataclasses import dataclass


@dataclass(slots=True)
class AffiliateProfile:
    """Anonymized affiliate profile used for propensity scoring.

    Fields map to the real Colsubsidio dataset columns (SERIE-based
    lookup): SERIE, GENERO, RANGO_EDAD, RANGO_SALARIAL, CATEGORIA,
    SEGMENTO_GRUPO_FAMILIAR, SEGMENTO_POBLACIONAL, PIRAMIDE_NUEVA,
    EMPRESA_FOCO, CIUDAD_AFILIADO plus the five consumption marks
    (HOTELES, PISCILAGO, DROGUERIA, AGENCIAS, VIVIENDA).

    The real dataset does not provide `stratum`: it keeps a default of 3
    (asked in conversation instead).

    `has_children`, `has_vehicle`, `has_credit` and `property_type` are not
    part of the real dataset either. When the profile comes from the
    database, they are filled from the synthetic `sint_*` columns of
    `AffiliateRecord` (`sint_tiene_hijos`, `sint_tiene_vehiculo`,
    `sint_tiene_credito`, `sint_tipo_vivienda`) — see
    `app.repositories.affiliates._record_to_profile`. On the CSV/xlsx
    fallback path (which lacks those columns) they stay `None`. For
    non-affiliates the whole profile is declared from conversation, and
    these fields come from what the client said.

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
    has_children: bool | None = None
    has_vehicle: bool | None = None
    has_credit: bool | None = None
