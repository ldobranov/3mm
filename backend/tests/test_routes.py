from fastapi.testclient import TestClient
from uuid import uuid4

from backend.database import SessionLocal
from backend.db.user import User
from backend.main import app
from backend.utils.auth import hash_password
from backend.utils.jwt_utils import create_access_token


def auth_headers(role: str) -> dict[str, str]:
    db = SessionLocal()
    try:
        unique = uuid4().hex
        user = User(
            username=f"{role}-{unique}",
            email=f"{role}-{unique}@example.com",
            hashed_password=hash_password("test-password"),
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        token = create_access_token(str(user.id), {"role": role})
        return {"Authorization": f"Bearer {token}"}
    finally:
        db.close()


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


def test_menu_can_be_created_and_updated():
    with TestClient(app) as client:
        headers = auth_headers("admin")
        create_response = client.post(
            "/menu/create",
            json={"name": "Test navigation", "items": [], "is_active": False},
            headers=headers,
        )

        assert create_response.status_code == 200
        created = create_response.json()
        assert created["name"] == "Test navigation"
        assert created["items"] == []

        update_response = client.put(
            "/menu/update",
            json={
                "id": created["id"],
                "name": created["name"],
                "language": "en",
                "items": [{"label": {"en": "Devices", "bg": "Устройства"}, "path": "/devices"}],
            },
            headers=headers,
        )

        assert update_response.status_code == 200
        assert update_response.json()["items"][0]["label"]["bg"] == "Устройства"


def test_menu_name_is_required():
    with TestClient(app) as client:
        headers = auth_headers("admin")
        response = client.post(
            "/menu/create",
            json={"name": "   ", "items": [], "is_active": False},
            headers=headers,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Menu name is required"


def test_menu_writes_require_admin_and_support_full_lifecycle():
    with TestClient(app) as client:
        admin_headers = auth_headers("admin")
        user_headers = auth_headers("user")
        payload = {"name": "Protected menu", "items": [], "is_active": False}

        assert client.post("/menu/create", json=payload).status_code == 401
        assert client.post("/menu/create", json=payload, headers=user_headers).status_code == 403

        first = client.post("/menu/create", json=payload, headers=admin_headers).json()
        second = client.post(
            "/menu/create",
            json={"name": "Replacement menu", "items": [], "is_active": False},
            headers=admin_headers,
        ).json()

        activate_first = client.post(f"/menu/{first['id']}/activate", headers=admin_headers)
        assert activate_first.status_code == 200
        assert activate_first.json()["is_active"] is True

        rename_second = client.patch(
            f"/menu/{second['id']}",
            json={"name": "Renamed menu"},
            headers=admin_headers,
        )
        assert rename_second.status_code == 200
        assert rename_second.json()["name"] == "Renamed menu"

        active_delete = client.delete(f"/menu/{first['id']}", headers=admin_headers)
        assert active_delete.status_code == 400
        assert "Activate another menu" in active_delete.json()["detail"]

        assert client.post(f"/menu/{second['id']}/activate", headers=admin_headers).status_code == 200
        deleted = client.delete(f"/menu/{first['id']}", headers=admin_headers)
        assert deleted.status_code == 200
        assert deleted.json() == {"deleted": True, "menu_id": first["id"]}
