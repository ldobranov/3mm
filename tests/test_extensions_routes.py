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
    with open("test_extension.zip", "wb") as f:
        f.write(b"Fake zip content")

    with open("test_extension.zip", "rb") as file:
        response = client.post("/extensions/upload", files={"file": file})

    assert response.status_code == 200, f"Unexpected status code: {response.status_code}"
    assert "message" in response.json(), "Response should contain a message"

    # Clean up test file
    import os
    os.remove("test_extension.zip")

def test_extensions_generate():
    response = client.post("/extensions/generate", json={"description": "Test extension"})
    assert response.status_code == 200, f"Unexpected status code: {response.status_code}"
    assert "name" in response.json(), "Response should contain a name"
    assert response.json()["name"] == "AI Generated Extension", "Name should match"

# Moved the test file to the backend folder as per the updated instructions
# Ensure all backend-related tests are located within the backend folder
