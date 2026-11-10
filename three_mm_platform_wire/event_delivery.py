"""Finite local event handoff budgets, shared by Core and the I/O Runtime."""
from pathlib import Path
import time


CLAIM_SECONDS = 10
DISPATCH_SECONDS = 3
COMPLETION_SECONDS = 4
LEASE_MS = 40_000


def boot_clock():
    """Same kernel boot/time domain as Core's durable event lease."""
    return (Path('/proc/sys/kernel/random/boot_id').read_text(encoding='ascii').strip(),
            int(time.clock_gettime(time.CLOCK_BOOTTIME) * 1000))


def lease_remaining(boot_id, deadline_ms):
    if (type(boot_id) is not str or type(deadline_ms) is not int
            or deadline_ms <= 0):
        raise ValueError('Invalid event handoff lease')
    current_boot, now = boot_clock()
    remaining = (deadline_ms - now) / 1000
    if boot_id != current_boot or not 0 < remaining <= LEASE_MS / 1000:
        raise ValueError('Event handoff lease is unavailable or expired')
    return remaining
