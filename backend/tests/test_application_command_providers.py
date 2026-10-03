"""The same signed application binding accepts any effective capability provider."""

import pytest
from sqlalchemy import select

from backend.db.module import ModuleInstallation
from backend.services.application_commands import authorize_execution, submit_command
from backend.services.device_capability_registry import (
    replace_provider,
    set_provider_enabled,
)
from backend.services.device_commands import deliver_next_command
from backend.tests.test_application_commands import setup, payload  # noqa: F401
from three_mm_protocol import CapabilityProviderReportV1


@pytest.mark.parametrize(
    "provider_type,role",
    [
        ("agent_module", "standalone"),
        ("native", "standalone"),
        ("embedded_firmware", "node"),
    ],
)
def test_application_binding_does_not_know_the_device_runtime(
    setup, provider_type, role
):
    s = setup
    device = s.devices[0]
    device.role = role
    if provider_type != "agent_module":
        for installation in s.db.scalars(
            select(ModuleInstallation).where(ModuleInstallation.device_id == device.id)
        ):
            installation.enabled = False
        s.db.commit()
        replace_provider(
            s.db,
            device,
            CapabilityProviderReportV1.model_validate(
                {
                    "schema_version": 1,
                    "device_id": device.device_id,
                    "provider_type": provider_type,
                    "provider_id": "example.runtime",
                    "provider_version": "0.1",
                    "expected_revision": 0,
                    "capabilities": [{"capability_id": "gpio.digital.output"}],
                }
            ),
        )
    s.db.commit()
    # Identical application manifest/config/request, irrespective of provider.
    submitted = submit_command(s.db, s.app, payload())
    assert (
        submit_command(s.db, s.app, payload())["command_id"] == submitted["command_id"]
    )
    command = deliver_next_command(s.db, device=device)
    assert command.payload["capability_id"] == "gpio.digital.output"
    assert "provider_type" not in command.payload
    assert authorize_execution(s.db, device, command.command_id)["authorized"] is True
    with pytest.raises(ValueError, match="consumed"):
        authorize_execution(s.db, device, command.command_id)
    invalid = payload("invalid")
    invalid["arguments"]["channel"] = "unapproved.channel"
    with pytest.raises(ValueError):
        submit_command(s.db, s.app, invalid)
    s.db.rollback()
    if provider_type != "agent_module":
        submit_command(s.db, s.app, payload("after-disable"))
        pending = deliver_next_command(s.db, device=device)
        set_provider_enabled(
            s.db,
            device,
            provider_type,
            "example.runtime",
            expected_revision=1,
            enabled=False,
            actor_user_id=1,
        )
        s.db.commit()
        with pytest.raises(ValueError, match="unavailable"):
            authorize_execution(s.db, device, pending.command_id)
