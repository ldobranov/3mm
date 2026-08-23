import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest
import backend.database  # noqa: F401 - register every SQLAlchemy relationship used by routes
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db.module import ModulePackage
from backend.routes.modules import router
from backend.services import compiled_ui
from backend.services.compiled_ui import CompiledUiBuildError, compile_ui_package
from backend.services.module_packages import validate_module_package
from backend.utils.db_utils import get_db


def package(source: str = "<template><time>12:34:56</time></template>") -> bytes:
    manifest = {
        "manifest_version": 2,
        "module_id": "org.3mm.clock",
        "name": "Clock",
        "version": "1.0.0",
        "runtimes": ["ui"],
        "entrypoints": {"ui": "compiled-ui.json"},
        "compatibility": {"protocol": "1.0", "architectures": ["any"]},
        "capabilities": {"provides": [], "consumes": []},
        "permissions": [],
        "health_check": {"type": "json_file", "path": "compiled-ui.json"},
        "registrations": [],
    }
    contract = {
        "compiled_ui_version": 1,
        "module_id": "org.3mm.clock",
        "version": "1.0.0",
        "entrypoints": [{
            "entrypoint_id": "clock",
            "kind": "widget",
            "source": "source/frontend/Clock.vue",
            "label": {"en": "Clock"},
        }],
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("compiled-ui.json", json.dumps(contract))
        archive.writestr("source/frontend/Clock.vue", source)
    return output.getvalue()


def fake_compiler(calls):
    def run(command, **kwargs):
        calls.append(command)
        output = Path(command[3])
        (output / "assets").mkdir(parents=True)
        (output / "assets" / "clock-test.mjs").write_text(
            "export default {}", encoding="utf-8"
        )
        (output / "assets" / "clock-test.css").write_text(
            ".clock{}", encoding="utf-8"
        )
        (output / "entrypoints.json").write_text(
            json.dumps({
                "entries": {"clock": "assets/clock-test.mjs"},
                "styles": ["assets/clock-test.css"],
            }),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")
    return run


def test_compiler_publishes_content_addressed_artifact_atomically(monkeypatch, tmp_path):
    blob = package()
    validated = validate_module_package(blob)
    calls = []
    monkeypatch.setenv("COMPILED_UI_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setattr(compiled_ui.subprocess, "run", fake_compiler(calls))

    artifact = compile_ui_package(blob, validated)
    cached = compile_ui_package(blob, validated)

    assert artifact.path == cached.path
    assert artifact.path.name == validated.sha256
    assert artifact.entrypoints == {"clock": "assets/clock-test.mjs"}
    assert artifact.styles == ("assets/clock-test.css",)
    assert len(calls) == 1
    assert Path(calls[0][3]).parent.parent == artifact.path.parent


def test_compiler_rejects_non_allowlisted_import_before_execution(monkeypatch, tmp_path):
    blob = package(
        "<script setup>import value from '@/stores/auth'</script><template>{{ value }}</template>"
    )
    validated = validate_module_package(blob)
    monkeypatch.setenv("COMPILED_UI_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setattr(
        compiled_ui.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("compiler must not execute"),
    )

    with pytest.raises(CompiledUiBuildError, match="import is not allowed"):
        compile_ui_package(blob, validated)


def test_failed_build_does_not_publish_partial_artifact(monkeypatch, tmp_path):
    blob = package()
    validated = validate_module_package(blob)
    root = tmp_path / "artifacts"
    monkeypatch.setenv("COMPILED_UI_ARTIFACTS_DIR", str(root))
    monkeypatch.setattr(
        compiled_ui.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, "", "broken"),
    )

    with pytest.raises(CompiledUiBuildError, match="broken"):
        compile_ui_package(blob, validated)

    assert not (root / "org.3mm.clock" / "1.0.0" / validated.sha256).exists()


def test_catalog_and_asset_endpoint_expose_only_reviewed_hash(monkeypatch, tmp_path):
    blob = package()
    validated = validate_module_package(blob)
    archive_path = tmp_path / "clock.zip"
    archive_path.write_bytes(blob)
    monkeypatch.setenv("COMPILED_UI_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setattr(compiled_ui.subprocess, "run", fake_compiler([]))
    compile_ui_package(blob, validated)

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    ModulePackage.__table__.create(engine)
    db = Session(engine)
    db.add(ModulePackage(
        module_id="org.3mm.clock",
        version="1.0.0",
        manifest=validated.manifest.model_dump(mode="json"),
        sha256=validated.sha256,
        size_bytes=len(blob),
        file_path=str(archive_path),
        registrations=[],
    ))
    db.commit()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    try:
        response = client.get("/api/v1/modules/compiled-ui/catalog")
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["source_sha256"] == validated.sha256
        assert item["entrypoints"][0]["kind"] == "widget"
        asset = client.get(item["entrypoints"][0]["asset_url"])
        assert asset.status_code == 200
        assert asset.text == "export default {}"
        assert "immutable" in asset.headers["cache-control"]
    finally:
        db.close()
        engine.dispose()
