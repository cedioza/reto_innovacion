"""Tests for the deterministic synthetic-column generator (plan C2, Fase 2 — RED).

`synthetic_for(profile: AffiliateProfile) -> dict` will live in
`app.services.synthetic`. It must be a pure function (no `random`, no shared
state): the same SERIE (and the same `household_segment`) always yields the
same synthetic dict, decided by a stable hash
(`sha256(f"{serie}:{campo}")`) — never by object identity or call order.

This module is written before `app.services.synthetic` exists, so collection
is expected to fail with an ImportError until Fase 2 implements it.
"""

from app.models.affiliate import AffiliateProfile
from app.services.synthetic import synthetic_for

SINT_KEYS = {
    "sint_tiene_vehiculo",
    "sint_tiene_credito",
    "sint_tiene_hijos",
    "sint_tipo_vivienda",
}


def _profile(
    document_number: str,
    household_segment: str | None = None,
) -> AffiliateProfile:
    return AffiliateProfile(
        document_number=document_number,
        age_range="26-40",
        household_segment=household_segment,
    )


class TestSyntheticGenerator:
    # -- determinism ---------------------------------------------------------

    def test_determinista_misma_serie_mismo_resultado(self) -> None:
        profile = _profile("S123", household_segment="RHO")

        first = synthetic_for(profile)
        second = synthetic_for(profile)

        assert first == second

    def test_deterministico_entre_instancias(self) -> None:
        profile_a = _profile("S123", household_segment="RHO")
        profile_b = _profile("S123", household_segment="RHO")

        assert profile_a is not profile_b
        assert synthetic_for(profile_a) == synthetic_for(profile_b)

    # -- shape -----------------------------------------------------------------

    def test_claves_y_tipos(self) -> None:
        result = synthetic_for(_profile("S999", household_segment="LAMBDA"))

        assert set(result.keys()) == SINT_KEYS
        assert isinstance(result["sint_tiene_vehiculo"], bool)
        assert isinstance(result["sint_tiene_credito"], bool)
        assert isinstance(result["sint_tiene_hijos"], bool)
        assert result["sint_tipo_vivienda"] in ("apartment", "house", None)

    # -- distribution over a wide sample ----------------------------------------

    def test_distribucion_en_rango_amplio(self) -> None:
        n = 400
        results = [
            synthetic_for(_profile(f"P{i:04d}", household_segment=None))
            for i in range(n)
        ]

        vehiculo_ratio = sum(r["sint_tiene_vehiculo"] for r in results) / n
        credito_ratio = sum(r["sint_tiene_credito"] for r in results) / n
        vivienda_none_ratio = (
            sum(1 for r in results if r["sint_tipo_vivienda"] is None) / n
        )

        assert 0.15 <= vehiculo_ratio <= 0.45
        assert 0.20 <= credito_ratio <= 0.50
        assert 0.20 <= vivienda_none_ratio <= 0.50

    # -- correlation with the real household segment ----------------------------

    def test_hijos_correlacionados_con_segmento(self) -> None:
        n = 300
        series = [f"H{i:04d}" for i in range(n)]

        rho_results = [
            synthetic_for(_profile(serie, household_segment="RHO"))
            for serie in series
        ]
        tau_results = [
            synthetic_for(_profile(serie, household_segment="TAU"))
            for serie in series
        ]

        rho_ratio = sum(r["sint_tiene_hijos"] for r in rho_results) / n
        tau_ratio = sum(r["sint_tiene_hijos"] for r in tau_results) / n

        assert rho_ratio > tau_ratio
        assert rho_ratio > 0.45
        assert tau_ratio < 0.45

    # -- no single-value fallback -------------------------------------------------

    def test_series_distintas_no_todas_iguales(self) -> None:
        results = [
            synthetic_for(_profile(f"V{i:04d}", household_segment=None))
            for i in range(50)
        ]

        vehiculo_values = {r["sint_tiene_vehiculo"] for r in results}

        assert vehiculo_values == {True, False}
