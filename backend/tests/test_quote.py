"""Tests for the quote engine — TDD RED phase."""

from app.services.quote import QuoteService
from app.schemas.conversation import ProfileData


class TestQuoteService:
    def setup_method(self) -> None:
        self.service = QuoteService()

    def _make_profile(
        self,
        age_range: str | None = "26-40",
        property_type: str | None = "house",
        zone: str | None = "urban",
        stratum: int | None = 3,
    ) -> ProfileData:
        return ProfileData(
            age_range=age_range,
            property_type=property_type,
            zone=zone,
            stratum=stratum,
        )

    def test_same_profile_same_price(self) -> None:
        profile = self._make_profile()
        q1 = self.service.calculate_quote(profile)
        q2 = self.service.calculate_quote(profile)
        assert q1["monthly_premium"] == q2["monthly_premium"]
        assert q1["annual_premium"] == q2["annual_premium"]

    def test_fire_alarm_reduces_premium(self) -> None:
        profile = self._make_profile()
        base = self.service.calculate_quote(profile)
        adjusted = self.service.calculate_quote(
            profile, selected_adjustments=["fire_alarm"]
        )
        assert adjusted["monthly_premium"] < base["monthly_premium"]

    def test_high_value_increases_premium(self) -> None:
        profile = self._make_profile()
        base = self.service.calculate_quote(profile)
        adjusted = self.service.calculate_quote(
            profile, selected_adjustments=["high_value"]
        )
        assert adjusted["monthly_premium"] > base["monthly_premium"]

    def test_no_adjustments_monthly_is_base_divided_12(self) -> None:
        profile = self._make_profile()
        quote = self.service.calculate_quote(profile)
        expected_monthly = round(quote["annual_premium"] / 12, 2)
        assert quote["monthly_premium"] == expected_monthly

    def test_young_age_increases_premium(self) -> None:
        adult = self._make_profile(age_range="26-40")
        young = self._make_profile(age_range="18-25")
        adult_q = self.service.calculate_quote(adult)
        young_q = self.service.calculate_quote(young)
        assert young_q["annual_premium"] > adult_q["annual_premium"]

    def test_senior_age_increases_premium(self) -> None:
        adult = self._make_profile(age_range="26-40")
        senior = self._make_profile(age_range="65+")
        adult_q = self.service.calculate_quote(adult)
        senior_q = self.service.calculate_quote(senior)
        assert senior_q["annual_premium"] > adult_q["annual_premium"]

    def test_quote_has_coverage_and_exclusions(self) -> None:
        profile = self._make_profile()
        quote = self.service.calculate_quote(profile)
        assert len(quote["coverage_details"]) > 0
        assert len(quote["exclusions"]) > 0
        assert quote["currency"] == "COP"
