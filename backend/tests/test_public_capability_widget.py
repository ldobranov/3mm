import base64
from datetime import UTC, datetime

import backend.database  # noqa: F401
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.database import get_db
from backend.db.base import Base
from backend.db.device import Device, DeviceCapabilityState
from backend.db.display import Display
from backend.db.module import ModuleInstallation, ModulePackage
from backend.db.user import User
from backend.db.widget import Widget
from backend.routes.display_routes import router
from backend.schemas.ai_extension_builder import ExtensionSpec
from backend.services.module_packages import validate_module_package
from backend.utils.ai_extension_builder import generator
from backend.utils.auth import hash_password
from three_mm_protocol import (
    BuilderSettingV1,
    CapabilityBindingV1,
    CapabilityPlanV1,
    CapabilityPresentationV1,
    PresentationStateV1,
)


DEVICE_ID = "dev_0123456789abcdef0123456789abcdef"


def _compiled_gpio_package(tmp_path):
    plan = CapabilityPlanV1(
        target="dashboard_widget",
        settings=(
            BuilderSettingV1(key="deviceId", label="Device", kind="device", required=True),
            BuilderSettingV1(key="channel", label="Input pin", kind="capability_channel", required=True),
        ),
        bindings=(CapabilityBindingV1(
            alias="inputState",
            capability_id="gpio.digital.input",
            operation="subscribe",
            device_setting="deviceId",
            channel_setting="channel",
            permissions=("hardware.gpio",),
        ),),
        presentations=(CapabilityPresentationV1(
            kind="indicator",
            source_binding="inputState",
            states=(
                PresentationStateV1(value=True, label="Active", color="#22C55E"),
                PresentationStateV1(value=False, label="Inactive", color="#EF4444"),
                PresentationStateV1(state="stale", label="Stale", color="#F59E0B"),
                PresentationStateV1(state="offline", label="Offline", color="#6B7280"),
                PresentationStateV1(state="error", label="Error", color="#DC2626"),
            ),
        ),),
    )
    spec = ExtensionSpec(
        name="PublicInputLamp",
        version="1.0.0",
        type="widget",
        description="Public scoped GPIO lamp",
        api_prefix="/api/public-input-lamp",
        backend_entry="public_input_lamp.py",
        frontend_entry="PublicInputLamp.vue",
        capability_plan=plan,
    )
    _, encoded, _ = generator.build_extension_zip(spec, use_ai=False)
    blob = base64.b64decode(encoded)
    validated = validate_module_package(blob)
    package_path = tmp_path / "public-input-lamp.zip"
    package_path.write_bytes(blob)
    return validated, package_path


def test_public_widget_reads_only_its_declared_device_channel(tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    user = User(
        username="public-owner",
        email="public-owner@example.com",
        hashed_password=hash_password("test"),
        role="admin",
    )
    device = Device(
        device_id=DEVICE_ID,
        display_name="Pi",
        role="standalone",
        protocol_version="1.0",
        approved_at=datetime.now(UTC),
    )
    db.add_all([user, device])
    db.commit()
    gpio_package = ModulePackage(
        module_id="org.3mm.mock-gpio",
        version="1.0.4",
        manifest={},
        sha256="a" * 64,
        size_bytes=1,
        file_path="unused",
        registrations=[{"kind": "capability", "registration_id": "gpio.digital.input"}],
    )
    validated, package_path = _compiled_gpio_package(tmp_path)
    compiled_package = ModulePackage(
        module_id=validated.manifest.module_id,
        version=validated.manifest.version,
        manifest=validated.manifest.model_dump(mode="json"),
        sha256=validated.sha256,
        size_bytes=validated.size_bytes,
        file_path=str(package_path),
        registrations=[],
    )
    db.add_all([gpio_package, compiled_package])
    db.commit()
    db.add(ModuleInstallation(
        device_id=device.id,
        module_package_id=gpio_package.id,
        module_id=gpio_package.module_id,
        installed_version=gpio_package.version,
        desired_version=gpio_package.version,
        status="succeeded",
        enabled=True,
    ))
    display = Display(user_id=user.id, title="Public GPIO", slug="public-gpio", is_public=True)
    db.add(display)
    db.commit()
    widget = Widget(
        display_id=display.id,
        type=f"compiled:{compiled_package.module_id}:{compiled_package.version}:widget",
        config={"deviceId": DEVICE_ID, "channel": "gpio.input.1"},
    )
    db.add(widget)
    db.add(DeviceCapabilityState(
        device_id=device.id,
        capability_id="gpio.digital.input",
        values={"gpio.input.1": True, "gpio.input.2": False},
        observed_at=datetime.now(UTC),
        received_at=datetime.now(UTC),
    ))
    db.commit()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    public_display = client.get("/api/public/@public-owner/public-gpio")
    assert public_display.status_code == 200
    state_url = public_display.json()["widgets"][0]["config"]["_publicCapabilityStateUrl"]
    state = client.get(state_url)
    assert state.status_code == 200
    assert state.json()["capability_id"] == "gpio.digital.input"
    assert state.json()["values"] == {"gpio.input.1": True}

    display.is_public = False
    db.commit()
    assert client.get(state_url).status_code == 404
    db.close()
    engine.dispose()
