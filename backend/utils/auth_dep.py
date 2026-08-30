"""Authentication dependencies for FastAPI routes."""

from typing import Optional
from fastapi import Header, HTTPException, Request, Depends
from backend.utils.jwt_utils import decode_token
from backend.db.user import User
from backend.utils.db_utils import get_db
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)


def try_get_claims(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """
    Optional auth dependency. Returns claims if valid token present, None otherwise.
    Never raises - used for endpoints that support both anonymous and authenticated access.
    """

    if not authorization or not authorization.lower().startswith("bearer "):
        logger.info("No valid authorization header found")
        return None

    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = decode_token(token)
        return claims
    except Exception as e:
        logger.warning(f"Failed to decode token: {e}")
        return None


def require_user(authorization: Optional[str] = Header(None)) -> dict:
    """
    Required auth dependency. Raises 401 if no valid token.
    Used for endpoints that require authentication.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401, detail="Authorization header missing or invalid format"
        )
    token = authorization.split(" ", 1)[1].strip()
    claims = decode_token(token)  # raises HTTPException on invalid/expired
    if claims.get("token_type", "user") != "user":
        raise HTTPException(status_code=401, detail="A normal user token is required")
    return claims


def require_admin(
    claims: dict = Depends(require_user), db: Session = Depends(get_db)
) -> User:
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
