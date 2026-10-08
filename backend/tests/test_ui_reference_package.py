import runpy
from pathlib import Path

from backend.services.module_packages import validate_module_package


ROOT = Path(__file__).resolve().parents[2] / "modules" / "ui-reference"


def test_neutral_ui_reference_is_deterministic_and_uses_existing_route_contract():
    build = runpy.run_path(str(ROOT / "build_package.py"))["build_package"]
    blob = build()
    assert blob == build()
    validated = validate_module_package(blob)
    assert validated.manifest.runtimes == ("ui",)
    assert validated.application_extension is None  # No business service/reader binding.
    assert validated.manifest.permissions == ()
    route = validated.compiled_ui.entrypoints[0]
    assert route.route == "/ui-reference"
    assert route.requires_role == "admin"
    assert route.label.translations["bg"] == "UI пример"
