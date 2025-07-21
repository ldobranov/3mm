import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.utils.db_utils import get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.db.base import Base

# Create a test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Override the get_db dependency
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# Create the test database schema
Base.metadata.create_all(bind=engine)

client = TestClient(app)

@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown():
    # Setup: Run before tests
    yield
    # Teardown: Run after tests
    Base.metadata.drop_all(bind=engine)

def test_user_routes():
    # Test create user
    response = client.post("/user/create", json={
        "username": "testuser",
        "email": "testuser@example.com",
        "password": "password123",
        "role": "user"
    })
    assert response.status_code == 200
    user_id = response.json()["id"]

    # Test read users
    response = client.get("/user/read")
    assert response.status_code == 200
    assert any(user["username"] == "testuser" for user in response.json()["users"])

    # Test update user
    response = client.put("/user/update", json={
        "id": user_id,
        "username": "updateduser",
        "email": "updateduser@example.com"
    })
    assert response.status_code == 200

    # Test delete user
    response = client.delete(f"/user/delete/{user_id}")
    assert response.status_code == 200

def test_role_routes():
    # Test create role
    response = client.post("/role/create", json={"name": "testrole"})
    assert response.status_code == 200
    role_id = response.json()["id"]

    # Test read roles
    response = client.get("/role/read")
    assert response.status_code == 200
    assert any(role["name"] == "testrole" for role in response.json()["roles"])

    # Test update role
    response = client.put("/role/update", json={"id": role_id, "name": "updatedrole"})
    assert response.status_code == 200

    # Test delete role
    response = client.delete(f"/role/delete/{role_id}")
    assert response.status_code == 200

def test_menu_routes():
    # Test create menu item
    response = client.post("/menu/create", json={
        "name": "Test Menu",
        "path": "/test-menu",
        "order": 1
    })
    assert response.status_code == 200
    menu_id = response.json()["id"]

    # Test read menu items
    response = client.get("/menu/read")
    assert response.status_code == 200
    assert any(item["name"] == "Test Menu" for item in response.json()["items"])

    # Test update menu item
    response = client.put("/menu/update", json={
        "id": menu_id,
        "name": "Updated Menu",
        "path": "/updated-menu",
        "order": 2
    })
    assert response.status_code == 200

    # Test delete menu item
    response = client.delete(f"/menu/delete/{menu_id}")
    assert response.status_code == 200

def test_settings_routes():
    # Test create setting
    response = client.post("/settings/create", json={
        "name": "Test Setting",
        "value": "Test Value"
    })
    assert response.status_code == 200
    setting_id = response.json()["id"]

    # Test read settings
    response = client.get("/settings/read")
    assert response.status_code == 200
    assert any(setting["name"] == "Test Setting" for setting in response.json()["items"])

    # Test update setting
    response = client.put("/settings/update", json={
        "id": setting_id,
        "name": "Updated Setting",
        "value": "Updated Value"
    })
    assert response.status_code == 200

    # Test delete setting
    response = client.delete(f"/settings/delete/{setting_id}")
    assert response.status_code == 200
