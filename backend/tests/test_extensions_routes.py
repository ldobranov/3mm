import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

# Ensure the backend module is discoverable without setting PYTHONPATH

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

# Renamed test functions to follow pytest naming conventions

def test_extensions_read():
    response = client.get("/extensions/read")
    assert response.status_code == 200, f"Unexpected status code: {response.status_code}"
    assert isinstance(response.json(), list), "Response should be a list"

def test_extensions_upload():
    # Update the test to use a valid .zip file for the /upload route
    import zipfile

    # Create a valid .zip file
    with zipfile.ZipFile("test_extension.zip", "w") as zipf:
        zipf.writestr("test.txt", "This is a test file.")

    with open("test_extension.zip", "rb") as file:
        response = client.post("/upload", files={"file": file})

    # Add debug logging to capture response details
    print(f"Response for /extensions/upload: {response.status_code}, {response.json()}")

    assert response.status_code == 200, f"Unexpected status code: {response.status_code}"
    assert "message" in response.json(), "Response should contain a message"

    # Clean up test file
    import os
    os.remove("test_extension.zip")

def test_extensions_generate():
    response = client.post("/extensions/generate", json={"description": "Test extension"})
    # Add debug logging to capture response details for /generate
    print(f"Response for /extensions/generate: {response.status_code}, {response.json()}")

    assert response.status_code == 200, f"Unexpected status code: {response.status_code}"
    assert "name" in response.json(), "Response should contain a name"
    assert response.json()["name"] == "AI Generated Extension", "Name should match"

def test_configure_mqtt():
    response = client.post(
        "/extensions/mqtt/configure",
        json={
            "broker": "test.mqtt.broker",
            "port": 1883,
            "username": "testuser",
            "password": "testpassword"
        }
    )
    assert response.status_code == 200, f"Unexpected status code: {response.status_code}"
    assert response.json()["message"] == "MQTT configured successfully", "Message should confirm successful configuration"

def test_send_command():
    response = client.post(
        "/extensions/mqtt/send",
        json={
            "topic": "test/topic",
            "payload": "test payload"
        }
    )
    assert response.status_code == 200, f"Unexpected status code: {response.status_code}"
    assert response.json()["message"] == "Command sent successfully", "Message should confirm successful command"

def test_fetch_status():
    response = client.get("/extensions/mqtt/status")
    assert response.status_code == 200, f"Unexpected status code: {response.status_code}"
    assert "status" in response.json(), "Response should contain a status"
    assert response.json()["status"] == "OK", "Status should be OK"

# Moved the test file to the backend folder as per the updated instructions
# Ensure all backend-related tests are located within the backend folder
