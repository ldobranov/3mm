"""Bounded cold-start budget for local ARMv6 application hosts."""

import platform


def application_startup_budget(declared_seconds: int) -> int:
    return max(declared_seconds, 120) if platform.machine() == "armv6l" else declared_seconds


def application_setup_budget(default_seconds: int) -> int:
    return max(default_seconds, 120) if platform.machine() == "armv6l" else default_seconds
