"""Authentication dependencies for FastAPI routes."""
from typing import Optional
from fastapi import Header, HTTPException, Request, Depends
from backend.utils.jwt_utils import decode_token
import logging

logger = logging.getLogger(__name__)


def try_get_claims(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """
    Optional auth dependency. Returns claims if valid token present, None otherwise.
    Never raises - used for endpoints that support both anonymous and authenticated access.
    """
    logger.info(f"try_get_claims - Authorization header: {authorization[:50] if authorization else 'None'}")
    
    if not authorization or not authorization.lower().startswith("bearer "):
        logger.info("No valid authorization header found")
        return None
    
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = decode_token(token)
        logger.info(f"Token decoded successfully: user_id={claims.get('sub')}, role={claims.get('role')}")
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
        raise HTTPException(status_code=401, detail="Authorization header missing or invalid format")
    token = authorization.split(" ", 1)[1].strip()
    return decode_token(token)  # raises HTTPException on invalid/expired