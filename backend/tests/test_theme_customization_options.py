"""Package-declared controls are bounded and enforced by the existing admin API."""

import json

import pytest
from sqlalchemy import select

from backend.db.audit_log import AuditLog
from backend.db.settings import Settings
from backend.services.module_packages import ModulePackageError, validate_module_package
from backend.services.theme_customization import customization_key
from backend.tests.test_theme_extension_lifecycle import BASE, runtime  # noqa: F401
from backend.tests.test_theme_extension_v2 import definition_v2, install_v2, v2_package


def theme_with_options(options):
    theme = definition_v2()
    theme["design"]["header_style"] = "theme"
    theme["customization_options"] = options
    return theme


@pytest.mark.parametrize("options", [
    {"css": "body{}"}, {"navigation": "sidebar"}, {"navigation": ["external"]},
    {"navigation": ["sidebar", "sidebar"]}, {"navigation": ["top"]},
    {"colors": ["url"]}, {"colors": ["accent", "accent"]}, {"colors": None},
])
def test_unsafe_or_inconsistent_options_rejected_before_install(options):
    with pytest.raises(ModulePackageError):
        validate_module_package(v2_package(theme_with_options(options)))


def test_offered_controls_enforced_without_changing_theme_or_authority(runtime):
    client, db, admin, user, _, _ = runtime
    digest = install_v2(client, admin, v2_package(theme_with_options({
        "navigation": ["sidebar", "top"], "colors": ["border"],
    })))
    assert client.post(f"{BASE}/selection", headers=admin, json={"sha256": digest}).status_code == 200
    original = client.get(f"{BASE}/appearance").json()["theme"]
    design = original["design"]
    preferences = {
        "navigation": "top", "density": design["layout"]["density"],
        "button": design["components"]["button"], "card": design["components"]["card"],
        "header_style": design["header_style"], "header_background_color": "#ffffff",
        "header_text_color": "#000000", "colors": {"light": {"border": "#123456"}},
    }
    def save(headers, value):
        return client.post(f"{BASE}/customization", headers=headers,
                           json={"sha256": digest, "preferences": value})
    assert save({}, preferences).status_code == 401
    assert save(user, preferences).status_code == 403
    assert save(admin, preferences).status_code == 200
    public = client.get(f"{BASE}/appearance").json()
    assert public["customization"] == preferences
    assert public["theme"] == original
    audit_count = len(list(db.scalars(select(AuditLog))))
    for change in (
        {"density": "comfortable"},
        {"colors": {"light": {"canvas": design["light"]["canvas"]}}},
    ):
        assert save(admin, {**preferences, **change}).status_code == 422
    assert len(list(db.scalars(select(AuditLog)))) == audit_count
    row = db.scalar(select(Settings).where(Settings.key == customization_key(digest)))
    row.value = json.dumps({**preferences, "colors": {"light": {"canvas": design["light"]["canvas"]}}})
    db.commit()
    public = client.get(f"{BASE}/appearance").json()
    assert public["theme"] == original
    assert "customization" not in public


def test_empty_options_mean_read_only_package_defaults():
    theme = validate_module_package(v2_package(theme_with_options({}))).theme_extension
    assert theme.customization_options.navigation == ()
    assert theme.customization_options.colors == ()
