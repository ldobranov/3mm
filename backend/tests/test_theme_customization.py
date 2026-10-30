"""Saved UI controls are scoped, bounded, audited and independent of ZIP/branding."""

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.db.audit_log import AuditLog
from backend.db.menu import Menu
from backend.db.module import ModulePackage
from backend.db.settings import Settings
from backend.services.theme_customization import customization_key
from backend.tests.test_theme_extension_lifecycle import BASE, runtime, upload
from backend.tests.test_theme_extension_v2 import install_v2


def preferences(**changes):
    return dict(navigation="top", density="compact", button="outline", card="raised",
                header_style="theme", header_background_color="#123456",
                header_text_color="#ffffff", **changes)


def save(client, admin, sha256=None, value=None):
    return client.post(f"{BASE}/customization", headers=admin,
                       json={"sha256": sha256, "preferences": value})


def test_builtin_customization_survives_reload_and_reset_preserves_branding(runtime):
    client, db, admin, _, _, _ = runtime
    db.add_all([Settings(key="site_name", value="Site", language_code="bg"),
                Settings(key="header_bg_color", value="#ABCDEF"),
                Settings(key="logo_url", value="/uploads/settings/logo.png")])
    db.commit()
    original = [(row.key, row.value) for row in db.scalars(select(Settings))]
    value = preferences()
    assert save(client, admin, value=value).status_code == 200
    db.expire_all()
    public = client.get(f"{BASE}/appearance")
    assert public.json() == {"theme": None, "customization": value}
    assert public.headers["cache-control"] == "no-store"
    assert db.scalar(select(AuditLog).where(AuditLog.entity_type == "theme_customization"))
    assert save(client, admin).json() == {"theme": None}
    assert [(row.key, row.value) for row in db.scalars(select(Settings))] == original


def test_exact_theme_versions_have_independent_settings_without_modifying_zip(runtime):
    client, db, admin, _, _, _ = runtime
    digests = [upload(client, admin, version=v).json()["sha256"] for v in ("1.0.0", "1.1.0")]
    for digest in digests:
        client.post(f"{BASE}/packages/{digest}/enable", headers=admin)
    first = db.scalar(select(ModulePackage).where(ModulePackage.sha256 == digests[0]))
    before = Path(first.file_path).read_bytes()
    client.post(f"{BASE}/selection", headers=admin, json={"sha256": digests[0]})
    assert save(client, admin, digests[0], preferences()).status_code == 200
    client.post(f"{BASE}/selection", headers=admin, json={"sha256": digests[1]})
    assert "customization" not in client.get(f"{BASE}/appearance").json()
    assert save(client, admin, digests[0], preferences()).status_code == 409
    client.post(f"{BASE}/selection", headers=admin, json={"sha256": digests[0]})
    assert client.get(f"{BASE}/appearance").json()["customization"] == preferences()
    assert Path(first.file_path).read_bytes() == before
    Path(first.file_path).unlink()
    assert client.get(f"{BASE}/appearance").json() == {"theme": None}


def test_customization_requires_real_admin_and_rejects_extra_or_unsafe_fields(runtime):
    client, db, admin, user, actor, _ = runtime
    assert save(client, {}, value=preferences()).status_code == 401
    assert save(client, user, value=preferences()).status_code == 403
    for changes in ({"navigation": "external"}, {"css": "body {display:none}"},
                    {"header_background_color": "url(https://bad.test)"},
                    {"header_style": "saved", "header_background_color": "#ffffff"}):
        value = {**preferences(), **changes}
        assert save(client, admin, value=value).status_code == 422
    assert not list(db.scalars(select(Settings)))
    actor.is_blocked = True; db.commit()
    assert save(client, admin, value=preferences()).status_code == 401


@pytest.mark.parametrize("value", ["bad json", '{"css":"bad"}', "x" * 2049])
def test_corrupt_customization_cannot_break_public_appearance(runtime, value):
    client, db, _, _, _, _ = runtime
    db.add(Settings(key=customization_key(None), value=value)); db.commit()
    assert client.get(f"{BASE}/appearance").json() == {"theme": None}


def test_v2_palette_overrides_persist_independently_without_rewriting_theme(runtime):
    client, db, admin, _, _, _ = runtime
    digest = install_v2(client, admin)
    client.post(f"{BASE}/selection", headers=admin, json={"sha256": digest})
    package = db.scalar(select(ModulePackage).where(ModulePackage.sha256 == digest))
    before = Path(package.file_path).read_bytes()
    original = client.get(f"{BASE}/appearance").json()["theme"]
    value = preferences(colors={"light": {"border": "#123456"}, "dark": {"border": "#ABCDEF"}})
    assert save(client, admin, digest, value).status_code == 200
    db.expire_all()
    result = client.get(f"{BASE}/appearance").json()
    assert result["customization"] == value
    assert result["theme"] == original
    assert Path(package.file_path).read_bytes() == before
    client.post(f"{BASE}/selection", headers=admin, json={"sha256": None})
    assert "customization" not in client.get(f"{BASE}/appearance").json()
    client.post(f"{BASE}/selection", headers=admin, json={"sha256": digest})
    assert client.get(f"{BASE}/appearance").json()["customization"] == value
    assert save(client, admin, digest).status_code == 200
    assert "customization" not in client.get(f"{BASE}/appearance").json()


def test_legacy_theme_only_accepts_its_supported_color_tokens(runtime):
    client, _, admin, _, _, _ = runtime
    digest = upload(client, admin).json()["sha256"]
    client.post(f"{BASE}/packages/{digest}/enable", headers=admin)
    client.post(f"{BASE}/selection", headers=admin, json={"sha256": digest})
    value = preferences(colors={"light": {"accent": "#123456"}, "dark": {"canvas": "#101010"}})
    assert save(client, admin, digest, value).json()["customization"] == value
    assert save(client, admin, digest, preferences(colors={"light": {"focus": "#123456"}})).status_code == 422
    client.post(f"{BASE}/selection", headers=admin, json={"sha256": None})
    assert save(client, admin, value=value).status_code == 200


def test_builtin_uses_the_v2_palette_contract_and_preserves_retired_settings(runtime):
    client, db, admin, user, _, _ = runtime
    retired = Settings(key="light_body_bg", value="#ABCDEF")
    db.add(retired); db.commit()
    value = preferences(colors={"light": {"border": "#123456"}, "dark": {"border": "#ABCDEF"}})
    assert save(client, user, value=value).status_code == 403
    assert save(client, admin, value=value).json() == {"theme": None, "customization": value}
    assert client.get(f"{BASE}/preview", headers=admin).json()["customization"] == value
    for colors in ({"light": {"text": "#ffffff"}}, {"dark": {"focus": "#15191f"}},
                   {"light": {"border": "url(https://bad.test)"}}):
        assert save(client, admin, value=preferences(colors=colors)).status_code == 422
        assert client.get(f"{BASE}/appearance").json()["customization"] == value
    assert save(client, admin).status_code == 200
    db.expire_all()
    assert db.get(Settings, retired.id).value == "#ABCDEF"


def test_palette_validation_and_existing_admin_boundary(runtime):
    client, db, admin, user, _, _ = runtime
    digest = install_v2(client, admin)
    client.post(f"{BASE}/selection", headers=admin, json={"sha256": digest})
    valid = preferences(colors={"dark": {"border": "#ABCDEF"}})
    assert save(client, {}, digest, valid).status_code == 401
    assert save(client, user, digest, valid).status_code == 403
    for colors in ({}, {"light": {}}, {"sepia": {"border": "#123456"}},
                   {"light": {"css": "#123456"}}, {"light": {"border": "url(https://bad.test)"}},
                   {"light": {"text": "#ffffff"}}, {"dark": {"accent_text": "#57ddc2"}},
                   {"light": {"border": ["#123456"]}}):
        assert save(client, admin, digest, preferences(colors=colors)).status_code == 422
    assert not list(db.scalars(select(Settings)))


def test_restored_unreadable_palette_is_ignored_without_losing_the_theme(runtime):
    client, db, admin, _, _, _ = runtime
    digest = install_v2(client, admin)
    client.post(f"{BASE}/selection", headers=admin, json={"sha256": digest})
    db.add(Settings(key=customization_key(digest), value=json.dumps(preferences(colors={"light": {"text": "#ffffff"}}))))
    db.commit()
    result = client.get(f"{BASE}/appearance").json()
    assert result["theme"]["theme_extension_version"] == 2
    assert "customization" not in result


def test_menu_layout_roundtrip_and_existing_admin_boundary(runtime):
    client, db, admin, user, _, _ = runtime
    menus = [Menu(name="Main", items=[], is_active=True), Menu(name="Footer", items=[], is_active=False)]
    db.add_all(menus); db.commit()
    layout = {"placements": [{"menu_id": menus[0].id, "location": "primary"},
                             {"menu_id": menus[1].id, "location": "footer"}],
              "sticky": {"header": True, "sidebar": True, "footer": False}}
    value = preferences(menu_layout=layout)
    assert save(client, {}, value=value).status_code == 401
    assert save(client, user, value=value).status_code == 403
    assert save(client, admin, value=value).json()["customization"] == value
    assert client.get(f"{BASE}/appearance").json()["customization"] == value
    db.expire_all()
    assert [(menu.name, menu.items, menu.is_active) for menu in menus] == [("Main", [], True), ("Footer", [], False)]
    # Deleting a configured menu does not activate a different one or lose colors.
    db.delete(menus[1]); db.commit()
    assert client.get(f"{BASE}/appearance").json()["customization"] == value
    assert save(client, admin, value=value).status_code == 409
    assert client.get(f"{BASE}/appearance").json()["customization"] == value
    layout["placements"] = []
    assert save(client, admin, value=preferences(menu_layout=layout)).status_code == 200


@pytest.mark.parametrize("layout", [
    {"sticky": {"header": "true", "sidebar": False, "footer": False}},
    {"sticky": {"header": True}},
    {"sticky": {"header": True, "sidebar": False, "footer": False}, "css": "position:fixed"},
    *[{"sticky": {"header": False, "sidebar": False, "footer": False}, "placements": placements}
      for placements in (None, [{"menu_id": True, "location": "header"}],
                         [{"menu_id": 1, "location": "external"}],
                         [{"menu_id": 1, "location": "header"}, {"menu_id": 1, "location": "footer"}],
                         [{"menu_id": i, "location": "primary"} for i in range(1, 18)])],
])
def test_invalid_menu_layout_is_rejected_without_mutating_saved_settings(runtime, layout):
    client, _, admin, _, _, _ = runtime
    value = preferences()
    assert save(client, admin, value=value).status_code == 200
    assert save(client, admin, value=preferences(menu_layout=layout)).status_code == 422
    assert client.get(f"{BASE}/appearance").json()["customization"] == value


def test_sticky_only_preferences_keep_the_automatic_menu_and_empty_is_explicit(runtime):
    client, _, admin, _, _, _ = runtime
    for layout in ({"sticky": {"header": False, "sidebar": True, "footer": False}},
                   {"sticky": {"header": False, "sidebar": False, "footer": True}, "placements": []}):
        value = preferences(menu_layout=layout)
        assert save(client, admin, value=value).json()["customization"] == value
        assert client.get(f"{BASE}/appearance").json()["customization"] == value
