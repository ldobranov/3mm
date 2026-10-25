"""Fresh application install starts with explicit resource consent required."""
from sqlalchemy.orm import Session
from sqlalchemy import select
from backend.db.application_authority_grant import ApplicationAuthorityGrant as Grant, ApplicationNativeReview as Native
from backend.db.module import ApplicationExtensionInstallation as Installation
from backend.db.installation_peer import InstallationPeerOutbound
from backend.services.application_authority_management import lock_compatibility_admission
from backend.routes import application_extensions as routes
from backend.tests.test_application_lifecycle_authority import lifecycle, request
import pytest


def test_fresh_install_never_defaults_to_compatibility_or_creates_grants(lifecycle, monkeypatch):
    s = lifecycle
    instance = routes.application_instance_id(s.module_id)
    with Session(s.engine) as db, db.begin():
        db.get(Installation, 1).instance_id = instance
        db.get(InstallationPeerOutbound, "peer-keep").application_instance_id = instance
    assert request(s, "uninstalling").status_code == 200
    monkeypatch.setattr(routes.UpdateHelperClient, "activate_application_extension",
        lambda *_args: {**s.result, "instance_id": instance})
    result = request(s, "activating")
    assert result.status_code == 200, result.text
    with Session(s.engine) as db:
        installed = db.scalar(select(Installation))
        assert installed.enabled and installed.status == "active"
        assert installed.authority_mode == "review_required"
        assert db.get(Grant, installed.id) is None
        assert db.scalar(select(Native.review_id)) is None
        with pytest.raises(ValueError, match="changed"):
            lock_compatibility_admission(db, installed, required=True)
