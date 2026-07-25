"""Regression test: REST API and channel webhooks must share one
ConversationService instance so sessions created on one channel are
visible from the other.
"""

from fastapi.testclient import TestClient

from app.main import app
from app.services.channel_handler import ChannelHandler
from app.services.conversation import conversation_service

client = TestClient(app)


class TestSharedConversationState:
    def test_session_created_via_rest_is_visible_to_shared_service(self) -> None:
        """The conversations router must use the shared module-level
        ``conversation_service`` instance, not a private one."""
        resp = client.post(
            "/api/v1/conversations",
            json={"message": {"role": "user", "content": "hola"}},
        )
        assert resp.status_code == 201
        session_id = resp.json()["session_id"]

        session = conversation_service.get(session_id)
        assert session is not None
        assert session.session_id == session_id

    def test_session_created_via_channel_handler_is_visible_via_rest_api(self) -> None:
        """A default ChannelHandler() uses the shared service, so a
        session it creates must be readable through the REST API."""
        handler = ChannelHandler()
        handler.handle_incoming("whatsapp", "user-shared-state-test", "hola")

        session_id = handler._sessions["user-shared-state-test"]

        resp = client.get(f"/api/v1/conversations/{session_id}")
        assert resp.status_code == 200
        assert resp.json()["session_id"] == session_id
