"""Test smoke: la app levanta y /api/v1/health responde correctamente."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_old_unprefixed_health_route_is_gone():
    """Sin alias de compatibilidad: la ruta vieja sin /api/v1 no existe."""
    response = client.get("/health")
    assert response.status_code == 404
