"""Tests for conversation orchestration — TDD RED phase."""

from datetime import datetime

import pytest

from app.services.conversation import ConversationService
from app.schemas.conversation import (
    ConversationCreate,
    ProfileData,
    Message,
)


class TestConversationService:
    def setup_method(self) -> None:
        self.service = ConversationService()

    def test_create_returns_session_in_collecting_state(self) -> None:
        body = ConversationCreate(message=Message(role="user", content="Hola"))
        session = self.service.create(body)
        assert session.session_id is not None
        assert session.state.value == "collecting_profile"
        assert session.next_action is not None

    def test_create_without_message_works(self) -> None:
        body = ConversationCreate()
        session = self.service.create(body)
        assert session.session_id is not None

    def test_get_nonexistent_session_returns_none(self) -> None:
        result = self.service.get("non-existent")
        assert result is None

    def test_get_existing_session_returns_it(self) -> None:
        body = ConversationCreate(message=Message(role="user", content="test"))
        created = self.service.create(body)
        fetched = self.service.get(created.session_id)
        assert fetched is not None
        assert fetched.session_id == created.session_id

    def test_update_profile_returns_recommendation_and_quote(self) -> None:
        body = ConversationCreate(message=Message(role="user", content="Quiero proteger mi casa"))
        session = self.service.create(body)

        profile = ProfileData(
            age_range="26-40",
            property_type="house",
            zone="urban",
            stratum=3,
        )
        updated = self.service.update_profile(session.session_id, profile)
        assert updated.state.value == "quote_ready"
        assert updated.recommendation is not None
        assert updated.quote is not None
        assert len(updated.recommendation.reasons) > 0

    def test_flow_messages_carry_timestamp(self) -> None:
        body = ConversationCreate(message=Message(role="user", content="Quiero proteger mi casa"))
        session = self.service.create(body)

        profile = ProfileData(
            age_range="26-40",
            property_type="house",
            zone="urban",
            stratum=3,
        )
        updated = self.service.update_profile(session.session_id, profile)

        assert len(updated.messages) > 0
        for m in updated.messages:
            assert m.timestamp is not None
            datetime.fromisoformat(m.timestamp)

    def test_update_profile_without_session_raises_error(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            self.service.update_profile("invalid", ProfileData())

    def test_accept_quote_transitions_to_awaiting_consent(self) -> None:
        body = ConversationCreate(message=Message(role="user", content="test"))
        session = self.service.create(body)

        profile = ProfileData(age_range="26-40", property_type="house", zone="urban", stratum=3)
        session = self.service.update_profile(session.session_id, profile)

        accepted = self.service.accept_quote(session.session_id)
        assert accepted.state.value == "awaiting_consent"
