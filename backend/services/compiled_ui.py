"""Install-time compiler and immutable artifact store for compiled UI packages."""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from backend.services.module_packages import ValidatedModulePackage


IMPORT_PATTERN = re.compile(
    r"(?:from\s+|import\s*\(\s*)['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)
ALLOWED_BARE_IMPORTS = {"vue"}


class CompiledUiBuildError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CompiledUiArtifact:
    module_id: str
    version: str
    source_sha256: str
    path: Path
    entrypoints: dict[str, str]
    styles: tuple[str, ...]


def compiled_artifacts_dir() -> Path:
    return Path(
        os.getenv(
            "COMPILED_UI_ARTIFACTS_DIR",
            ".runtime/compiled-extensions",
        )
    )


def _compiler_node() -> str:
    return os.getenv("COMPILED_UI_NODE", "node")


def _compiler_script() -> Path:
    configured = os.getenv("COMPILED_UI_COMPILER_SCRIPT")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).parents[2] / "frontend" / "compiler" / "compile-ui-extension.mjs"


def _validate_source_imports(workspace: Path) -> None:
    for source in (workspace / "source" / "frontend").rglob("*"):
        if not source.is_file() or source.suffix.lower() not in {".vue", ".ts", ".js"}:
            continue
        text = source.read_text(encoding="utf-8")
        for imported in IMPORT_PATTERN.findall(text):
            if imported.startswith(("./", "../")) or imported in ALLOWED_BARE_IMPORTS:
                continue
            raise CompiledUiBuildError(f"compiled UI import is not allowed: {imported}")


def _load_artifact(path: Path, validated: ValidatedModulePackage) -> CompiledUiArtifact:
    try:
        metadata = json.loads((path / "artifact.json").read_text(encoding="utf-8"))
        index = json.loads((path / "entrypoints.json").read_text(encoding="utf-8"))
        entries = index["entries"]
        styles = tuple(index.get("styles", []))
    except (OSError, KeyError, json.JSONDecodeError, TypeError) as exc:
        raise CompiledUiBuildError("compiled UI artifact index is invalid") from exc

    if metadata != {
        "module_id": validated.manifest.module_id,
        "version": validated.manifest.version,
        "source_sha256": validated.sha256,
    }:
        raise CompiledUiBuildError("compiled UI artifact identity does not match its source package")

    expected_ids = {item.entrypoint_id for item in validated.compiled_ui.entrypoints}
    if set(entries) != expected_ids:
        raise CompiledUiBuildError("compiled UI artifact entrypoints do not match the source contract")
    for relative in [*entries.values(), *styles]:
        target = (path / relative).resolve()
        if path.resolve() not in target.parents or not target.is_file():
            raise CompiledUiBuildError("compiled UI artifact references an invalid output file")
    return CompiledUiArtifact(
        module_id=validated.manifest.module_id,
        version=validated.manifest.version,
        source_sha256=validated.sha256,
        path=path,
        entrypoints=entries,
        styles=styles,
    )


def compile_ui_package(
    package: bytes,
    validated: ValidatedModulePackage,
    *,
    timeout_seconds: int = 90,
) -> CompiledUiArtifact:
    if validated.compiled_ui is None:
        raise CompiledUiBuildError("module package does not contain compiled UI source")

    root = compiled_artifacts_dir().resolve()
    destination = (
        root
        / validated.manifest.module_id
        / validated.manifest.version
        / validated.sha256
    )
    if destination.is_dir():
        return _load_artifact(destination, validated)

    destination.parent.mkdir(parents=True, exist_ok=True)
    # Keep the staging directory on the artifact filesystem so the final
    # directory rename remains atomic even when /tmp is a separate mount.
    with tempfile.TemporaryDirectory(
        prefix=".3mm-compiled-ui-",
        dir=destination.parent,
    ) as temporary:
        temporary_root = Path(temporary)
        workspace = temporary_root / "source"
        output = temporary_root / "artifact"
        workspace.mkdir()
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            archive.extractall(workspace)

        _validate_source_imports(workspace)
        command = [
            _compiler_node(),
            str(_compiler_script()),
            str(workspace),
            str(output),
        ]
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(temporary_root),
            "TMPDIR": str(temporary_root),
            "TEMP": str(temporary_root),
            "TMP": str(temporary_root),
            "NO_COLOR": "1",
        }
        for name in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"):
            if value := os.environ.get(name):
                environment[name] = value
        if os.name == "nt":
            environment.update(
                {
                    "USERPROFILE": str(temporary_root),
                    "HOMEDRIVE": temporary_root.drive,
                    "HOMEPATH": str(temporary_root)[len(temporary_root.drive) :],
                    "APPDATA": str(temporary_root / "AppData" / "Roaming"),
                    "LOCALAPPDATA": str(temporary_root / "AppData" / "Local"),
                }
            )
        try:
            result = subprocess.run(
                command,
                cwd=workspace,
                env=environment,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CompiledUiBuildError(f"compiled UI toolchain failed: {exc}") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "compiler failed").strip()
            raise CompiledUiBuildError(f"compiled UI build failed: {detail[-2000:]}")

        (output / "compiled-ui.json").write_text(
            json.dumps(validated.compiled_ui.model_dump(mode="json"), indent=2) + "\n",
            encoding="utf-8",
        )
        (output / "artifact.json").write_text(
            json.dumps(
                {
                    "module_id": validated.manifest.module_id,
                    "version": validated.manifest.version,
                    "source_sha256": validated.sha256,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        _load_artifact(output, validated)
        try:
            output.rename(destination)
        except FileExistsError:
            pass

    return _load_artifact(destination, validated)


def load_compiled_ui_artifact(validated: ValidatedModulePackage) -> CompiledUiArtifact:
    """Load an already-published artifact without invoking the compiler."""
    if validated.compiled_ui is None:
        raise CompiledUiBuildError("module package does not contain compiled UI source")
    destination = (
        compiled_artifacts_dir().resolve()
        / validated.manifest.module_id
        / validated.manifest.version
        / validated.sha256
    )
    if not destination.is_dir():
        raise CompiledUiBuildError("compiled UI artifact is not available")
    return _load_artifact(destination, validated)
