from datetime import datetime, timezone
import backend.database  # noqa: F401
import pytest
from backend.db.base import Base
from backend.db.device import Device
from backend.db.module import ModuleInstallation, ModulePackage
from backend.db.user import User
from backend.routes.device_capabilities import router
from backend.utils import jwt_utils
from backend.utils.auth import hash_password
from backend.utils.db_utils import get_db
from backend.utils.jwt_utils import create_access_token
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

DEVICE_ID="dev_0123456789abcdef0123456789abcdef"

@pytest.fixture(autouse=True)
def jwt_secret(monkeypatch): monkeypatch.setattr(jwt_utils,"SECRET_KEY","test-only-key-with-at-least-32-bytes")

def test_capability_api_lists_only_enabled_installations_and_queues_generic_command():
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool); Base.metadata.create_all(engine); db=Session(engine)
    admin=User(username="admin",email="admin@example.com",hashed_password=hash_password("test-password"),role="admin")
    device=Device(device_id=DEVICE_ID,display_name="test",role="node",protocol_version="1.0",approved_at=datetime.now(timezone.utc)); db.add_all([admin,device]); db.commit()
    package=ModulePackage(module_id="org.3mm.gpio",version="1.0.0",manifest={},sha256="a"*64,size_bytes=1,file_path="unused",registrations=[{"kind":"capability","registration_id":"gpio.digital.control"}]); db.add(package); db.commit()
    db.add(ModuleInstallation(device_id=device.id,module_package_id=package.id,module_id=package.module_id,installed_version="1.0.0",desired_version="1.0.0",status="succeeded",enabled=True,data_retained=True)); db.commit()
    app=FastAPI(); app.include_router(router); app.dependency_overrides[get_db]=lambda:db; client=TestClient(app); headers={"Authorization":f"Bearer {create_access_token(str(admin.id),{'role':'admin'})}"}
    assert client.get(f"/api/v1/devices/{DEVICE_ID}/capabilities",headers=headers).json()[0]["capability_id"]=="gpio.digital.control"
    queued=client.post(f"/api/v1/devices/{DEVICE_ID}/capabilities/invoke",headers=headers,json={"capability_id":"gpio.digital.control","action":"set_output","arguments":{"capability_id":"gpio.output.1","value":True}})
    assert queued.status_code==200 and queued.json()["status"]=="queued"
    denied=client.post(f"/api/v1/devices/{DEVICE_ID}/capabilities/invoke",headers=headers,json={"capability_id":"unknown","action":"set_output"})
    assert denied.status_code==409
    db.close(); engine.dispose()
