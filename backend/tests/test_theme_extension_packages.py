"""Focused contract and package-boundary tests; no live installation required."""

import io
import json
import zipfile

import pytest
from pydantic import ValidationError

from backend.services.module_packages import ModulePackageError, validate_module_package
from three_mm_protocol import ThemeExtensionV1


def definition():
    return {
        "theme_extension_version": 1,
        "design_api_version": 1,
        "module_id": "org.example.theme",
        "version": "1.0.0",
        "name": {"en": "Example", "translations": {"bg": "Пример"}},
        "light": {"body_bg": "#FFFFFF", "text_primary": "#222222", "radius_sm": 0},
        "dark": {"body_bg": "#16181C", "text_primary": "#E5E7EB"},
    }


def manifest():
    return {
        "manifest_version": 2,
        "module_id": "org.example.theme",
        "name": "Example",
        "version": "1.0.0",
        "runtimes": ["ui"],
        "entrypoints": {"ui": "theme-extension.json"},
        "compatibility": {"protocol": "1.0", "architectures": ["any"]},
        "health_check": {"type": "json_file", "path": "theme-extension.json"},
    }


def package(*, theme=None, metadata=None, extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("manifest.json", json.dumps(metadata or manifest()))
        archive.writestr("theme-extension.json", json.dumps(theme or definition()))
        if extra is not None:
            archive.writestr(extra, "not allowed")
    return output.getvalue()


def test_theme_uses_the_existing_immutable_package_contract():
    blob = package()
    validated = validate_module_package(blob, architecture="armv6l")
    assert validated.theme_extension is not None
    assert validated.theme_extension.light.radius_sm == 0
    assert validated.theme_extension.name.translations["bg"] == "Пример"
    assert validated.theme_extension.dark.card_bg is None  # built-in fallback
    assert len(validated.sha256) == 64
    assert validated.size_bytes == len(blob)
    assert validated.runtime_extension is None
    assert validated.compiled_ui is None
    assert validated.application_extension is None


@pytest.mark.parametrize("value", ["red", "var(--secret)", "url(https://example.com/x)", "#fff;display:none", "#00000000"])
def test_theme_rejects_css_expressions_and_non_contract_colors(value):
    theme = definition()
    theme["light"]["body_bg"] = value
    with pytest.raises(ModulePackageError, match="invalid theme-extension"):
        validate_module_package(package(theme=theme))


@pytest.mark.parametrize("key,value", [("radius_md", -1), ("radius_md", 51), ("radius_md", True), ("radius_md", "8"), ("radius_md", 1.5), ("position", "fixed"), ("css", "*{display:none}")])
def test_theme_rejects_unbounded_or_unknown_tokens(key, value):
    theme = definition()
    theme["dark"][key] = value
    with pytest.raises(ValidationError):
        ThemeExtensionV1.model_validate(theme)


@pytest.mark.parametrize("change", [{"dark": {}}, {"dark": None}, {"base_theme": "org.other.theme"}, {"design_api_version": 2}, {"scripts": ["main.js"]}, {"routes": ["/admin"]}])
def test_theme_requires_both_modes_and_a_closed_contract(change):
    theme = definition()
    theme.update(change)
    with pytest.raises(ValidationError):
        ThemeExtensionV1.model_validate(theme)


@pytest.mark.parametrize("extra", ["theme.css", "theme.js", "assets/logo.svg", "source/frontend/App.vue", "service/app.py"])
def test_theme_package_cannot_ship_executable_content_or_arbitrary_assets(extra):
    with pytest.raises(ModulePackageError, match="forbidden files"):
        validate_module_package(package(extra=extra))


@pytest.mark.parametrize("changes", [
    {"permissions": ["data.read"]},
    {"registrations": [{"kind": "navigation", "registration_id": "org.example.nav"}]},
    {"runtimes": ["core", "ui"]},
    {"entrypoints": {"ui": "something-else.json"}},
    {"capabilities": {"provides": ["gpio.digital.control"]}},
    {"configuration_defaults": {"key": "value"}},
    {"dependencies": {"org.example.other": ">=1.0.0"}},
    {"compatibility": {"protocol": "1.0", "architectures": ["aarch64"]}},
    {"health_check": {"type": "file_exists", "path": "other"}},
])
def test_theme_cannot_request_other_runtime_authority(changes):
    metadata = manifest()
    metadata.update(changes)
    with pytest.raises(ModulePackageError, match="theme extension"):
        validate_module_package(package(metadata=metadata))


@pytest.mark.parametrize("change", [{"module_id": "org.other.theme"}, {"version": "2.0.0"}])
def test_theme_identity_is_bound_to_the_package(change):
    theme = definition()
    theme.update(change)
    with pytest.raises(ModulePackageError, match="identity"):
        validate_module_package(package(theme=theme))


def test_theme_definition_is_bounded_before_parsing():
    theme = definition()
    theme["name"]["translations"]["bg"] = "x" * (64 * 1024)
    with pytest.raises(ModulePackageError, match="size limit"):
        validate_module_package(package(theme=theme))
