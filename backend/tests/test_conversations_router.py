from fastapi.testclient import TestClient

from app.main import app
from app.services.integrations.gemini_client import FALLBACK_MESSAGE, GeminiReply

import app.services.orchestrator as orchestrator

client = TestClient(app)


def _scripted_llm(replies: list[GeminiReply]):
    """Fábrica de un `generate_reply` guionado (sin red).

    Devuelve una función con la firma de
    `generate_reply(contents, *, tools=None, system_instruction=None)` que
    responde con `replies` en orden y registra cada llamada en `.calls`. Si
    el guion se agota, falla con AssertionError (más llamadas que
    respuestas guionadas).
    """

    calls: list[dict] = []

    def _generate_reply(contents, *, tools=None, system_instruction=None):
        calls.append(
            {
                "contents": contents,
                "tools": tools,
                "system_instruction": system_instruction,
            }
        )
        assert len(calls) <= len(replies), (
            "LLM script exhausted: more calls than scripted replies"
        )
        return replies[len(calls) - 1]

    _generate_reply.calls = calls
    return _generate_reply


class TestCreateConversation:
    def test_without_document_number_returns_201(self):
        response = client.post(
            "/api/v1/conversations",
            json={"message": {"role": "user", "content": "hello"}},
        )
        assert response.status_code == 201
        data = response.json()
        assert "session_id" in data
        assert len(data["session_id"]) > 0

    def test_with_document_number_returns_201(self):
        response = client.post(
            "/api/v1/conversations",
            json={
                "message": {"role": "user", "content": "hello"},
                "document_number": "12345678",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "session_id" in data


class TestGetConversation:
    def test_valid_id_returns_200(self):
        create_resp = client.post(
            "/api/v1/conversations",
            json={"message": {"role": "user", "content": "hello"}},
        )
        session_id = create_resp.json()["session_id"]

        response = client.get(f"/api/v1/conversations/{session_id}")
        assert response.status_code == 200

    def test_invalid_id_returns_404(self):
        response = client.get("/api/v1/conversations/nonexistent-id")
        assert response.status_code == 404


class TestPostMessage:
    """Tests for `POST /api/v1/conversations/{session_id}/message` — Fase 3.

    El endpoint no existe todavía (Fase 3 del plan A3): estos tests deben
    fallar por 404/405 del router (ruta inexistente), no por errores de
    importación. El LLM siempre está guionado vía monkeypatch de
    `orchestrator.generate_reply` (nunca red real).
    """

    def _create_session(self) -> str:
        response = client.post("/api/v1/conversations", json={})
        assert response.status_code == 201
        return response.json()["session_id"]

    def test_happy_path_returns_200_with_updated_messages(self, monkeypatch):
        session_id = self._create_session()
        llm = _scripted_llm(
            [GeminiReply(kind="text", text="¡Hola! Cuéntame de tu casa")]
        )
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        response = client.post(
            f"/api/v1/conversations/{session_id}/message",
            json={"content": "hola"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id

        last_two = data["messages"][-2:]
        assert last_two[0]["role"] == "user"
        assert last_two[0]["content"] == "hola"
        assert last_two[1]["role"] == "assistant"
        assert last_two[1]["content"] == "¡Hola! Cuéntame de tu casa"

    def test_unknown_session_returns_404_without_calling_llm(self, monkeypatch):
        llm = _scripted_llm([])  # falla si se llama: guion vacío
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        response = client.post(
            "/api/v1/conversations/no-existe/message",
            json={"content": "hola"},
        )

        assert response.status_code == 404
        assert len(llm.calls) == 0

    def test_empty_content_returns_422(self):
        session_id = self._create_session()

        response = client.post(
            f"/api/v1/conversations/{session_id}/message",
            json={"content": ""},
        )

        assert response.status_code == 422

    def test_missing_content_returns_422(self):
        session_id = self._create_session()

        response = client.post(
            f"/api/v1/conversations/{session_id}/message",
            json={},
        )

        assert response.status_code == 422

    def test_llm_down_returns_fallback_message(self, monkeypatch):
        session_id = self._create_session()
        llm = _scripted_llm([GeminiReply(kind="error", text=FALLBACK_MESSAGE)])
        monkeypatch.setattr(orchestrator, "generate_reply", llm)

        response = client.post(
            f"/api/v1/conversations/{session_id}/message",
            json={"content": "hola"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["messages"][-1]["role"] == "assistant"
        assert data["messages"][-1]["content"] == FALLBACK_MESSAGE
