import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

@pytest.fixture(scope="function")
def setup_hiveos_extension():
    # Setup logic for HiveOS extension if needed
    yield
    # Teardown logic if needed

def test_hiveos_authenticate(setup_hiveos_extension):
    response = client.post("/extensions/hiveos/authenticate", json={"api_key": "test_api_key"})
    assert response.status_code == 200, f"Unexpected status code: {response.status_code}"
    assert response.json() == {"message": "API key stored successfully"}

def test_hiveos_fetch_rigs(setup_hiveos_extension):
    response = client.get("/extensions/hiveos/rigs", headers={"Authorization": "Bearer test_api_key"})
    assert response.status_code == 200, f"Unexpected status code: {response.status_code}"
    assert "data" in response.json(), "Response should contain data"

def test_hiveos_manage_rigs(setup_hiveos_extension):
    response = client.post(
        "/extensions/hiveos/rigs/manage",
        json={"api_key": "test_api_key", "action": "start", "rig_id": 1}
    )
    assert response.status_code == 200, f"Unexpected status code: {response.status_code}"
    assert response.json() == {"message": "Action start performed on rig 1"}
