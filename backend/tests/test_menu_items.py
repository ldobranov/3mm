import pytest
from fastapi import HTTPException

from backend.routes.settings import _validated_menu_items


def test_menu_items_accept_supported_audiences_and_legacy_items() -> None:
    items = [
        {"path": "/@demo/status", "label": {"en": "Status"}, "audience": "public"},
        {"path": "/dashboard", "label": {"en": "Dashboards"}},
    ]

    assert _validated_menu_items(items) is items


def test_menu_items_reject_unknown_audience() -> None:
    with pytest.raises(HTTPException) as exc:
        _validated_menu_items(
            [{"path": "/settings", "label": {"en": "Settings"}, "audience": "all"}]
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Menu item audience is invalid"
