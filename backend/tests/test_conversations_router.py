from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


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
