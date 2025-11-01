from fastapi import APIRouter, Depends, HTTPException, Request
from datetime import datetime, timezone
from backend.utils.jwt_utils import decode_token, create_access_token

router = APIRouter()

@router.post("/user/refresh")
async def refresh_access_token(request: Request):
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    raw_token = auth.split(" ", 1)[1].strip()

    # Validate existing token
    claims = decode_token(raw_token)

    # Optional: only refresh near expiry (disabled for now)
    # now = int(datetime.now(timezone.utc).timestamp())
    # exp = int(claims.get("exp", 0))
    # if exp - now > 10 * 60:
    #     raise HTTPException(status_code=400, detail="Too early to refresh")

    subject = str(claims.get("sub") or claims.get("user_id") or "")
    if not subject:
        raise HTTPException(status_code=401, detail="Invalid subject")

    extra = {k: v for k, v in claims.items() if k not in ("sub", "iat", "exp")}
    new_token = create_access_token(subject=subject, extra_claims=extra)
    return {"token": new_token}
