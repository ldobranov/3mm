"""New WP4 executors/build provenance must be present before target activation."""

import json
from pathlib import Path

import pytest

from deployment.deployment_contract import DeploymentContractError, validate_deployment_contract


WP4_FILES = (
    'backend/services/application_checkpoints.py',
    'backend/services/application_identity_read.py',
    'backend/services/application_peer_read.py',
    'backend/services/application_status_read.py',
    'backend/services/compiled_ui.py',
    'backend/services/compiled_ui_provenance.py',
    'backend/services/installation_peer_listing.py',
    'backend/services/installation_peer_read_sources.py',
    'backend/services/installation_status_binding.py',
    'frontend/compiler/compile-ui-extension.mjs',
    'three_mm_protocol/application_peer_read.py',
)


@pytest.mark.parametrize('missing', WP4_FILES)
def test_incomplete_wp4_release_is_rejected_by_target_contract(missing):
    root = Path(__file__).resolve().parents[2]
    raw = (root / 'deployment/deployment-contract.json').read_bytes()
    required = set(json.loads(raw)['required_files'])
    assert set(WP4_FILES) <= required
    assert all((root / item).is_file() for item in WP4_FILES)
    assert validate_deployment_contract(raw, required).schema_version == 2
    with pytest.raises(DeploymentContractError, match='incomplete'):
        validate_deployment_contract(raw, required - {missing})
