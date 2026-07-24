"""End-to-end happy path test for the full insurance conversation flow.

Tests the complete pipeline via TestClient without mocking:
  POST /conversations → POST /{id}/profile → POST /{id}/accept →
  POST /{id}/consent → GET /{id}

This is a BEHAVIORAL test — it validates the full orchestrated flow,
not individual component internals.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestHappyPath:
    """Full happy path: create → profile → accept → consent → verify."""

    def test_full_happy_path(self) -> None:
        # -- Step 1: Create conversation ------------------------------------
        resp = client.post(
            "/api/v1/conversations",
            json={
                "message": {
                    "role": "user",
                    "content": "Quiero proteger mi casa",
                }
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        session_id = data["session_id"]
        assert session_id is not None
        assert data["state"] == "collecting_profile"
        assert "next_action" in data

        # -- Step 2: Update profile (triggers recommendation + quote) -------
        resp = client.post(
            f"/api/v1/conversations/{session_id}/profile",
            json={
                "age_range": "26-40",
                "property_type": "house",
                "zone": "urban",
                "stratum": 3,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["state"] == "quote_ready"
        assert data["recommendation"] is not None
        assert data["recommendation"]["product_id"] == "hogar-estandar"
        assert len(data["recommendation"]["reasons"]) > 0
        assert data["quote"] is not None
        assert data["quote"]["monthly_premium"] > 0
        assert len(data["quote"]["coverage_details"]) > 0
        assert len(data["quote"]["exclusions"]) > 0

        # -- Step 3: Accept quote -------------------------------------------
        resp = client.post(f"/api/v1/conversations/{session_id}/accept")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["state"] == "awaiting_consent"

        # -- Step 4: Submit consent -----------------------------------------
        resp = client.post(
            f"/api/v1/conversations/{session_id}/consent",
            json={"consent_given": True},
        )
        assert resp.status_code == 200, resp.text
        app_data = resp.json()
        assert app_data["session_id"] == session_id
        assert app_data["state"] == "ready_for_payment"
        assert app_data["consent_timestamp"] is not None
        assert app_data["product_id"] == "hogar-estandar"
        assert app_data["profile"]["age_range"] == "26-40"
        assert app_data["recommendation"]["product_id"] == "hogar-estandar"

        # -- Step 5: Verify session state is persisted ----------------------
        resp = client.get(f"/api/v1/conversations/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "ready_for_payment"

    def test_invalid_session_returns_404(self) -> None:
        resp = client.get("/api/v1/conversations/non-existent")
        assert resp.status_code == 404

    def test_consent_without_session_returns_400(self) -> None:
        resp = client.post(
            "/api/v1/conversations/no-session/consent",
            json={"consent_given": True},
        )
        assert resp.status_code == 400

    def test_consent_without_accepting_first_returns_400(self) -> None:
        resp = client.post(
            "/api/v1/conversations",
            json={"message": {"role": "user", "content": "test"}},
        )
        sid = resp.json()["session_id"]

        # Try consent directly without profile + accept
        resp = client.post(
            f"/api/v1/conversations/{sid}/consent",
            json={"consent_given": True},
        )
        assert resp.status_code == 400

    def test_recommendation_is_deterministic(self) -> None:
        """Same profile always produces the same quote."""
        resp1 = client.post(
            "/api/v1/conversations",
            json={"message": {"role": "user", "content": "test"}},
        )
        sid1 = resp1.json()["session_id"]
        client.post(
            f"/api/v1/conversations/{sid1}/profile",
            json={"age_range": "26-40", "property_type": "house",
                  "zone": "urban", "stratum": 3},
        )

        resp2 = client.post(
            "/api/v1/conversations",
            json={"message": {"role": "user", "content": "test"}},
        )
        sid2 = resp2.json()["session_id"]
        client.post(
            f"/api/v1/conversations/{sid2}/profile",
            json={"age_range": "26-40", "property_type": "house",
                  "zone": "urban", "stratum": 3},
        )

        data1 = client.get(f"/api/v1/conversations/{sid1}").json()
        data2 = client.get(f"/api/v1/conversations/{sid2}").json()
        assert (
            data1["quote"]["monthly_premium"]
            == data2["quote"]["monthly_premium"]
        )
