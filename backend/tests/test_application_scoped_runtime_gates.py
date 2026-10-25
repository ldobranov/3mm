"""Unsupported scoped entry paths must not reach legacy execution."""

import pytest
from sqlalchemy import update

from backend.config import ApplicationRuntimeSettings
from backend.db.module import (
    ApplicationExtensionInstallation as Installation,
)
from backend.services import application_extensions as gateway
from backend.services import application_public_web as public_web
from backend.services.application_extensions import ApplicationGatewayError
from backend.tests.test_application_access import environment as access_environment
from backend.tests.test_application_public_web import registry
from backend.tests.test_module_packages import application_package
from backend.tests.test_application_public_web import definition as public_definition
from three_mm_runtime.application_transport import DispatchPhase


@pytest.mark.parametrize("mode", ["enforced", "review_required"])
def test_public_http_refuses_unsupported_mode_without_hiding_other_apps(
    registry, monkeypatch, mode
):
    db, add, _definitions = registry
    _, blocked, _ = add("org.example.scoped", "/scoped", 1)
    add("org.example.legacy", "/legacy", 2)
    blocked.authority_mode = mode
    db.commit()
    with pytest.raises(public_web.ApplicationPublicWebError, match="scoped") as error:
        public_web.prepare_public_http(
            db, ApplicationRuntimeSettings(), method="GET", path="/scoped"
        )
    assert error.value.status_code == 503
    binding, *_ = public_web.prepare_public_http(
        db, ApplicationRuntimeSettings(), method="GET", path="/legacy")
    assert binding.route.path == "/legacy"



@pytest.mark.parametrize("mode", ["enforced", "review_required"])
def test_direct_gateway_cannot_bypass_outer_gate(monkeypatch, tmp_path, mode):
    blob = application_package(definition=public_definition(
        "org.3mm.workflow-reference", "/scoped").model_dump(mode="json"))
    values = access_environment(monkeypatch, tmp_path, blob)
    client, db, engine, _, _, installation, package, *_ = values
    installation.authority_mode = mode
    db.commit()
    calls = []

    class Transport:
        def __init__(self, *_args):
            calls.append("constructed")

        def invoke(self, *_args, **_kwargs):
            calls.append("invoked")
            return {}

    monkeypatch.setattr(gateway, "ApplicationServiceClient", Transport)
    try:
        with pytest.raises(ApplicationGatewayError, match="scoped") as error:
            gateway.invoke_application(
                installation,
                package,
                gateway_settings(tmp_path),
                "render_public",
                {},
                {
                    "audience": "public",
                    "idempotency_key": "logical-job",
                },
                required_audience="public",
            )
        assert error.value.phase == DispatchPhase.NOT_DISPATCHED
        assert error.value.retryable is False
        assert calls == []
    finally:
        client.close()
        db.close()
        engine.dispose()


def gateway_settings(tmp_path):
    return ApplicationRuntimeSettings(key_root=tmp_path / "keys")


def test_direct_gateway_reloads_mode_not_cached_orm_state(monkeypatch, tmp_path):
    blob = application_package(definition=public_definition("org.3mm.workflow-reference", "/scoped").model_dump(mode="json"))
    values = access_environment(monkeypatch, tmp_path, blob)
    client, db, engine, _, _, installation, package, *_ = values
    db.expire_on_commit = False
    assert installation.authority_mode == "compatibility"
    db.execute(
        update(Installation)
        .values(authority_mode="enforced")
        .execution_options(synchronize_session=False)
    )
    db.commit()
    assert installation.authority_mode == "compatibility"
    monkeypatch.setattr(
        gateway,
        "ApplicationServiceClient",
        lambda *_: pytest.fail("Transport must not be created"),
    )
    try:
        with pytest.raises(ApplicationGatewayError, match="scoped"):
            gateway.invoke_application(
                installation,
                package,
                gateway_settings(tmp_path),
                "render_public",
                {},
                {"audience": "public"},
                required_audience="public",
            )
    finally:
        client.close()
        db.close()
        engine.dispose()


def test_public_http_reloads_mode_after_route_resolution(registry, monkeypatch):
    db, add, _ = registry
    _, installation, _ = add("org.example.changed", "/changed", 1)
    db.expire_on_commit = False
    real_resolve = public_web.resolve_public_route

    def resolve_then_change(*args, **kwargs):
        result = real_resolve(*args, **kwargs)
        db.execute(
            update(Installation)
            .where(Installation.id == installation.id)
            .values(authority_mode="enforced")
            .execution_options(synchronize_session=False)
        )
        db.commit()
        assert installation.authority_mode == "compatibility"
        return result

    monkeypatch.setattr(public_web, "resolve_public_route", resolve_then_change)
    with pytest.raises(public_web.ApplicationPublicWebError, match="scoped"):
        public_web.prepare_public_http(
            db, ApplicationRuntimeSettings(), method="GET", path="/changed"
        )
