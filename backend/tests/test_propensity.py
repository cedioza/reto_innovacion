"""Tests for the propensity engine — TDD RED phase."""

from app.services.propensity import PropensityService
from app.schemas.conversation import ProfileData


class TestPropensityService:
    def setup_method(self) -> None:
        self.service = PropensityService()

    def _profile(
        self,
        age_range: str = "26-40",
        property_type: str = "house",
        zone: str = "urban",
        stratum: int = 3,
    ) -> ProfileData:
        return ProfileData(
            age_range=age_range,
            property_type=property_type,
            zone=zone,
            stratum=stratum,
        )

    def test_deterministic_same_input_same_output(self) -> None:
        p = self._profile()
        r1 = self.service.evaluate(p)
        r2 = self.service.evaluate(p)
        assert r1["score"] == r2["score"]
        assert r1["reasons"] == r2["reasons"]

    def test_full_profile_scores_above_0_5(self) -> None:
        p = self._profile()
        result = self.service.evaluate(p)
        assert result["score"] >= 0.5
        assert result["recommended"] is True
        assert result["product_id"] == "hogar-estandar"

    def test_low_risk_profile_scores_below_0_5(self) -> None:
        p = self._profile(
            age_range="18-25",
            property_type="apartment",
            zone="rural",
            stratum=1,
        )
        result = self.service.evaluate(p)
        assert result["score"] < 0.5
        assert result["recommended"] is False

    def test_reasons_are_explicit_and_traceable(self) -> None:
        p = self._profile()
        result = self.service.evaluate(p)
        assert len(result["reasons"]) >= 3
        for reason in result["reasons"]:
            assert "code" in reason
            assert "label" in reason
            assert "evidence" in reason

    def test_young_age_reduces_score(self) -> None:
        adult = self._profile(age_range="26-40")
        young = self._profile(age_range="18-25")
        assert self.service.evaluate(adult)["score"] > self.service.evaluate(young)["score"]

    def test_score_never_exceeds_1(self) -> None:
        p = self._profile(stratum=4, zone="urban", property_type="house", age_range="41-55")
        result = self.service.evaluate(p)
        assert 0.0 <= result["score"] <= 1.0

    def test_minimal_profile_does_not_crash(self) -> None:
        p = ProfileData()
        result = self.service.evaluate(p)
        assert 0.0 <= result["score"] <= 1.0
        assert result["product_id"] == "hogar-estandar"
