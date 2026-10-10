"""Cooperative SDK guard; not protection against native Python bypasses."""

from contextvars import ContextVar

relational_transaction_active: ContextVar[bool] = ContextVar(
    "three_mm_relational_transaction_active", default=False
)


def require_outside_relational_transaction() -> None:
    if relational_transaction_active.get():
        raise RuntimeError(
            "Platform calls are forbidden inside a scoped relational transaction"
        )
