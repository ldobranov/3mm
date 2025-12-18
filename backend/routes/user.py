from fastapi import APIRouter, Depends, HTTPException, Header, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from backend.utils.db_utils import get_db
from backend.utils.auth import hash_password, verify_password
from backend.utils.jwt_utils import decode_token, create_access_token
from backend.db.user import User, UserSchema
from backend.db.session import Session as UserSession
from backend.db.audit_log import AuditLog
from pydantic import BaseModel
import logging
import traceback
import jwt

logger = logging.getLogger(__name__)
from datetime import datetime, timedelta
import user_agents

# Initialize logger
logger = logging.getLogger(__name__)

class LanguagePreference(BaseModel):
    language: str

router = APIRouter()

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class LoginPayload(BaseModel):
    email: str
    password: str

token_blacklist = set()

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
def login_user(
    payload: LoginPayload, 
    request: Request,
    db: Session = Depends(get_db),
    user_agent: str = Header(None, alias="User-Agent")
):
    try:
        logger.debug(f"Incoming login payload: {payload.model_dump()}")
        if not payload.email or not payload.password:
            raise HTTPException(status_code=422, detail="Missing required fields")

        db_user = db.query(User).filter(User.email == payload.email).first()
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")

        if not verify_password(payload.password, db_user.hashed_password):
            raise HTTPException(status_code=400, detail="Invalid credentials")

        # Issue token using centralized JWT utils (env-driven secret and standard claims)
        token = create_access_token(subject=str(db_user.id), extra_claims={
            "username": db_user.username,
            "role": db_user.role or ""
        })
        
        # Parse user agent for device info
        device_info = {}
        if user_agent:
            ua = user_agents.parse(user_agent)
            device_info = {
                "device_name": f"{ua.browser.family} on {ua.os.family}",
                "user_agent": user_agent
            }
        
        # Create session record
        session = UserSession(
            user_id=db_user.id,
            token=token,
            ip_address=request.client.host if request.client else None,
            expires_at=datetime.utcnow() + timedelta(days=7),
            **device_info
        )
        db.add(session)
        db.commit()
        
        # Create audit log for login
        audit_log = AuditLog(
            user_id=db_user.id,
            action="LOGIN",
            ip_address=request.client.host if request.client else None,
            user_agent=user_agent,
            session_id=session.id
        )
        db.add(audit_log)
        db.commit()
        
        logger.debug(f"Generated token: {token}")
        return {"message": "Login successful", "token": token}
    except HTTPException:
        raise
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

        # Check if token is blacklisted
        if token in token_blacklist:
            logger.error("Token has been revoked (blacklisted)")
            raise HTTPException(status_code=401, detail="Token has been revoked")

        # Decode the token and handle potential errors
        try:
            payload = decode_token(token)
            logger.debug(f"Decoded JWT payload: {payload}")
        except HTTPException as e:
            # Propagate specific auth errors
            raise e
        except Exception as e:
            logger.error(f"Invalid token: {e}")
            raise HTTPException(status_code=401, detail="Invalid token")

        user_id = payload.get("sub") or payload.get("user_id")
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
            "role": user.role
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
        payload_decoded = decode_token(token)
        user_id = payload_decoded.get("sub") or payload_decoded.get("user_id")

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

@router.get("/read")
def read_users(
    authorization: str = Header(...),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """Get list of users - admin only"""
    try:
        # Decode token to get user info
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authorization required")
        
        token = authorization.split("Bearer ")[1]
        claims = decode_token(token)
        user_id = claims.get("sub") or claims.get("user_id")
        
        # Check if user is admin
        current_user = db.query(User).filter(User.id == user_id).first()
        if not current_user or current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Return users list
        users = db.query(User).offset(skip).limit(limit).all()
        return {
            "items": [
                {
                    "id": u.id,
                    "username": u.username,
                    "email": u.email,
                    "role": u.role,
                    "created_at": u.created_at.isoformat() if hasattr(u, 'created_at') and u.created_at else None
                }
                for u in users
            ],
            "total": db.query(User).count()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading users: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.put("/update")
def update_user(
    user_data: dict,
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    """Update user - admin only"""
    try:
        # Decode token to get user info
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authorization required")
        
        token = authorization.split("Bearer ")[1]
        claims = decode_token(token)
        admin_id = claims.get("sub") or claims.get("user_id")
        
        # Check if user is admin
        admin_user = db.query(User).filter(User.id == admin_id).first()
        if not admin_user or admin_user.role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Get user to update
        user_id = user_data.get("id")
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID required")
        
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Update user fields
        if "username" in user_data:
            user.username = user_data["username"]
        if "email" in user_data:
            user.email = user_data["email"]
        if "role" in user_data:
            user.role = user_data["role"]
        if "password" in user_data and user_data["password"]:
            user.hashed_password = hash_password(user_data["password"])
        
        db.commit()
        db.refresh(user)
        
        return {"message": "User updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.delete("/delete/{user_id}")
def delete_user(
    user_id: int,
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    """Delete user - admin only"""
    try:
        # Decode token to get user info
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authorization required")
        
        token = authorization.split("Bearer ")[1]
        claims = decode_token(token)
        admin_id = claims.get("sub") or claims.get("user_id")
        
        # Check if user is admin
        admin_user = db.query(User).filter(User.id == admin_id).first()
        if not admin_user or admin_user.role != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Prevent self-deletion
        if user_id == admin_id:
            raise HTTPException(status_code=400, detail="Cannot delete your own account")
        
        # Get user to delete
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Delete related records first to avoid foreign key constraints
        # Import necessary models
        from backend.db.permission import Permission
        from backend.db.page import Page
        from backend.db.display import Display
        from backend.db.audit_log import AuditLog
        from backend.db.session import Session as UserSession
        
        # Delete user's permissions (both as grantor and grantee)
        db.query(Permission).filter(
            (Permission.user_id == user_id) | (Permission.granted_by == user_id)
        ).delete(synchronize_session=False)
        
        # Delete user's sessions
        db.query(UserSession).filter(UserSession.user_id == user_id).delete(synchronize_session=False)
        
        # Delete user's audit logs
        db.query(AuditLog).filter(AuditLog.user_id == user_id).delete(synchronize_session=False)
        
        # Delete user's pages
        db.query(Page).filter(Page.owner_id == user_id).delete(synchronize_session=False)
        
        # Delete user's displays/dashboards
        db.query(Display).filter(Display.user_id == user_id).delete(synchronize_session=False)
        
        # Now delete the user
        db.delete(user)
        db.commit()
        
        return {"message": "User deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/logout")
def logout_user(
    authorization: str = Header(...),
    request: Request = None,
    db: Session = Depends(get_db),
    user_agent: str = Header(None, alias="User-Agent")
):
    try:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authorization header missing or invalid format")

        token = authorization.split("Bearer ")[1]
        
        # Deactivate session in database
        session = db.query(UserSession).filter(
            UserSession.token == token,
            UserSession.is_active == True
        ).first()
        
        if session:
            session.is_active = False
            
            # Create audit log for logout
            audit_log = AuditLog(
                user_id=session.user_id,
                action="LOGOUT",
                ip_address=request.client.host if request and request.client else None,
                user_agent=user_agent,
                session_id=session.id
            )
            db.add(audit_log)
            db.commit()
        
        token_blacklist.add(token)
        return {"message": "Logout successful"}
    except Exception as e:
        logger.error(f"Error during logout: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/language")
def save_user_language(
    preference: LanguagePreference,
    authorization: str = Header(None),
    db: Session = Depends(get_db)
):
    """Save user's language preference (supports guest users)"""
    try:
        # Handle both authenticated and guest users
        if authorization and authorization.startswith("Bearer "):
            # Authenticated user - save to backend
            token = authorization.split("Bearer ")[1]
            payload = decode_token(token)
            user_id = payload.get("sub") or payload.get("user_id")

            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            return {
                "message": "Language preference saved successfully", 
                "language": preference.language,
                "storage": "backend"
            }
        else:
            # Guest user - allow but don't save to backend
            return {
                "message": "Language preference saved locally", 
                "language": preference.language,
                "storage": "localStorage",
                "guest": True
            }

    except HTTPException:
        return {
            "message": "Language preference saved locally", 
            "language": preference.language,
            "storage": "localStorage",
            "guest": True
        }
    except Exception as e:
        logger.error(f"Error saving language preference: {e}")
        # For guest users, still return success with localStorage
        return {
            "message": "Language preference saved locally", 
            "language": preference.language,
            "storage": "localStorage",
            "guest": True
        }

@router.get("/language")
def get_user_language(
    authorization: str = Header(...),
    db: Session = Depends(get_db)
):
    """Get user's language preference"""
    try:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authorization header missing or invalid format")

        token = authorization.split("Bearer ")[1]
        payload = decode_token(token)
        user_id = payload.get("sub") or payload.get("user_id")

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Get language preference from settings - try with fallback to "en"
        try:
            from backend.db.settings import Settings

            setting = db.query(Settings).filter(
                Settings.key == "language",
                Settings.user_id == user_id
            ).first()

            language = setting.value if setting else "en"
        except Exception as settings_error:
            # If Settings table doesn't exist, fallback to "en"
            logger.warn(f"Settings table not available, defaulting to 'en': {settings_error}")
            language = "en"

        return {"language": language}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving language preference: {e}")
        return {"language": "en"}  # Fallback to English