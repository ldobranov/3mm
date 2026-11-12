from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import backend.database  # noqa: F401 - register the complete model graph
from backend.config import ApplicationRuntimeSettings
from backend.db.base import Base
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.applications.public_web import routes as public_web
from backend.applications.public_web.routes import ApplicationPublicWebError
from backend.tests.test_module_packages import application_definition
from packages.protocol import (
    ApplicationExtensionV1,
    public_http_request_schema_v1,
    public_http_response_schema_v1,
)
from packages.protocol.application_extension import ApplicationPublicWebhookV1


# Test composition of the separated route admission and response-validation
# boundaries. Real signed IPC/FD handoff is covered by test_application_public_web_transport.
def dispatch_public_http(db, settings, **request):
    binding, installation, package, payload = public_web.prepare_public_http(db, settings, **request)
    result = invoke_application(installation, package, settings, binding.route.handler_operation_id,
        payload.model_dump(mode="json"), {"audience": "public"}, required_audience="public")
    return public_web.validate_public_http_response(binding, result)


def invoke_application(*args, **kwargs):
    raise AssertionError("Test dispatcher must supply a result")


def definition(module_id: str, path: str, *, max_response_bytes: int = 256 * 1024):
    value = application_definition(module_id=module_id)
    value["operations"].append(
        {
            "operation_id": "render_public",
            "kind": "query",
            "audiences": ["public"],
            "idempotency": "forbidden",
            "input_schema": public_http_request_schema_v1(),
            "output_schema": public_http_response_schema_v1(),
        }
    )
    value["public_http_routes"] = [
        {
            "route_id": "public_page",
            "path": path,
            "methods": ["GET", "HEAD"],
            "handler_operation_id": "render_public",
            "content_types": ["text/html; charset=utf-8", "application/xml"],
            "max_response_bytes": max_response_bytes,
        }
    ]
    return ApplicationExtensionV1.model_validate(value)


@pytest.fixture
def registry(monkeypatch, tmp_path: Path):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = Session(engine)
    definitions: dict[str, ApplicationExtensionV1] = {}

    def add(module_id: str, path: str, digit: int, *, active: bool = True, max_response_bytes: int = 256 * 1024):
        current = definition(module_id, path, max_response_bytes=max_response_bytes)
        definitions[module_id] = current
        package = ModulePackage(
            module_id=module_id,
            version="1.0.0",
            manifest={},
            sha256=f"{digit:064x}",
            size_bytes=1,
            file_path="unused",
            registrations=[],
        )
        db.add(package)
        db.flush()
        installation = ApplicationExtensionInstallation(
            module_id=module_id,
            module_package_id=package.id,
            instance_id=str(digit) * 24,
            active_version=package.version,
            status="active" if active else "disabled",
            enabled=active,
            socket_path="unused",
            configuration={},
        )
        db.add(installation)
        db.commit()
        return package, installation, current

    monkeypatch.setattr(
        public_web,
        "load_application_definition",
        lambda package: definitions[package.module_id],
    )
    try:
        yield db, add, definitions
    finally:
        db.close()
        engine.dispose()


def test_registry_reconstructs_only_active_routes_and_matches_parameters(registry):
    db, add, _definitions = registry
    add("org.3mm.public-one", "/items/{slug}", 1)
    add("org.3mm.public-disabled", "/disabled", 2, active=False)

    items = public_web.build_public_route_registry(db)
    assert [(item.module_id, item.route.path) for item in items] == [
        ("org.3mm.public-one", "/items/{slug}")
    ]

    binding, params = public_web.resolve_public_route(db, "GET", "/items/example")
    assert binding.module_id == "org.3mm.public-one"
    assert params == {"slug": "example"}

    with pytest.raises(ApplicationPublicWebError) as missing:
        public_web.resolve_public_route(db, "GET", "/disabled")
    assert missing.value.status_code == 404


def test_candidate_rejects_cross_application_overlap_but_allows_internal_specificity(registry):
    db, add, _definitions = registry
    add("org.3mm.public-one", "/items/{slug}", 1)

    package = ModulePackage(
        module_id="org.3mm.public-two",
        version="1.0.0",
        manifest={},
        sha256="f" * 64,
        size_bytes=1,
        file_path="unused",
        registrations=[],
    )
    db.add(package)
    db.flush()

    with pytest.raises(ApplicationPublicWebError, match="overlaps") as conflict:
        public_web.validate_public_http_candidate(
            db, package, definition(package.module_id, "/items/new")
        )
    assert conflict.value.status_code == 409

    public_web.validate_public_http_candidate(
        db, package, definition(package.module_id, "/other/{slug}")
    )

    overlapping_self = definition(package.module_id, "/a/{value}")
    overlapping_self = overlapping_self.model_copy(
        update={
            "public_http_routes": overlapping_self.public_http_routes
            + (
                overlapping_self.public_http_routes[0].model_copy(
                    update={"route_id": "second", "path": "/a/fixed"}
                ),
            )
        }
    )
    public_web.validate_public_http_candidate(db, package, overlapping_self)

    ambiguous_self = definition(package.module_id, "/a/{value}/fixed")
    ambiguous_self = ambiguous_self.model_copy(
        update={
            "public_http_routes": ambiguous_self.public_http_routes
            + (
                ambiguous_self.public_http_routes[0].model_copy(
                    update={"route_id": "second", "path": "/a/static/{value}"}
                ),
            )
        }
    )
    with pytest.raises(ApplicationPublicWebError, match="overlaps"):
        public_web.validate_public_http_candidate(db, package, ambiguous_self)


def webhook_definition(current, path="/webhooks/demo"):
    # This fixture isolates ownership; package validation covers the webhook's handler schema.
    return current.model_copy(update={"public_http_routes": (), "public_webhook": ApplicationPublicWebhookV1(
        contract_version=1, webhook_id="receive", path=path, signature_profile="hmac_sha256_v1",
        handler_operation_id="receive_event",
    )})


def test_webhook_reservations_cover_http_templates_and_competing_webhooks(registry):
    db, add, definitions = registry
    first, installed, initial = add("org.3mm.callback-one", "/unrelated", 1)
    definitions[first.module_id] = webhook_definition(initial)
    second, competing, template = add("org.3mm.callback-two", "/{area}/{name}", 2, active=False)
    third, _, unrelated = add("org.3mm.callback-three", "/forms/working/extra", 3)

    for conflicting in (template, definition(second.module_id, "/webhooks/demo"), webhook_definition(template)):
        with pytest.raises(ApplicationPublicWebError, match="Public webhook route conflict") as conflict:
            public_web.validate_public_http_candidate(db, second, conflicting)
        assert conflict.value.status_code == 409

    # A pending reservation blocks another activation, but isn't published as HTTP.
    competing.status = "activating"
    db.commit()
    with pytest.raises(ApplicationPublicWebError, match="Public webhook route conflict"):
        public_web.validate_public_http_candidate(db, first, definitions[first.module_id])
    with pytest.raises(ApplicationPublicWebError, match="Public webhook route conflict"):
        public_web.require_reviewed_webhook_route(db, installed.id, "/webhooks/demo")

    # Legacy conflicts fail only the pilot's startup; unrelated public pages still resolve.
    competing.status, competing.enabled = "active", True
    db.commit()
    with pytest.raises(ApplicationPublicWebError, match="Public webhook route conflict"):
        public_web.require_reviewed_webhook_route(db, installed.id, "/webhooks/demo")
    assert public_web.resolve_public_route(db, "GET", unrelated.public_http_routes[0].path)[0].module_id == third.module_id
    assert all(route.module_id != first.module_id for route in public_web.build_public_route_registry(db))


def test_reservation_change_between_package_validation_and_write_is_refused(registry):
    db, add, definitions = registry
    first, _, initial = add("org.3mm.callback-one", "/unrelated", 1, active=False)
    second, competing, template = add("org.3mm.callback-two", "/webhooks/{name}", 2, active=False)
    candidate = definitions[first.module_id] = webhook_definition(initial)
    snapshot = public_web.validate_public_http_candidate(db, first, candidate)
    assert snapshot == ()
    public_web.require_current_public_route_reservations(db, first.module_id, snapshot)
    competing.status = "activating"
    db.commit()
    with pytest.raises(ApplicationPublicWebError, match="ownership changed") as conflict:
        public_web.require_current_public_route_reservations(db, first.module_id, snapshot)
    assert conflict.value.status_code == 409
    with pytest.raises(ApplicationPublicWebError, match="Public webhook route conflict"):
        public_web.validate_public_http_candidate(db, first, candidate)


def test_dispatch_filters_credentials_and_validates_response(registry, monkeypatch, tmp_path):
    db, add, _definitions = registry
    _package, _installation, _definition = add(
        "org.3mm.public-one", "/items/{slug}", 1
    )
    captured = {}

    def invoke(installation, package, settings, operation_id, payload, context, **kwargs):
        captured.update(
            installation=installation,
            package=package,
            settings=settings,
            operation_id=operation_id,
            payload=payload,
            context=context,
            kwargs=kwargs,
        )
        return {
            "status": 200,
            "content_type": "text/html; charset=utf-8",
            "headers": {"Cache-Control": "public, max-age=60"},
            "body": "<h1>Example</h1>",
        }

    monkeypatch.setattr(__import__(__name__, fromlist=["x"]), "invoke_application", invoke)
    settings = ApplicationRuntimeSettings(
        root=tmp_path / "apps",
        key_root=tmp_path / "keys",
        helper_socket=tmp_path / "helper.sock",
    )
    response = dispatch_public_http(
        db,
        settings,
        method="GET",
        path="/items/example",
        query={"page": ["1", "2"]},
        headers={
            "Accept-Language": "bg-BG",
            "Authorization": "Bearer private",
            "Cookie": "admin=session",
        },
    )

    assert response.status == 200
    assert response.headers == {"cache-control": "public, max-age=60"}
    assert captured["operation_id"] == "render_public"
    assert captured["payload"]["path_params"] == {"slug": "example"}
    assert captured["payload"]["query"] == {"page": ["1", "2"]}
    assert captured["payload"]["headers"] == {"accept-language": "bg-BG"}
    assert captured["context"]["audience"] == "public"
    assert "idempotency_key" not in captured["context"]
    assert captured["kwargs"] == {"required_audience": "public"}


def test_dispatch_fails_closed_for_method_content_type_size_and_bad_headers(
    registry, monkeypatch, tmp_path
):
    db, add, _definitions = registry
    add(
        "org.3mm.public-one",
        "/items/{slug}",
        1,
        max_response_bytes=1024,
    )
    settings = ApplicationRuntimeSettings(
        root=tmp_path / "apps",
        key_root=tmp_path / "keys",
        helper_socket=tmp_path / "helper.sock",
    )

    with pytest.raises(ApplicationPublicWebError) as method:
        dispatch_public_http(
            db, settings, method="POST", path="/items/example"
        )
    assert method.value.status_code == 405

    monkeypatch.setattr(
        __import__(__name__, fromlist=["x"]),
        "invoke_application",
        lambda *_args, **_kwargs: {
            "status": 200,
            "content_type": "text/plain; charset=utf-8",
            "headers": {},
            "body": "not declared",
        },
    )
    with pytest.raises(ApplicationPublicWebError, match="undeclared content type"):
        dispatch_public_http(
            db, settings, method="GET", path="/items/example"
        )

    monkeypatch.setattr(
        __import__(__name__, fromlist=["x"]),
        "invoke_application",
        lambda *_args, **_kwargs: {
            "status": 200,
            "content_type": "text/html; charset=utf-8",
            "headers": {},
            "body": "x" * 1025,
        },
    )
    with pytest.raises(ApplicationPublicWebError, match="too large"):
        dispatch_public_http(
            db, settings, method="GET", path="/items/example"
        )

    monkeypatch.setattr(
        __import__(__name__, fromlist=["x"]),
        "invoke_application",
        lambda *_args, **_kwargs: {
            "status": 200,
            "headers": {"Set-Cookie": "bad=1"},
        },
    )
    with pytest.raises(ApplicationPublicWebError, match="invalid response"):
        dispatch_public_http(
            db, settings, method="GET", path="/items/example"
        )



def test_dispatch_accepts_declared_bounded_binary_asset(registry, monkeypatch, tmp_path):
    import base64

    db, add, definitions = registry
    package, _installation, current = add(
        "org.3mm.public-asset", "/assets/{name}", 7, max_response_bytes=1024
    )
    route = current.public_http_routes[0].model_copy(
        update={"content_types": ("image/png",), "max_response_bytes": 1024}
    )
    definitions[package.module_id] = current.model_copy(
        update={"public_http_routes": (route,)}
    )
    payload = b"\x89PNG\r\n\x1a\n" + b"x" * 64
    monkeypatch.setattr(
        __import__(__name__, fromlist=["x"]),
        "invoke_application",
        lambda *_args, **_kwargs: {
            "status": 200,
            "content_type": "image/png",
            "headers": {"ETag": '"asset-v1"'},
            "body_base64": base64.b64encode(payload).decode("ascii"),
        },
    )
    settings = ApplicationRuntimeSettings(
        root=tmp_path / "apps",
        key_root=tmp_path / "keys",
        helper_socket=tmp_path / "helper.sock",
    )
    response = dispatch_public_http(
        db, settings, method="GET", path="/assets/logo.png"
    )
    assert base64.b64decode(response.body_base64) == payload



def test_public_route_ownership_reconstructs_after_upgrade_disable_restart_rollback_and_uninstall(
    registry,
):
    db, add, definitions = registry
    module_id = "org.3mm.public-lifecycle"
    first_package, installation, first_definition = add(
        module_id, "/version-one/{slug}", 3
    )

    assert [item.route.path for item in public_web.build_public_route_registry(db)] == [
        "/version-one/{slug}"
    ]

    second_package = ModulePackage(
        module_id=module_id,
        version="2.0.0",
        manifest={},
        sha256="4" * 64,
        size_bytes=1,
        file_path="unused-v2",
        registrations=[],
    )
    db.add(second_package)
    db.flush()
    definitions[module_id] = definition(module_id, "/version-two/{slug}").model_copy(
        update={"version": "2.0.0"}
    )
    installation.module_package_id = second_package.id
    installation.active_version = second_package.version
    db.commit()

    assert [item.route.path for item in public_web.build_public_route_registry(db)] == [
        "/version-two/{slug}"
    ]

    installation.enabled = False
    installation.status = "disabled"
    db.commit()
    assert public_web.build_public_route_registry(db) == ()

    installation.enabled = True
    installation.status = "active"
    db.commit()
    restarted = Session(db.get_bind())
    try:
        assert [item.route.path for item in public_web.build_public_route_registry(restarted)] == [
            "/version-two/{slug}"
        ]
    finally:
        restarted.close()

    definitions[module_id] = first_definition
    installation.module_package_id = first_package.id
    installation.active_version = first_package.version
    db.commit()

    assert [item.route.path for item in public_web.build_public_route_registry(db)] == [
        "/version-one/{slug}"
    ]
    with pytest.raises(ApplicationPublicWebError) as stale:
        public_web.resolve_public_route(db, "GET", "/version-two/example")
    assert stale.value.status_code == 404

    db.delete(installation)
    db.commit()
    assert public_web.build_public_route_registry(db) == ()


def test_public_route_registry_fails_closed_on_inconsistent_active_package(registry):
    db, add, _definitions = registry
    _package, installation, _definition = add(
        "org.3mm.public-inconsistent", "/safe", 5
    )
    installation.active_version = "9.9.9"
    db.commit()

    with pytest.raises(ApplicationPublicWebError, match="inconsistent") as error:
        public_web.build_public_route_registry(db)
    assert error.value.status_code == 503



def test_same_application_static_route_wins_over_parameter_route(registry):
    db, add, definitions = registry
    package, _installation, current = add(
        "org.3mm.public-specificity", "/items/{slug}", 8
    )
    static_route = current.public_http_routes[0].model_copy(
        update={"route_id": "items_new", "path": "/items/new"}
    )
    definitions[package.module_id] = current.model_copy(
        update={"public_http_routes": current.public_http_routes + (static_route,)}
    )

    binding, params = public_web.resolve_public_route(db, "GET", "/items/new")
    assert binding.route.route_id == "items_new"
    assert params == {}

    binding, params = public_web.resolve_public_route(db, "GET", "/items/example")
    assert binding.route.route_id == "public_page"
    assert params == {"slug": "example"}
