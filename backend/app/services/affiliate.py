"""Affiliate service — profile lookup with fallback.

Two lookup paths:
1. Affiliate found → return real anonymized profile.
2. Affiliate not found → build a declared profile from conversation data.
"""

from app.repositories.affiliates import AffiliateRepository
from app.models.affiliate import AffiliateProfile
from app.schemas.conversation import ProfileData


class AffiliateService:
    def __init__(self) -> None:
        self._repo = AffiliateRepository()

    def lookup(self, document_number: str) -> AffiliateProfile | None:
        """Look up an affiliate by their anonymized document number."""
        return self._repo.find_by_document(document_number)

    def build_declared_profile(self, data: ProfileData) -> AffiliateProfile:
        """Build a fallback profile from declared (conversation) data."""
        return AffiliateProfile(
            document_number="declared",
            age_range=data.age_range or "unknown",
            stratum=data.stratum or 3,
            city=None,
            property_type=data.property_type,
            zone=data.zone or "urban",
        )

    def resolve(
        self, document_number: str | None, declared: ProfileData | None = None
    ) -> AffiliateProfile:
        """Resolve the best available profile.

        Priority:
          1. Real affiliate profile when document_number is provided.
          2. Declared profile from conversation data.
          3. Minimal default profile.
        """
        if document_number:
            profile = self.lookup(document_number)
            if profile:
                return profile

        if declared:
            return self.build_declared_profile(declared)

        return self.build_declared_profile(
            ProfileData(age_range="unknown", stratum=3)
        )
