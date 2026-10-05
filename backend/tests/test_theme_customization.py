"""Saved UI controls are scoped, bounded, audited and independent of ZIP/branding."""

import json
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.db.audit_log import AuditLog
from backend.db.module import ModulePackage
from backend.db.settings import Settings
from backend.services.theme_customization import customization_key
from backend.tests.test_theme_extension_lifecycle import BASE, runtime, upload


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
