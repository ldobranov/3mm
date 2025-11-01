from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session
from backend.db.menu import Menu, MenuCreateSchema
from backend.db.page import Page
from backend.db.settings import Settings
from backend.db.user import User, UserSchema
from backend.db.role import Role
from backend.utils.db_utils import get_db
from backend.utils.crud import create_crud_routes
from backend.utils.jwt_utils import decode_token
from backend.utils.auth_dep import require_user
from pydantic import BaseModel, field_validator, ConfigDict
import json

router = APIRouter()

# Dependency to restrict access to admin users for certain routers
from typing import Optional

def admin_required(claims: dict = Depends(require_user), db: Session = Depends(get_db)):
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: admin role required")
    
    return user

# Schema definitions
class MenuUpdate(BaseModel):
    id: int
    name: str
    items: list | None = []
    is_active: bool = False

    model_config = {
        "from_attributes": True
    }

class PageCreate(BaseModel):
    title: str
    content: str
    slug: str | None = None
    is_public: bool = True
    allowed_roles: list[str] = []

    model_config = ConfigDict(from_attributes=True)

class PageUpdate(BaseModel):
    id: int  # Used for updates
    title: str
    content: str
    slug: str | None = None
    is_public: bool | None = None
    allowed_roles: list[str] | None = None

    model_config = ConfigDict(from_attributes=True)

class SettingsUpdateSchema(BaseModel):
    id: int
    key: str
    value: str | None = None
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)

class SettingsCreateSchema(BaseModel):
    key: str
    value: str | None = None
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)

class UserCreate(BaseModel):
    username: str
    email: str
    hashed_password: str

class RoleCreate(BaseModel):
    name: str

# Consolidated dynamic CRUD route registration
def register_crud_routes():
    # Menu CRUD routes - OK to keep
    menu_crud_router = create_crud_routes(Menu, "menu", MenuCreateSchema, MenuUpdate, MenuUpdate)
    
    # Don't register page CRUD routes here - we have custom page routes in page_routes.py
    # page_crud_router = create_crud_routes(Page, "pages", PageCreate, PageUpdate)
    
    # Settings CRUD routes - we'll handle these with custom routes for proper access control
    # settings_crud_router = create_crud_routes(Settings, "settings", SettingsCreateSchema, SettingsUpdateSchema)
    
    # Don't register user CRUD routes here - we have custom user routes in user.py
    # that handle authentication, registration, profile management etc.
    # user_crud_router = create_crud_routes(User, "user", UserSchema)
    
    # Role CRUD routes - add admin dependency since only admins should manage roles
    role_crud_router = create_crud_routes(Role, "role", RoleCreate)

    router.include_router(menu_crud_router)
    # Don't include page router here - it's handled by page_routes.py
    # router.include_router(page_crud_router, dependencies=[Depends(admin_required)])
    
    # Don't include settings CRUD router - we'll add custom routes
    # router.include_router(settings_crud_router, dependencies=[Depends(admin_required)])
    
    # Don't include user CRUD router - handled by custom user routes
    # router.include_router(user_crud_router)
    
    # Roles should be admin-only
    router.include_router(role_crud_router, dependencies=[Depends(admin_required)])

# Call the function to register routes during application initialization
register_crud_routes()

# Custom settings routes with proper access control

@router.get("/settings/read")
def read_settings(db: Session = Depends(get_db), skip: int = 0, limit: int = 10000):
    """Get settings - public endpoint for reading settings like site title"""
    try:
        settings = db.query(Settings).offset(skip).limit(limit).all()
        return {"items": settings}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading settings: {e}")

@router.post("/settings/create")
def create_setting(setting: SettingsCreateSchema, user = Depends(require_user), db: Session = Depends(get_db)):
    """Create a new setting - admin only"""
    try:
        # Check if setting with this key already exists
        existing = db.query(Settings).filter(Settings.key == setting.key).first()
        if existing:
            # Update existing setting instead of creating new one
            existing.value = setting.value
            existing.description = setting.description
            db.commit()
            db.refresh(existing)
            return existing

        db_setting = Settings(**setting.model_dump())
        db.add(db_setting)
        db.commit()
        db.refresh(db_setting)
        return db_setting
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating setting: {e}")

@router.put("/settings/update")
def update_settings(settings: SettingsUpdateSchema, user = Depends(require_user), db: Session = Depends(get_db)):
    """Update settings - admin only"""
    try:
        db_settings = db.query(Settings).filter(Settings.id == settings.id).first()
        if not db_settings:
            raise HTTPException(status_code=404, detail="Settings not found")

        db_settings.key = settings.key
        db_settings.value = settings.value
        db_settings.description = settings.description

        db.commit()
        db.refresh(db_settings)
        return db_settings
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {e}")

@router.delete("/settings/delete/{setting_id}")
def delete_setting(setting_id: int, user = Depends(require_user), db: Session = Depends(get_db)):
    """Delete a setting - admin only"""
    try:
        db_setting = db.query(Settings).filter(Settings.id == setting_id).first()
        if not db_setting:
            raise HTTPException(status_code=404, detail="Setting not found")
        
        db.delete(db_setting)
        db.commit()
        return {"message": "Setting deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting setting: {e}")

@router.get("/settings")
def handle_settings():
    """Placeholder implementation for handle_settings."""
    return {"message": "Settings endpoint is under construction."}
