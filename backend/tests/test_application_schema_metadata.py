"""Real consent/seals with native GPIO int64 schema metadata, no hardware I/O."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import io
import os
import zipfile

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from backend.db.application_authority_grant import (
    ApplicationAuthorityAction as Action, ApplicationAuthorityGrant as Grant,
    ApplicationAuthorityPlan as Plan, ApplicationNativeReview as Native,
)
from backend.db.device import Device, DeviceCapabilityHealth, DeviceCapabilityProvider
from backend.db.module import (
    ApplicationConnectorBinding, ApplicationExtensionInstallation as Installation,
    ModuleInstallation, ModulePackage,
)
from backend.applications.authority import management as authority
from backend.applications.management import consent
from backend.applications.authority.keys import AuthorityReviewKeyError
from backend.applications.authority.metadata import read_authority_guard
from backend.devices.capabilities.registry import capability_catalog
from backend.artifacts.packages import validate_module_package
from backend.tests.test_application_authority_management import identity, installed, source_subject, source_installed
from backend.tests.test_application_checkpoint_authority import store_checkpoint_package
from backend.tests.test_application_consent import allow, preview, read, state
from backend.tests.test_application_authority_sources import DEVICE
from packages.protocol.character_display import CharacterDisplayProfileV1
from packages.protocol.gpio_input import GpioInputProfileV1, INPUT_EVENT, MAX_MONOTONIC_NS
from packages.protocol import character_display_package, gpio_input_package


pytestmark = pytest.mark.skipif(os.name != "posix", reason="Real protected Core seals and SQLite authority locks")
DISPLAY = "command:display_frame"
INPUT = "event:input_edges"
CONNECTOR = "connector:business_api"


def _object(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _store_provider(db, s, identifier, profile, builder):
    blob = builder.build_package(profile)
    package = validate_module_package(blob)
    manifest = package.manifest.model_dump(mode="json")
    archive = s.root / "modules" / (package.sha256 + ".zip")
    archive.write_bytes(blob)
    db.add(ModulePackage(id=identifier, module_id=manifest["module_id"], version=manifest["version"],
        sha256=package.sha256, size_bytes=len(blob), manifest=manifest,
        registrations=manifest["registrations"], file_path=str(archive)))
    db.flush()
    db.add(ModuleInstallation(device_id=1, module_package_id=identifier, module_id=manifest["module_id"],
        installed_version=manifest["version"], desired_version=manifest["version"], status="succeeded", enabled=True))
    return manifest["module_id"]


def configure(s, *, input_consumer, agent_modules=False):
    """Publish real profile contracts through the ordinary effective registry."""
    s.display = CharacterDisplayProfileV1(driver="pcf8574", columns=16, rows=2)
    s.input = GpioInputProfileV1(driver="gpiod")
    lcd, gpio = s.display.contract(), s.input.contract()
    definition = s.validated.application_extension.model_dump(mode="json")
    definition["service"]["sdk_version"] = "1.3"
    definition["command_bindings"] = [{
        "binding_id": "display_frame", "target_device_config_key": "TARGET_DEVICE_ID",
        "capability_id": lcd.capability_id, "contract_version": lcd.contract_version,
        "action": "write_frame", "max_ttl_seconds": 10,
        "arguments_schema": lcd.actions["write_frame"].arguments_schema,
    }]
    manifest = s.validated.manifest.model_dump(mode="json")
    manifest["capabilities"]["consumes"] = [lcd.capability_id]
    if input_consumer:
        # This is the Monitor shape: an internal idempotent event handler whose
        # nested payload carries a protocol-defined signed-int64 timestamp.
        definition["operations"].append({
            "operation_id": "input_changed", "kind": "command", "audiences": ["internal"],
            "idempotency": "required", "input_schema": _object({
                "event_id": {"type": "string", "maxLength": 64},
                "device_id": {"type": "string", "maxLength": 64},
                "event_type": {"type": "string", "enum": [INPUT_EVENT]},
                "occurred_at": {"type": "string", "maxLength": 40},
                "payload": deepcopy(gpio.events[INPUT_EVENT]),
            }),
        })
        definition["event_subscriptions"] = [{
            "subscription_id": "input_edges", "event_type": INPUT_EVENT,
            "capability_id": gpio.capability_id, "handler_operation_id": "input_changed",
            "device_scope_config_key": "TARGET_DEVICE_ID", "max_backlog": 8,
        }]
        definition["optional_resources"] = [DISPLAY, INPUT]
        manifest["permissions"].append("events.consume")
        manifest["capabilities"]["consumes"].append(gpio.capability_id)
    store_checkpoint_package(s, definition, manifest)
    # A distinct real package/installation witnesses cross-application isolation.
    other_definition = deepcopy(definition)
    other_definition.update(module_id="org.example.unrelated", command_bindings=[],
        connectors=[], event_subscriptions=[], optional_resources=[], operations=definition["operations"][:1])
    other_manifest = deepcopy(manifest)
    other_manifest.update(module_id="org.example.unrelated", permissions=["data.read", "data.write", "process.spawn"],
        capabilities={"provides": [], "consumes": []})
    blob = io.BytesIO()
    with zipfile.ZipFile(s.archive) as source, zipfile.ZipFile(blob, "w") as target:
        target.writestr("manifest.json", json.dumps(other_manifest))
        target.writestr("application-extension.json", json.dumps(other_definition))
        artifact = other_definition["service"]["artifact"]
        target.writestr(artifact, source.read(artifact))
    other_package = validate_module_package(blob.getvalue())
    other_archive = s.root / "modules" / (other_package.sha256 + ".zip")
    other_archive.write_bytes(blob.getvalue())
    now = datetime.now(UTC)
    with Session(s.engine) as db, db.begin():
        db.add(ModulePackage(id=2, module_id="org.example.unrelated", version="1.0.0",
            sha256=other_package.sha256, size_bytes=len(blob.getvalue()),
            manifest=other_manifest, file_path=str(other_archive)))
        db.flush()
        db.add(Installation(id=2, module_id="org.example.unrelated", module_package_id=2,
            instance_id="b" * 24, configuration=deepcopy(s.configuration), socket_path="unused.sock",
            active_version="1.0.0", enabled=True, status="active"))
        if agent_modules:
            db.execute(delete(DeviceCapabilityProvider))
            _store_provider(db, s, 3, s.display, character_display_package)
            s.input_module_id = _store_provider(db, s, 4, s.input, gpio_input_package)
        else:
            db.execute(update(DeviceCapabilityProvider).where(DeviceCapabilityProvider.id == 1).values(
                provider_id="org.example.lcd", configured_capability_ids=[lcd.capability_id], capabilities=[{
                    "capability_id": lcd.capability_id, "metadata": {}, "contract": lcd.model_dump(mode="json"),
                }]))
            db.add(DeviceCapabilityProvider(device_id=1, provider_type="native", provider_id="org.example.input",
                provider_version="1.0.0", revision=1, enabled=True, reported_at=now,
                configured_capability_ids=[gpio.capability_id], capabilities=[{
                    "capability_id": gpio.capability_id, "metadata": {}, "contract": gpio.model_dump(mode="json"),
                }]))
        db.execute(delete(DeviceCapabilityHealth))
        db.flush()
        for declaration in capability_catalog(db, db.get(Device, 1)):
            db.add(DeviceCapabilityHealth(device_id=1, provider_type=declaration.provider_type,
                provider_id=declaration.provider_id, observed_at=now, report={
                    "declaration_digest": declaration.declaration_digest,
                    "capabilities": [{"capability_id": declaration.capability_id, "healthy": True}]},
                expires_at=now + timedelta(minutes=5)))
    return s


def require(s, scope):
    prepared = s.manager._prepare(1)
    with s.manager.keys.read_locked() as key, Session(s.engine) as db:
        return s.manager._require_grant(db, key, 1, prepared, scope)


def _sources(s):
    with Session(s.engine) as db:
        return {
            "providers": [(row.id, row.provider_id, row.revision, deepcopy(row.capabilities))
                for row in db.scalars(select(DeviceCapabilityProvider).order_by(DeviceCapabilityProvider.id))],
            "connector": [(row.id, row.application_installation_id, row.enabled,
                row.destination_origin, row.authority_revision)
                for row in db.scalars(select(ApplicationConnectorBinding))],
            "modules": [(row.device_id, row.module_package_id, row.module_id,
                row.installed_version, row.status, row.enabled)
                for row in db.scalars(select(ModuleInstallation).order_by(ModuleInstallation.id))],
            "other_application": [(row.id, row.module_id, row.module_package_id,
                row.instance_id, row.active_version, row.enabled, row.status,
                row.authority_mode, row.authority_incarnation, row.authority_epoch, deepcopy(row.configuration))
                for row in db.scalars(select(Installation).where(Installation.id == 2))],
            "other_grants": list(db.scalars(select(Grant.installation_id).where(Grant.installation_id == 2))),
            "other_reviews": list(db.scalars(select(Native.review_id).where(Native.installation_id == 2))),
        }


def test_unrelated_native_gpio_int64_contract_does_not_poison_lcd_consent(state):
    s = configure(state, input_consumer=False)
    before = _sources(s)
    reviewed = preview(s)
    assert reviewed["scopes"] == reviewed["selected_scopes"] == [DISPLAY, CONNECTOR]
    assert reviewed["resources"].get("events", []) == []
    assert reviewed["resources"]["commands"][0]["target_device_id"] == DEVICE
    assert allow(s, reviewed)["effective"]
    assert require(s, DISPLAY) and require(s, CONNECTOR)
    with pytest.raises(authority.AuthorityManagementError):
        require(s, INPUT)
    assert _sources(s) == before  # Consent never rewrites a provider or connector.


def test_int64_event_schema_survives_fresh_consent_native_gate_and_sealed_receipts(state):
    s = configure(state, input_consumer=True, agent_modules=True)
    before = _sources(s)
    reviewed = preview(s)
    assert reviewed["scopes"] == sorted([DISPLAY, INPUT, CONNECTOR])
    assert reviewed["selected_scopes"] == [CONNECTOR]  # Optional is not implicit.
    handler = reviewed["resources"]["events"][0]["handler"]
    assert handler["input_schema"]["properties"]["payload"]["properties"]["monotonic_ns"]["maximum"] == MAX_MONOTONIC_NS
    with Session(s.engine) as db:
        assert db.scalar(select(DeviceCapabilityProvider.id)) is None
        assert db.scalar(select(ModuleInstallation.id).where(ModuleInstallation.module_id == s.input_module_id))
        assert db.get(Grant, 1) is None and db.scalar(select(Native.review_id)) is None
    with pytest.raises(authority.AuthorityManagementError):
        require(s, DISPLAY)
    request_id = identity()
    scopes = sorted([DISPLAY, INPUT, CONNECTOR])
    result = allow(s, reviewed, scopes=scopes, request_id=request_id)
    assert result["saved"] and result["effective"]
    for scope in scopes:
        assert require(s, scope)
    # Every record is re-read and authenticated with the real protected key;
    # an in-memory model parse alone would miss these canonicalization paths.
    plan = read(s, "plan", Plan, reviewed["preview_id"])
    grant = read(s, "grant", Grant, 1)
    native = read(s, "native", Native, grant["data"]["native_review_id"])
    receipt = read(s, "action", Action, request_id)
    assert plan["state"] == "consent_applied" and native["state"] == "administrator_approved"
    assert grant["data"]["selection"]["scopes"] == scopes
    assert receipt["data"]["result"]["saved"]
    assert str(MAX_MONOTONIC_NS) in json.dumps(plan)
    assert str(MAX_MONOTONIC_NS) in json.dumps(grant)
    replayed = allow(s, reviewed, scopes=scopes, request_id=request_id)
    assert replayed["replayed"] and replayed["grant_revision"] == result["grant_revision"]
    with Session(s.engine) as db:
        guard = read_authority_guard(db)
    with s.manager.native_activation(1, s.validated.sha256, s.configuration, guard):
        pass
    with Session(s.engine) as db:
        with authority.effect_admission(db, 1, DISPLAY) as admission:
            assert not admission.compatibility and admission.approved_scopes == frozenset(scopes)
            db.commit()
    assert preview(s)["selected_scopes"] == scopes
    assert _sources(s) == before
    with s.engine.begin() as db:
        db.execute(update(Grant).where(Grant.installation_id == 1).values(seal="f" * 64))
    with pytest.raises((authority.AuthorityManagementError, AuthorityReviewKeyError, ValueError)):
        require(s, DISPLAY)


@pytest.mark.parametrize("unavailable", ["absent", "unhealthy"])
def test_optional_agent_gpio_unavailable_never_blocks_lcd_or_infers_input_rights(state, unavailable):
    s = configure(state, input_consumer=True, agent_modules=True)
    with Session(s.engine) as db, db.begin():
        if unavailable == "absent":
            db.execute(delete(ModuleInstallation).where(ModuleInstallation.module_id == s.input_module_id))
        else:
            row = db.scalar(select(DeviceCapabilityHealth).where(
                DeviceCapabilityHealth.provider_id == s.input_module_id))
            row.report = {**row.report, "capabilities": [{
                "capability_id": s.input.contract().capability_id, "healthy": False,
                "reason": "driver_unavailable"}]}
    before = _sources(s)
    reviewed = preview(s)
    assert reviewed["scopes"] == [DISPLAY, CONNECTOR]
    assert reviewed["selected_scopes"] == [CONNECTOR]
    assert [item["scope"] for item in reviewed["unavailable_resources"]] == [INPUT]
    assert allow(s, reviewed, scopes=[DISPLAY, CONNECTOR])["effective"]
    assert require(s, DISPLAY) and require(s, CONNECTOR)
    with pytest.raises(authority.AuthorityManagementError):
        require(s, INPUT)
    assert _sources(s) == before


def test_schema_metadata_allowance_does_not_grant_optional_input_or_survive_revocation(state):
    s = configure(state, input_consumer=True)
    allow(s, preview(s), scopes=[DISPLAY, CONNECTOR])
    assert require(s, DISPLAY) and require(s, CONNECTOR)
    with pytest.raises(authority.AuthorityManagementError):
        require(s, INPUT)
    reviewed = preview(s)
    with pytest.raises(authority.AuthorityManagementError, match="actor_unavailable"):
        consent.allow(s.manager, 1, actor_token=s.user_token, request_id=identity(),
            preview_id=reviewed["preview_id"], expected_revision=reviewed["revision"],
            fingerprint=reviewed["fingerprint"], scopes=[DISPLAY, INPUT, CONNECTOR],
            user_permissions=[], accept_native_code=True)
    # Failed user approval leaves the exact selected scopes and source untouched.
    assert read(s, "grant", Grant, 1)["data"]["selection"]["scopes"] == [DISPLAY, CONNECTOR]
    assert require(s, CONNECTOR)
    status = s.manager.inspect(1)
    s.manager.revoke(1, actor_token=s.token, request_id=identity(),
        expected_revision=status["grant_record_revision"])
    for scope in (DISPLAY, INPUT, CONNECTOR):
        with pytest.raises(authority.AuthorityManagementError):
            require(s, scope)
