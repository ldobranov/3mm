import importlib
import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
import zipfile
import io

from backend.services.module_packages import validate_module_package
from three_mm_application_sdk import ApplicationContext, ApplicationStorage, OperationContext
from three_mm_protocol import ApplicationPublicHttpResponseV1


REFERENCE_ROOT = Path(__file__).parents[2] / "modules" / "public-web-reference"


class FixedClock:
    def now(self):
        return datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def _builder_module():
    spec = importlib.util.spec_from_file_location(
        "public_web_reference_builder",
        REFERENCE_ROOT / "build_reference_package.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _context(audience: str):
    return OperationContext(
        audience=audience,
        correlation_id=f"public-reference-{audience}",
        idempotency_key=None,
    )


def _request(path: str, path_params=None):
    return {
        "method": "GET",
        "path": path,
        "path_params": path_params or {},
        "query": {},
        "headers": {},
    }


def test_public_web_reference_is_deterministic_valid_and_domain_neutral(tmp_path):
    builder = _builder_module()
    package = builder.build_package()
    assert package == builder.build_package()

    validated = validate_module_package(package, architecture="aarch64")
    assert validated.manifest.module_id == "org.3mm.public-web-reference"
    assert set(validated.manifest.permissions) == {
        "data.read",
        "data.write",
        "process.spawn",
    }
    assert validated.application_extension is not None
    assert [route.path for route in validated.application_extension.public_http_routes] == [
        "/",
        "/items/{slug}",
        "/feed.xml",
        "/info.txt",
        "/old-item",
        "/gone",
    ]
    assert validated.application_extension.connectors == ()
    assert validated.application_extension.event_subscriptions == ()
    assert validated.application_extension.jobs == ()

    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        wheel_name = validated.application_extension.service.artifact
        wheel = archive.read(wheel_name)
    wheel_path = tmp_path / Path(wheel_name).name
    wheel_path.write_bytes(wheel)

    sys.path.insert(0, str(wheel_path))
    try:
        migrations = importlib.import_module("public_web_reference.migrations")
        service_module = importlib.import_module("public_web_reference.service")
        storage = ApplicationStorage(tmp_path / "data")
        storage.migrate(migrations.get_migrations(), "0001")
        service = service_module.create_service(
            ApplicationContext(
                module_id=validated.manifest.module_id,
                version=validated.manifest.version,
                data_dir=tmp_path / "data",
                configuration={},
                storage=storage,
                platform=None,
                clock=FixedClock(),
            )
        )

        assert service.handle("health", {}, _context("internal")) == {"status": "ready"}

        home = ApplicationPublicHttpResponseV1.model_validate(
            service.handle("render_public", _request("/"), _context("public"))
        )
        assert home.status == 200
        assert "Public Web Reference" in home.body

        item = ApplicationPublicHttpResponseV1.model_validate(
            service.handle(
                "render_public",
                _request("/items/example", {"slug": "<script>"}),
                _context("public"),
            )
        )
        assert item.status == 200
        assert "&lt;script&gt;" in item.body
        assert "<script>" not in item.body

        feed = ApplicationPublicHttpResponseV1.model_validate(
            service.handle("render_public", _request("/feed.xml"), _context("public"))
        )
        assert feed.content_type == "application/xml"
        assert feed.body.startswith("<?xml")

        info = ApplicationPublicHttpResponseV1.model_validate(
            service.handle("render_public", _request("/info.txt"), _context("public"))
        )
        assert info.body == "Public Web Reference\n"

        redirect = ApplicationPublicHttpResponseV1.model_validate(
            service.handle("render_public", _request("/old-item"), _context("public"))
        )
        assert redirect.status == 301
        assert redirect.location == "/items/example"

        gone = ApplicationPublicHttpResponseV1.model_validate(
            service.handle("render_public", _request("/gone"), _context("public"))
        )
        assert gone.status == 410
        assert gone.body == "Gone\n"
    finally:
        sys.path.remove(str(wheel_path))
        for name in list(sys.modules):
            if name == "public_web_reference" or name.startswith("public_web_reference."):
                sys.modules.pop(name)
