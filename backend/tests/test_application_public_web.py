from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import backend.database  # noqa: F401 - register the complete model graph
from backend.config import ApplicationRuntimeSettings
from backend.db.base import Base
from backend.db.module import ApplicationExtensionInstallation, ModulePackage
from backend.services import application_public_web as public_web
from backend.services.application_public_web import ApplicationPublicWebError
from backend.tests.test_module_packages import application_definition
from three_mm_protocol import (
    ApplicationExtensionV1,
    public_http_request_schema_v1,
    public_http_response_schema_v1,
)


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


def test_candidate_rejects_static_dynamic_and_internal_overlaps(registry):
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
    with pytest.raises(ApplicationPublicWebError, match="overlaps"):
        public_web.validate_public_http_candidate(db, package, overlapping_self)


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

    monkeypatch.setattr(public_web, "invoke_application", invoke)
    settings = ApplicationRuntimeSettings(
        root=tmp_path / "apps",
        key_root=tmp_path / "keys",
        helper_socket=tmp_path / "helper.sock",
    )
    response = public_web.dispatch_public_http(
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
        public_web.dispatch_public_http(
            db, settings, method="POST", path="/items/example"
        )
    assert method.value.status_code == 405

    monkeypatch.setattr(
        public_web,
        "invoke_application",
        lambda *_args, **_kwargs: {
            "status": 200,
            "content_type": "text/plain; charset=utf-8",
            "headers": {},
            "body": "not declared",
        },
    )
    with pytest.raises(ApplicationPublicWebError, match="undeclared content type"):
        public_web.dispatch_public_http(
            db, settings, method="GET", path="/items/example"
        )

    monkeypatch.setattr(
        public_web,
        "invoke_application",
        lambda *_args, **_kwargs: {
            "status": 200,
            "content_type": "text/html; charset=utf-8",
            "headers": {},
            "body": "x" * 1025,
        },
    )
    with pytest.raises(ApplicationPublicWebError, match="too large"):
        public_web.dispatch_public_http(
            db, settings, method="GET", path="/items/example"
        )

    monkeypatch.setattr(
        public_web,
        "invoke_application",
        lambda *_args, **_kwargs: {
            "status": 200,
            "headers": {"Set-Cookie": "bad=1"},
        },
    )
    with pytest.raises(ApplicationPublicWebError, match="invalid response"):
        public_web.dispatch_public_http(
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
        public_web,
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
    response = public_web.dispatch_public_http(
        db, settings, method="GET", path="/assets/logo.png"
    )
    assert base64.b64decode(response.body_base64) == payload
