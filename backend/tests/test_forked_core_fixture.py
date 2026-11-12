"""The process fixture must not inherit a vanished parent thread's route lock."""
import os

import pytest

from backend.tests.test_platform_runtime_process import (
    activate_identity_grant, checkpoint_app, core_stack, identity_app,
    managed_installed, source_installed, source_subject,
)


pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Actual forked Core fixture')


def test_forked_core_rebuilds_only_derived_router_caches(identity_app, monkeypatch):
    import backend.main as main
    from fastapi.routing import _IncludedRouter

    branch = next(route for route in main.app.routes if isinstance(route, _IncludedRouter))
    monkeypatch.setattr(branch, '_effective_candidates_version', None)
    activate_identity_grant(identity_app)
    # Model a different parent thread holding FastAPI's private cache mutex at
    # fork. Only the child copy may be replaced; the endpoint/router objects and
    # this parent lock must survive unchanged.
    original_router, include_context = branch.original_router, branch.include_context
    with branch._effective_routes_lock:
        with core_stack(identity_app, monkeypatch) as stack:
            assert stack.http()[0] == 200
            assert stack.http('/settings/read')[0] == 200
        assert branch._effective_routes_lock.locked()
        assert branch.original_router is original_router
        assert branch.include_context is include_context
        assert branch in main.app.routes
