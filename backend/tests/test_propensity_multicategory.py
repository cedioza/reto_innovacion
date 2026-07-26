"""Tests for the multi-category propensity engine — TDD RED phase.

Covers criteria for the explainable multi-category propensity engine:
1. 5 distinct canonical profiles win 5 distinct products, each with >=2 reasons.
2. Determinism: same profile -> same full ranking and score.
3. Enriched data changes the ranking (e.g. declaring a vehicle).
4. Ranking shape: 5 entries, one per category, sorted desc, scores in [0, 1].
5. Result is JSON-safe.
6. Empty profile falls back deterministically to hogar-estandar, not recommended.
7. Structured log with the full scoring is emitted on evaluate().
"""

import json
import logging

from app.services.propensity import PropensityService
from app.schemas.conversation import ProfileData

CATEGORIES = {"hogar", "accidentes", "vida", "movilidad", "credito"}


class TestMultiCategoryPropensity:
    def setup_method(self) -> None:
        self.service = PropensityService()

    # -- Criterio 1 --------------------------------------------------------
    def test_five_canonical_profiles_win_five_distinct_products(self) -> None:
        profiles = {
            "hogar": ProfileData(
                age_range="26-40", property_type="house", zone="urban", stratum=3
            ),
            "vida": ProfileData(
                age_range="26-40", has_children=True, has_family=True
            ),
            "accidentes": ProfileData(
                age_range="18-25", zone="urban", has_children=False
            ),
            "movilidad": ProfileData(age_range="26-40", has_vehicle=True),
            "credito": ProfileData(age_range="41-55", has_credit=True),
        }
        expected_product_ids = {
            "hogar": "hogar-estandar",
            "vida": "vida-basico",
            "accidentes": "accidentes-personales",
            "movilidad": "movilidad-auto",
            "credito": "credito-vida-deudor",
        }

        winners = {}
        for category, profile in profiles.items():
            result = self.service.evaluate(profile)
            winners[category] = result["product_id"]
            assert result["product_id"] == expected_product_ids[category]
            assert len(result["reasons"]) >= 2
            for reason in result["reasons"]:
                assert "code" in reason
                assert "label" in reason
                assert "evidence" in reason

        assert len(set(winners.values())) == 5

    # -- Criterio 2 ----------------------------------------------------------
    def test_deterministic_ranking_for_vida_profile(self) -> None:
        p = ProfileData(age_range="26-40", has_children=True, has_family=True)
        r1 = self.service.evaluate(p)
        r2 = self.service.evaluate(p)
        assert r1["ranking"] == r2["ranking"]
        assert r1["score"] == r2["score"]

    # -- Criterio 3 ------------------------------------------------------------
    def test_enriched_data_changes_ranking_winner(self) -> None:
        base_profile = ProfileData(
            age_range="26-40", property_type="house", zone="urban", stratum=3
        )
        base_result = self.service.evaluate(base_profile)
        assert base_result["product_id"] == "hogar-estandar"

        enriched_profile = ProfileData(
            age_range="26-40",
            property_type="house",
            zone="urban",
            stratum=3,
            has_vehicle=True,
        )
        enriched_result = self.service.evaluate(enriched_profile)
        assert enriched_result["product_id"] == "movilidad-auto"
        assert any(
            reason["code"] == "vehicle_declared"
            for reason in enriched_result["reasons"]
        )

    # -- Criterio 4 ------------------------------------------------------------
    def test_ranking_shape_and_ordering(self) -> None:
        p = ProfileData(
            age_range="26-40", property_type="house", zone="urban", stratum=3
        )
        result = self.service.evaluate(p)
        ranking = result["ranking"]

        assert len(ranking) == 5
        assert {entry["category"] for entry in ranking} == CATEGORIES

        for entry in ranking:
            assert "category" in entry
            assert "product_id" in entry
            assert "score" in entry
            assert "reasons" in entry
            assert 0.0 <= entry["score"] <= 1.0

        scores = [entry["score"] for entry in ranking]
        assert scores == sorted(scores, reverse=True)

        assert result["product_id"] == ranking[0]["product_id"]
        assert result["score"] == ranking[0]["score"]

    # -- Criterio 5 ------------------------------------------------------------
    def test_result_is_json_safe(self) -> None:
        p = ProfileData(age_range="41-55", has_credit=True)
        result = self.service.evaluate(p)
        json.dumps(result)  # must not raise

    # -- Criterio 6 ------------------------------------------------------------
    def test_empty_profile_falls_back_to_hogar_not_recommended(self) -> None:
        p = ProfileData()
        result = self.service.evaluate(p)
        assert result["product_id"] == "hogar-estandar"
        assert result["recommended"] is False
        assert result["score"] == result["ranking"][0]["score"]

    # -- Criterio 7 ------------------------------------------------------------
    def test_evaluate_emits_structured_log_with_all_categories(
        self, caplog
    ) -> None:
        p = ProfileData(
            age_range="26-40", property_type="house", zone="urban", stratum=3
        )
        with caplog.at_level(logging.INFO, logger="app.services.propensity"):
            self.service.evaluate(p)

        records = [
            r
            for r in caplog.records
            if r.name == "app.services.propensity"
        ]
        assert records, "expected at least one log record from the propensity module"

        matching = [
            r.getMessage()
            for r in records
            if "hogar" in r.getMessage()
            and "movilidad" in r.getMessage()
            and "credito" in r.getMessage()
        ]
        assert matching, (
            "expected a log record whose message mentions the 5 categories"
        )
