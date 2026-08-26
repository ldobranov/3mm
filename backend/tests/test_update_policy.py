from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.config import UpdateCatalogSettings
from backend.services.system_updates import (
    CurrentRelease,
    UpdateCatalogError,
    UpdateCheckResponse,
)
from backend.services.update_policy import (
    SystemUpdateCheckManager,
    UpdatePolicyError,
    UpdatePolicyRequest,
    check_and_cache_update_catalog,
    ensure_apply_is_allowed,
    read_update_check_cache,
    read_update_policy_status,
    run_due_automatic_check,
    save_update_policy,
)


def settings(tmp_path: Path) -> UpdateCatalogSettings:
    return UpdateCatalogSettings(
        policy_file=tmp_path / "policy.json",
        check_cache_file=tmp_path / "check-cache.json",
    )


def catalog_response() -> UpdateCheckResponse:
    return UpdateCheckResponse(
        status="up_to_date",
        message="Current release is up to date",
        repository="ldobranov/3mm",
        repository_url="https://github.com/ldobranov/3mm",
        architecture="aarch64",
        current=CurrentRelease(
            release_id="v1.2.0",
            commit="a" * 40,
            version="1.2.0",
            metadata_available=True,
        ),
        update_available=False,
        checked_at=datetime(2026, 8, 26, 8, 0, tzinfo=UTC),
    )


def test_policy_is_persisted_and_reports_the_daily_window(tmp_path: Path) -> None:
    update_settings = settings(tmp_path)
    saved = save_update_policy(
        update_settings,
        UpdatePolicyRequest(
            channel="beta",
            automatic_checks_enabled=True,
            check_interval_hours=12,
            maintenance_window_enabled=True,
            maintenance_timezone="Europe/Sofia",
            maintenance_start="03:00",
            maintenance_duration_minutes=120,
        ),
    )

    inside = read_update_policy_status(
        update_settings, now=datetime(2026, 8, 26, 1, 30, tzinfo=UTC)
    )
    outside = read_update_policy_status(
        update_settings, now=datetime(2026, 8, 26, 8, 0, tzinfo=UTC)
    )

    assert saved.channel == "beta"
    assert inside.within_maintenance_window is True
    assert inside.current_window_ends_at == datetime(2026, 8, 26, 2, 0, tzinfo=UTC)
    assert outside.within_maintenance_window is False
    assert outside.next_window_starts_at == datetime(2026, 8, 27, 0, 0, tzinfo=UTC)


def test_outside_window_requires_a_separate_explicit_override(tmp_path: Path) -> None:
    update_settings = settings(tmp_path)
    save_update_policy(
        update_settings,
        UpdatePolicyRequest(
            maintenance_window_enabled=True,
            maintenance_timezone="UTC",
            maintenance_start="03:00",
            maintenance_duration_minutes=60,
        ),
    )
    now = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)

    with pytest.raises(UpdatePolicyError, match="explicit override"):
        ensure_apply_is_allowed(update_settings, maintenance_override=False, now=now)

    allowed = ensure_apply_is_allowed(
        update_settings, maintenance_override=True, now=now
    )
    assert allowed.within_maintenance_window is False


def test_successful_check_is_cached_until_the_configured_interval(
    tmp_path: Path,
) -> None:
    update_settings = settings(tmp_path)
    save_update_policy(
        update_settings,
        UpdatePolicyRequest(
            channel="beta", automatic_checks_enabled=True, check_interval_hours=6
        ),
    )
    now = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)
    calls: list[str] = []

    def checker(_settings, *, channel):
        calls.append(channel)
        return catalog_response()

    assert run_due_automatic_check(update_settings, checker=checker, now=now) is True
    assert (
        run_due_automatic_check(
            update_settings, checker=checker, now=now + timedelta(hours=1)
        )
        is False
    )

    cached = read_update_check_cache(update_settings)
    assert calls == ["beta"]
    assert cached is not None
    assert cached.result is not None
    assert cached.next_check_at == now + timedelta(hours=6)


def test_failed_checks_keep_the_last_result_and_back_off(tmp_path: Path) -> None:
    update_settings = settings(tmp_path)
    now = datetime(2026, 8, 26, 8, 0, tzinfo=UTC)
    check_and_cache_update_catalog(
        update_settings,
        channel="stable",
        checker=lambda *_args, **_kwargs: catalog_response(),
        now=now,
    )

    def unavailable(*_args, **_kwargs):
        raise UpdateCatalogError("Catalog unavailable")

    with pytest.raises(UpdateCatalogError):
        check_and_cache_update_catalog(
            update_settings,
            channel="stable",
            checker=unavailable,
            now=now + timedelta(hours=7),
        )

    cached = read_update_check_cache(update_settings)
    assert cached is not None
    assert cached.result is not None
    assert cached.consecutive_failures == 1
    assert cached.last_error == "Catalog unavailable"
    assert cached.next_check_at == now + timedelta(hours=7, minutes=15)


def test_background_check_manager_has_a_managed_lifecycle() -> None:
    async def scenario() -> None:
        manager = SystemUpdateCheckManager()
        await manager.start()
        first_task = manager._worker_task
        assert first_task is not None
        assert not first_task.done()
        await manager.start()
        assert manager._worker_task is first_task
        await manager.stop()
        assert manager._worker_task is None
        assert first_task.cancelled()

    asyncio.run(scenario())
