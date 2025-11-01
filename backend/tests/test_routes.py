import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

import pytest
from fastapi.testclient import TestClient
from backend.main import app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.db.base import Base
from sqlalchemy.sql import text

client = TestClient(app)

# Setup a test database
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown():
    # Drop all tables to avoid duplicate index errors
    Base.metadata.drop_all(bind=engine)
    # Create tables before tests
    Base.metadata.create_all(bind=engine)

    # Reset auto-increment counters for tables
    with engine.connect() as connection:
        connection.execute(text("DELETE FROM users;"))
        connection.execute(text("DELETE FROM roles;"))
        connection.execute(text("DELETE FROM settings;"))
        connection.execute(text("DELETE FROM menus;"))

    yield

    # Teardown: Drop tables after tests
    Base.metadata.drop_all(bind=engine)

def test_menu_read():
    response = client.get("/menu/read")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    for item in data["items"]:
        assert "id" in item
        assert "name" in item
        assert "items" in item  # Settings.vue expects items array
        assert "is_active" in item  # Settings.vue expects is_active property

def test_user_routes():
    # Test create user
    response = client.post("/user/create", json={
        "id": 102,  # Ensuring unique id
        "username": "unique_testuser",
        "email": "unique_testuser@example.com",
        "password": "password123",
        "role": "user"
    })
    assert response.status_code == 200
    user_id = response.json()["id"]

    # Test read users
    response = client.get("/user/read")
    assert response.status_code == 200
    assert any(user["username"] == "unique_testuser" for user in response.json()["items"])

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
    response = client.post("/role/create", json={
        "name": "unique_role_name_102",  # Ensuring unique role name
        "permissions": ["read", "write"]
    })
    assert response.status_code == 200
    role_id = response.json()["id"]

    # Test read roles
    response = client.get("/role/read")
    assert response.status_code == 200
    assert any(role["name"] == "unique_role_name_102" for role in response.json()["roles"])

    # Test update role
    response = client.put("/role/update", json={
        "id": role_id,
        "name": "updated_role_name",
        "permissions": ["read"]
    })
    assert response.status_code == 200

    # Test delete role
    response = client.delete(f"/role/delete/{role_id}")
    assert response.status_code == 200

def test_menu_routes():
    # Test create menu item with proper structure for Settings.vue
    response = client.post("/menu/create", json={
        "name": "Test Menu",
        "path": "/test-menu",
        "order": 1,
        "items": [
            {"label": "Home", "path": "/"},
            {"label": "About", "path": "/about"}
        ],
        "is_active": True
    })
    assert response.status_code == 200
    menu_id = response.json()["id"]

    # Test read menu items
    response = client.get("/menu/read")
    assert response.status_code == 200
    items = response.json()["items"]
    assert any(item["name"] == "Test Menu" for item in items)
    
    # Verify menu structure matches what Settings.vue expects
    test_menu = next(item for item in items if item["name"] == "Test Menu")
    assert "items" in test_menu
    assert "is_active" in test_menu
    assert isinstance(test_menu["items"], list)

    # Test update menu item with items array
    response = client.put("/menu/update", json={
        "id": menu_id,
        "name": "Updated Menu",
        "path": "/updated-menu",
        "order": 2,
        "items": [
            {"label": "Home", "path": "/"},
            {"label": "About", "path": "/about"},
            {"label": "Contact", "path": "/contact"}
        ],
        "is_active": True
    })
    assert response.status_code == 200

    # Verify update worked
    response = client.get("/menu/read")
    assert response.status_code == 200
    updated_items = response.json()["items"]
    updated_menu = next(item for item in updated_items if item["name"] == "Updated Menu")
    assert len(updated_menu["items"]) == 3  # Should have 3 items now

    # Test delete menu item
    response = client.delete(f"/menu/delete/{menu_id}")
    assert response.status_code == 200

def test_settings_routes():
    # Test create setting
    response = client.post("/settings/create", json={
        "key": "unique_test_setting",
        "value": "Unique Test Value",
        "description": "A unique test setting"
    })
    assert response.status_code == 200
    setting_id = response.json()["id"]

    # Test read settings
    response = client.get("/settings/read")
    assert response.status_code == 200
    assert any(setting["key"] == "unique_test_setting" for setting in response.json()["items"])

    # Test update setting
    response = client.put("/settings/update", json={
        "id": setting_id,
        "key": "updated_setting",
        "value": "Updated Value",
        "description": "Updated description"
    })
    assert response.status_code == 200

    # Test delete setting
    response = client.delete(f"/settings/delete/{setting_id}")
    assert response.status_code == 200

def test_settings_vue_component_settings():
    """Test settings specifically used by the Settings.vue component"""
    # Create header-related settings that Settings.vue manages
    header_settings = [
        {"key": "site_name", "value": "Test Site", "description": "The name of the site"},
        {"key": "header_message", "value": "Welcome to our site", "description": "Header message"},
        {"key": "logo_url", "value": "https://example.com/logo.png", "description": "Logo URL"},
        {"key": "header_bg_color", "value": "#ffffff", "description": "Header background color"},
        {"key": "header_text_color", "value": "#000000", "description": "Header text color"}
    ]
    
    created_settings = []
    for setting_data in header_settings:
        response = client.post("/settings/create", json=setting_data)
        assert response.status_code == 200
        created_settings.append(response.json())

    # Test reading settings - Settings.vue expects this structure
    response = client.get("/settings/read")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    
    # Verify header settings are present
    settings_items = data["items"]
    header_keys = ["site_name", "header_message", "logo_url", "header_bg_color", "header_text_color"]
    for key in header_keys:
        assert any(setting["key"] == key for setting in settings_items), f"Missing setting: {key}"

    # Test updating settings as Settings.vue would
    site_setting = next(s for s in settings_items if s["key"] == "site_name")
    response = client.put("/settings/update", json={
        "id": site_setting["id"],
        "key": "site_name",
        "value": "Updated Site Name",
        "description": "Updated site name"
    })
    assert response.status_code == 200

    # Verify the update
    response = client.get("/settings/read")
    updated_settings = response.json()["items"]
    updated_site_setting = next(s for s in updated_settings if s["key"] == "site_name")
    assert updated_site_setting["value"] == "Updated Site Name"

    # Test light theme settings
    light_theme_settings = [
        {"key": "light_body_bg", "value": "#ffffff", "description": "Light theme body background"},
        {"key": "light_content_bg", "value": "#ffffff", "description": "Light theme content background"},
        {"key": "light_button_primary_bg", "value": "#007bff", "description": "Light theme primary button background"},
        {"key": "light_button_secondary_bg", "value": "#6c757d", "description": "Light theme secondary button background"},
        {"key": "light_button_danger_bg", "value": "#dc3545", "description": "Light theme danger button background"},
        {"key": "light_card_bg", "value": "#ffffff", "description": "Light theme card background"},
        {"key": "light_card_border", "value": "#e3e3e3", "description": "Light theme card border"},
        {"key": "light_panel_bg", "value": "#ffffff", "description": "Light theme panel background"},
        {"key": "light_text_primary", "value": "#222222", "description": "Light theme primary text"},
        {"key": "light_text_secondary", "value": "#666666", "description": "Light theme secondary text"},
        {"key": "light_text_muted", "value": "#999999", "description": "Light theme muted text"},
        {"key": "light_border_radius_sm", "value": "4", "description": "Light theme small border radius"},
        {"key": "light_border_radius_md", "value": "8", "description": "Light theme medium border radius"},
        {"key": "light_border_radius_lg", "value": "12", "description": "Light theme large border radius"}
    ]
    
    for setting_data in light_theme_settings:
        response = client.post("/settings/create", json=setting_data)
        assert response.status_code == 200

    # Test dark theme settings
    dark_theme_settings = [
        {"key": "dark_body_bg", "value": "#1f2937", "description": "Dark theme body background"},
        {"key": "dark_content_bg", "value": "#1f2937", "description": "Dark theme content background"},
        {"key": "dark_button_primary_bg", "value": "#3b82f6", "description": "Dark theme primary button background"},
        {"key": "dark_button_secondary_bg", "value": "#6b7280", "description": "Dark theme secondary button background"},
        {"key": "dark_button_danger_bg", "value": "#ef4444", "description": "Dark theme danger button background"},
        {"key": "dark_card_bg", "value": "#374151", "description": "Dark theme card background"},
        {"key": "dark_card_border", "value": "#4b5563", "description": "Dark theme card border"},
        {"key": "dark_panel_bg", "value": "#374151", "description": "Dark theme panel background"},
        {"key": "dark_text_primary", "value": "#e5e7eb", "description": "Dark theme primary text"},
        {"key": "dark_text_secondary", "value": "#9ca3af", "description": "Dark theme secondary text"},
        {"key": "dark_text_muted", "value": "#6b7280", "description": "Dark theme muted text"},
        {"key": "dark_border_radius_sm", "value": "4", "description": "Dark theme small border radius"},
        {"key": "dark_border_radius_md", "value": "8", "description": "Dark theme medium border radius"},
        {"key": "dark_border_radius_lg", "value": "12", "description": "Dark theme large border radius"}
    ]
    
    for setting_data in dark_theme_settings:
        response = client.post("/settings/create", json=setting_data)
        assert response.status_code == 200

    # Verify all Settings.vue settings are present
    response = client.get("/settings/read")
    final_settings = response.json()["items"]
    all_expected_keys = (
        header_keys + 
        [s["key"] for s in light_theme_settings] + 
        [s["key"] for s in dark_theme_settings]
    )
    
    for key in all_expected_keys:
        assert any(setting["key"] == key for setting in final_settings), f"Missing expected setting: {key}"

def test_menu_with_items_structure():
    """Test that menu items have the proper structure expected by Settings.vue"""
    # Create a menu with items as expected by Settings.vue component
    menu_data = {
        "name": "Main Navigation",
        "path": "/main",
        "order": 1,
        "items": [
            {"label": "Dashboard", "path": "/dashboard", "icon": "bi-speedometer2"},
            {"label": "Pages", "path": "/pages", "icon": "bi-file-text"},
            {"label": "Users", "path": "/users", "icon": "bi-people"},
            {"label": "Settings", "path": "/settings", "icon": "bi-gear"}
        ],
        "is_active": True
    }
    
    response = client.post("/menu/create", json=menu_data)
    assert response.status_code == 200
    menu_id = response.json()["id"]

    # Test that the menu structure is preserved
    response = client.get("/menu/read")
    assert response.status_code == 200
    menus = response.json()["items"]
    
    main_menu = next((m for m in menus if m["name"] == "Main Navigation"), None)
    assert main_menu is not None
    assert "items" in main_menu
    assert "is_active" in main_menu
    assert main_menu["is_active"] == True
    assert len(main_menu["items"]) == 4
    
    # Verify each item has the expected structure
    for item in main_menu["items"]:
        assert "label" in item
        assert "path" in item
        # icon is optional but should be present if provided
        if "icon" in item:
            assert isinstance(item["icon"], str)

    # Test updating menu items (as Settings.vue would when reordering)
    updated_items = [
        {"label": "Dashboard", "path": "/dashboard", "icon": "bi-speedometer2"},
        {"label": "Settings", "path": "/settings", "icon": "bi-gear"},  # Moved to second position
        {"label": "Pages", "path": "/pages", "icon": "bi-file-text"},
        {"label": "Users", "path": "/users", "icon": "bi-people"}
    ]
    
    response = client.put("/menu/update", json={
        "id": menu_id,
        "name": "Main Navigation",
        "path": "/main",
        "order": 1,
        "items": updated_items,
        "is_active": True
    })
    assert response.status_code == 200

    # Verify the reordering worked
    response = client.get("/menu/read")
    updated_menus = response.json()["items"]
    updated_main_menu = next(m for m in updated_menus if m["name"] == "Main Navigation")
    assert updated_main_menu["items"][1]["label"] == "Settings"  # Should be in second position

    # Clean up
    response = client.delete(f"/menu/delete/{menu_id}")
    assert response.status_code == 200

def test_settings_read_empty_database():
    """Test reading settings when database is empty"""
    # Clear any existing settings
    with engine.connect() as connection:
        connection.execute(text("DELETE FROM settings;"))
    
    response = client.get("/settings/read")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) == 0

def test_menu_read_empty_database():
    """Test reading menu when database is empty"""
    # Clear any existing menus
    with engine.connect() as connection:
        connection.execute(text("DELETE FROM menus;"))
    
    response = client.get("/menu/read")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) == 0