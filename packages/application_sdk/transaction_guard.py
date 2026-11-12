"""Cooperative SDK guard; not protection against native Python bypasses."""

from contextvars import ContextVar
from contextlib import contextmanager
import threading

_operation = threading.local()


@contextmanager
def host_operation():
    previous = getattr(_operation, "active", False)
    _operation.active = True
    try: yield
    finally: _operation.active = previous


def require_delegation_worker():
    if getattr(_operation, "active", False):
        raise RuntimeError("Delegations execute from a worker after the current handler returns")

relational_transaction_active: ContextVar[bool] = ContextVar(
    "three_mm_relational_transaction_active", default=False
)


def require_outside_relational_transaction() -> None:
    if relational_transaction_active.get():
        raise RuntimeError(
            "Platform calls are forbidden inside a scoped relational transaction"
        )
