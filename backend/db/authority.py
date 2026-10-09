"""Internal M20 metadata, not grants or a replacement command epoch."""

import secrets

from sqlalchemy import BigInteger, CheckConstraint, Column, Integer, String

from backend.db.base import Base


MAX_AUTHORITY_REVISION = 2**53 - 1


def new_authority_generation() -> str:
    return secrets.token_hex(16)


class CoreAuthorityGuard(Base):
    """Database serialization point for future participating authority writers."""

    __tablename__ = "core_authority_guard"
    singleton_id = Column(Integer, primary_key=True)
    generation = Column(String(32), nullable=False, default=new_authority_generation)
    revision = Column(BigInteger, nullable=False, default=1)
    __table_args__ = (
        CheckConstraint("singleton_id = 1", name="ck_authority_guard_singleton"),
        CheckConstraint(
            "length(generation) = 32", name="ck_authority_guard_generation"
        ),
        CheckConstraint(
            f"revision >= 1 AND revision <= {MAX_AUTHORITY_REVISION}",
            name="ck_authority_guard_revision",
        ),
    )
