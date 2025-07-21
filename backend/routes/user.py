from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from backend.utils.db_utils import get_db
from backend.utils.auth import hash_password, verify_password
from backend.utils.jwt_utils import decode_jwt
from backend.db.user import User, UserSchema
from pydantic import BaseModel
import logging
import traceback
import jwt
from datetime import datetime, timedelta

router = APIRouter()

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class LoginPayload(BaseModel):
    email: str
    password: str

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("route_debug")

@router.post("/register")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    try:
        logger.debug(f"Registering user: {user}")
        if not user.username or not user.email or not user.password:
            raise HTTPException(status_code=422, detail="Missing required fields")

        hashed_password = hash_password(user.password)
        new_user = User(username=user.username, email=user.email, hashed_password=hashed_password)
        db.add(new_user)
        db.commit()
        logger.debug(f"User registered: {new_user}, ID: {new_user.id}")
        return {"message": "User registered successfully"}
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Username or email already exists")
    except Exception as e:
        logger.error(f"Error during user registration: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/login")
def login_user(payload: LoginPayload, db: Session = Depends(get_db)):
    try:
        logger.debug(f"Incoming login payload: {payload.model_dump()}")
        if not payload.email or not payload.password:
            raise HTTPException(status_code=422, detail="Missing required fields")

        db_user = db.query(User).filter(User.email == payload.email).first()
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")

        if not verify_password(payload.password, db_user.hashed_password):
            raise HTTPException(status_code=400, detail="Invalid credentials")

        SECRET_KEY = "your_secret_key"  # Ensure this matches the one in jwt_utils.py
        token = jwt.encode({
            "user_id": db_user.id,
            "exp": datetime.utcnow() + timedelta(hours=1)
        }, SECRET_KEY, algorithm="HS256")

        logger.debug(f"Generated token: {token}")
        return {"message": "Login successful", "token": token}
    except Exception as e:
        logger.error(f"Error during login: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.get("/profile")
def fetch_user_profile(authorization: str = Header(...), db: Session = Depends(get_db)):
    try:
        logger.debug(f"Incoming request headers: {authorization}")
        logger.debug(f"Authorization header received: {authorization}")

        # Validate Authorization header format
        if not authorization or not authorization.startswith("Bearer "):
            logger.error("Authorization header missing or invalid format")
            raise HTTPException(status_code=401, detail="Authorization header missing or invalid format")

        # Extract and log the token
        token = authorization.split("Bearer ")[1]
        logger.debug(f"Extracted token: {token}")

        # Decode the token and handle potential errors
        try:
            payload = decode_jwt(token)
            logger.debug(f"Decoded JWT payload: {payload}")
        except jwt.ExpiredSignatureError:
            logger.error("Token has expired")
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.InvalidTokenError as e:
            logger.error(f"Invalid token: {e}")
            raise HTTPException(status_code=401, detail="Invalid token")

        user_id = payload.get("user_id")
        logger.debug(f"Decoded payload: {payload}, user_id: {user_id}")

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error("User not found")
            raise HTTPException(status_code=404, detail="User not found")

        logger.debug(f"Profile fetched: {user}")
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role  # Return role directly as a string
        }
    except ValueError as e:
        logger.error(f"JWT error: {e}")
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=422, detail="Unprocessable Entity")

@router.put("/profile/update")
def update_user_profile(payload: dict, authorization: str = Header(...), db: Session = Depends(get_db)):
    try:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authorization header missing or invalid format")

        token = authorization.split("Bearer ")[1]
        payload_decoded = decode_jwt(token)
        user_id = payload_decoded.get("user_id")

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if "username" in payload:
            user.username = payload["username"]
        if "email" in payload:
            user.email = payload["email"]
        if "password" in payload:
            user.hashed_password = hash_password(payload["password"])

        db.commit()
        db.refresh(user)

        return {"message": "Profile updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating profile: {e}")

@router.post("/logout")
def logout_user(authorization: str = Header(...)):
    try:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authorization header missing or invalid format")

        token = authorization.split("Bearer ")[1]
        # Here you can implement token invalidation logic, such as adding the token to a blacklist.
        # For now, we'll just return a success message.

        return {"message": "Logout successful"}
    except Exception as e:
        logger.error(f"Error during logout: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")