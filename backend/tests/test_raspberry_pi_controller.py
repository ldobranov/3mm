import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_configure_mqtt():
    response = client.post(
        "/extensions/raspberry_pi_controller/configure",
        json={
            "broker": "10.10.0.100",
            "port": 1883,
            "username": "testuser",
            "password": "testpassword"
        }
    )
    assert response.status_code == 200, f"Unexpected status code: {response.status_code}"
    assert response.json()["message"] == "MQTT configured successfully", "Message should confirm successful configuration"

def test_send_command():
    response = client.post(
        "/extensions/raspberry_pi_controller/send",
        json={
            "topic": "test/topic",
            "payload": "test payload"
        }
    )
    assert response.status_code == 200, f"Unexpected status code: {response.status_code}"
    assert response.json()["message"] == "Command sent successfully", "Message should confirm successful command"

def test_fetch_status():
    response = client.get("/extensions/raspberry_pi_controller/status")
    assert response.status_code == 200, f"Unexpected status code: {response.status_code}"
    assert "status" in response.json(), "Response should contain a status"
    assert response.json()["status"] == "OK", "Status should be OK"

def test_simple():
    assert 1 == 1, "Basic test to confirm file execution"
