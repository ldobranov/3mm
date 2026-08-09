from fastapi.testclient import TestClient

from backend.main import app


def test_system_health_and_readiness():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/ready").json() == {"status": "ready"}


def test_openapi_document_is_available():
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "FastAPI"


def test_public_settings_and_menu_reads_have_stable_envelopes():
    with TestClient(app) as client:
        settings_response = client.get("/settings/read")
        menu_response = client.get("/menu/read")

    assert settings_response.status_code == 200
    assert isinstance(settings_response.json()["items"], list)
    assert menu_response.status_code == 200
    assert isinstance(menu_response.json()["items"], list)
