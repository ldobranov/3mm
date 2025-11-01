from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
import os

# Environment-driven configuration
SECRET_KEY = os.getenv('JWT_SECRET', 'dev-insecure-secret')
ALGORITHM = os.getenv('JWT_ALG', 'HS256')
try:
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('JWT_ACCESS_MINUTES', '15'))
except ValueError:
    ACCESS_TOKEN_EXPIRE_MINUTES = 15

# Fail fast in production if secret is not set properly
if os.getenv('ENV') == 'production' and (not SECRET_KEY or SECRET_KEY == 'dev-insecure-secret'):
    raise RuntimeError('JWT_SECRET must be set in production')


def create_access_token(subject: str, extra_claims: dict | None = None, expires_delta: timedelta | None = None) -> str:
    now = datetime.now(timezone.utc)
    exp = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        # allow small leeway to tolerate minor clock skew
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], leeway=10)
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

# Backward-compatibility alias for legacy imports
def decode_jwt(token: str) -> dict:
    return decode_token(token)


def verify_jwt_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
