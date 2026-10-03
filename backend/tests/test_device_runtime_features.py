"""C5 ownership, support withdrawal and legacy compatibility on common Core."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from backend.db.device import Device, DeviceCommand, DeviceEvent
from backend.db.application_command import ApplicationCommandRequest
from backend.services.device_commands import node_update_is_terminal, DeviceCommandError
from backend.services.device_runtime_features import replace_runtime_features
from backend.services.application_commands import authorize_execution, submit_command
from backend.tests.test_application_commands import setup, payload  # noqa: F401
from backend.tests.test_mock_embedded_protocol import (
    core,
    approve,
    MockEmbeddedClient,
    ORIGIN,  # noqa: F401
)
from three_mm_protocol.node_features import (
    DeviceRuntimeFeaturesReportV1,
    MANDATORY_NODE_FEATURES,
)


def declaration(device_id, revision=0, *, optional=False):
    features = MANDATORY_NODE_FEATURES
    commands = ["capability.invoke"]
    if optional:
        features = features | {
            "module_lifecycle",
            "release_update_apply",
            "application_execution_permits",
        }
        commands += [
            "module.install",
            "module.disable",
            "agent.update.apply",
            "application.capability.invoke",
        ]
    return DeviceRuntimeFeaturesReportV1(
        device_id=device_id,
        runtime_name="reference",
        runtime_version="1",
        features=tuple(sorted(features)),
        command_types=tuple(sorted(commands)),
        expected_revision=revision,
    ).model_dump(mode="json")


def queue(client, admin, node, kind, key):
    return client.post(
        node.prefix + "/commands",
        headers=admin,
        json={"command_type": kind, "payload": {}, "idempotency_key": key},
    )


@pytest.mark.parametrize("role", ["standalone", "hub", "node"])
def test_legacy_unknown_and_revisioned_advertisement_do_not_grant_capabilities(
    core, tmp_path, role
):
    client, db, admin, viewer, transport = core
    node = MockEmbeddedClient(ORIGIN, tmp_path, transport=transport)
    try:
        approve(core, node)
        device = db.scalar(select(Device).where(Device.device_id == node.device_id))
        device.role = role
        db.commit()
        path = node.prefix + "/runtime-features"
        assert client.get(path, headers=admin).json()["source"] == "legacy_unadvertised"
        assert queue(client, admin, node, "module.install", "legacy").status_code == 200
        report = declaration(node.device_id)
        assert client.put(path, headers=admin, json=report).status_code == 401
        assert client.get(path, headers=viewer).status_code == 403
        assert client.get(path).status_code == 401
        assert (
            node._request(
                "PUT", path, report | {"device_id": "dev_" + "f" * 32}
            ).status_code
            == 403
        )
        response = node._request("PUT", path, report)
        assert response.status_code == 200 and response.json()["revision"] == 1
        assert node._request("PUT", path, report).json()["revision"] == 1
        assert (
            node._request("PUT", path, declaration(node.device_id, 1)).json()[
                "revision"
            ]
            == 1
        )
        assert (
            node._request(
                "PUT", path, declaration(node.device_id, optional=True)
            ).status_code
            == 409
        )
        assert (
            db.query(DeviceEvent)
            .filter_by(event_type="runtime.features.updated")
            .count()
            == 1
        )
        assert (
            client.get(
                node.prefix + "/capabilities?registry_version=2", headers=admin
            ).json()
            == []
        )
        assert queue(client, admin, node, "module.install", "new").status_code == 409
        # Original idempotent request remains queryable; it is not new authorization.
        assert queue(client, admin, node, "module.install", "legacy").status_code == 200
        assert (
            node._request("GET", node.prefix + "/protocol").json()[
                "runtime_features_revision"
            ]
            == 1
        )
        assert node.poll() is None
        command = db.query(DeviceCommand).one()
        assert command.status == "failed" and command.delivery_attempts == 0
        assert command.result == {"execution_state": "not_dispatched"}
        node.close()
        node = MockEmbeddedClient(ORIGIN, tmp_path, transport=transport)
        node.negotiate()
        assert (
            client.get(path, headers=admin).json()["revision"] == 2
        )  # runtime changed, no identity change
    finally:
        node.close()


def test_withdrawal_cancels_only_never_dispatched_work_and_preserves_ota_uncertainty(
    core, tmp_path
):
    client, db, admin, _, transport = core
    node = MockEmbeddedClient(ORIGIN, tmp_path, transport=transport)
    try:
        approve(core, node)
        node._body(
            node._request(
                "PUT",
                node.prefix + "/runtime-features",
                declaration(node.device_id, optional=True),
            )
        )
        dispatched = queue(
            client, admin, node, "agent.update.apply", "delivered"
        ).json()
        assert node._request("GET", node.prefix + "/commands/next").status_code == 200
        pending = queue(client, admin, node, "agent.update.apply", "pending").json()
        node._body(
            node._request(
                "PUT", node.prefix + "/runtime-features", declaration(node.device_id, 1)
            )
        )
        assert node._request("GET", node.prefix + "/commands/next").status_code == 204
        delivered = db.scalar(
            select(DeviceCommand).where(
                DeviceCommand.command_id == dispatched["command_id"]
            )
        )
        cancelled = db.scalar(
            select(DeviceCommand).where(
                DeviceCommand.command_id == pending["command_id"]
            )
        )
        db.refresh(delivered)
        db.refresh(cancelled)
        assert delivered.status == "delivered" and not node_update_is_terminal(
            delivered
        )
        assert cancelled.status == "failed" and node_update_is_terminal(cancelled)
        assert (
            queue(client, admin, node, "capability.invoke", "still-paused").status_code
            == 409
        )
        delivered.delivered_at = datetime.now(UTC) - timedelta(seconds=31)
        db.commit()
        assert (
            node._request("GET", node.prefix + "/commands/next").json()["command_id"]
            == dispatched["command_id"]
        )
        # Failure after actual delivery must never be mistaken for Core cancellation.
        delivered.status = "failed"
        delivered.result = {"execution_state": "not_dispatched"}
        db.commit()
        assert not node_update_is_terminal(delivered)
    finally:
        node.close()


def test_signed_application_permit_support_cannot_be_inferred_from_gpio_capability(
    setup,
):
    s = setup
    device = s.devices[0]

    def report(revision, optional=False):
        replace_runtime_features(
            s.db,
            device,
            DeviceRuntimeFeaturesReportV1.model_validate(
                declaration(device.device_id, revision, optional=optional)
            ),
        )
        s.db.commit()

    report(0)
    with pytest.raises(DeviceCommandError, match="advertise"):
        submit_command(s.db, s.app, payload())
    s.db.rollback()
    report(1, True)
    submitted = submit_command(s.db, s.app, payload())
    from backend.services.device_commands import deliver_next_command

    command = deliver_next_command(s.db, device=device)
    assert command.command_id == submitted["command_id"]
    report(2)
    with pytest.raises(ValueError, match="execution permits"):
        authorize_execution(s.db, device, command.command_id)
    s.db.rollback()
    assert s.db.get(ApplicationCommandRequest, command.command_id).claimed is False
    report(3, True)
    assert authorize_execution(s.db, device, command.command_id)["authorized"] is True
