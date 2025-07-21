import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

SECRET_KEY = "your_secret_key"

def decode_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except ExpiredSignatureError:
        raise ValueError("Token has expired")
    except InvalidTokenError:
        raise ValueError("Invalid token")
