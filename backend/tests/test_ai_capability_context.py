from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.database  # noqa: F401
from backend.db.base import Base
from backend.db.device import Device
from backend.db.module import ModuleInstallation, ModulePackage
from backend.services.ai_capability_context import build_automation_capability_context


def test_context_contains_only_trusted_enabled_capabilities():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    approved = Device(
        device_id="dev_approved",
        display_name="Approved Pi",
        role="standalone",
        protocol_version="1.0",
        approved_at=datetime.now(timezone.utc),
    )
    revoked = Device(
        device_id="dev_revoked",
        display_name="Revoked Pi",
        role="node",
        protocol_version="1.0",
        approved_at=datetime.now(timezone.utc),
        revoked_at=datetime.now(timezone.utc),
    )
    db.add_all([approved, revoked])
    db.commit()
    package = ModulePackage(
        module_id="org.3mm.mock-gpio",
        version="1.0.0",
        manifest={},
        sha256="a" * 64,
        size_bytes=1,
        file_path="unused",
        registrations=[
            {"kind": "capability", "registration_id": "gpio.digital.control"},
            {"kind": "navigation", "registration_id": "gpio.navigation"},
        ],
    )
    db.add(package)
    db.commit()
    db.add_all([
        ModuleInstallation(
            device_id=approved.id,
            module_package_id=package.id,
            module_id=package.module_id,
            installed_version=package.version,
            desired_version=package.version,
            status="succeeded",
            enabled=True,
        ),
        ModuleInstallation(
            device_id=revoked.id,
            module_package_id=package.id,
            module_id=package.module_id,
            installed_version=package.version,
            desired_version=package.version,
            status="succeeded",
            enabled=True,
        ),
    ])
    db.commit()

    result = build_automation_capability_context(db)

    assert [item.model_dump() for item in result.capabilities] == [{
        "device_id": "dev_approved",
        "device_name": "Approved Pi",
        "device_role": "standalone",
        "capability_id": "gpio.digital.control",
        "module_id": "org.3mm.mock-gpio",
        "module_version": "1.0.0",
        "metadata": {},
    }]
    db.close()
    engine.dispose()
