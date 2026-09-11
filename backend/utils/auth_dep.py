"""Authentication dependencies for FastAPI routes."""

from typing import Optional
from fastapi import Header, HTTPException, Request, Depends
from backend.utils.jwt_utils import decode_token
from backend.db.user import User
from backend.db.session import UserSession
from datetime import datetime, timezone
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


def validate_user_claims(claims: dict, db: Session) -> User:
    if claims.get("token_type", "user") != "user":
        raise HTTPException(401, "A normal user token is required")
    try:
        user_id = int(claims.get("sub") or claims.get("user_id"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(401, "Invalid user subject") from exc
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(401, "User is unavailable")
    if user.is_blocked:
        raise HTTPException(401, "Account is blocked")
    if claims.get("token_version", 0) != user.token_version:
        raise HTTPException(401, "Session has been revoked")
    # Current login tokens carry sid; preserve existing legacy signed tokens.
    if "sid" in claims:
        sid = claims["sid"]
        if not isinstance(sid, int) or isinstance(sid, bool):
            raise HTTPException(401, "Invalid session")
        session = db.get(UserSession, sid)
        if session is None or session.user_id != user.id or not session.is_active:
            raise HTTPException(401, "Session is revoked or unavailable")
        if session.expires_at is not None:
            expires = session.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires <= datetime.now(timezone.utc):
                raise HTTPException(401, "Session expired")
    return user


def guard_user_session(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """Enforce revocation on legacy and dynamically registered HTTP routes too.

    Invalid/non-user credentials remain the responsibility of route-specific
    authentication. Expired signed tokens are checked here to support refresh.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return
    from backend.utils.jwt_utils import decode_token_for_refresh
    try:
        claims = decode_token_for_refresh(authorization.split(" ", 1)[1].strip())
    except HTTPException:
        return
    if claims.get("token_type", "user") == "user":
        validate_user_claims(claims, db)


def require_user(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)) -> dict:
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
    validate_user_claims(claims, db)
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
