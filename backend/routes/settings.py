from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from backend.db.menu import Menu, Page, MenuCreateSchema
from backend.db.settings import Settings
from backend.db.user import User, UserSchema
from backend.db.role import Role
from backend.db.extension import Extension
from backend.utils.db_utils import get_db
from backend.utils.crud import create_crud_routes
from pydantic import BaseModel, field_validator, ConfigDict
import json

router = APIRouter()

# Schema definitions
class MenuUpdate(BaseModel):
    id: int
    name: str
    path: str
    order: int

    model_config = {
        "from_attributes": True
    }

class PageCreate(BaseModel):
    title: str
    content: str

    model_config = ConfigDict(from_attributes=True)

class PageUpdate(BaseModel):
    id: int  # Used for updates
    title: str
    content: str

    model_config = ConfigDict(from_attributes=True)

class SettingsSchema(BaseModel):
    id: int
    name: str
    language: str
    data: dict

    model_config = ConfigDict(from_attributes=True)

    @field_validator("data")
    def validate_data(cls, value):
        if not isinstance(value, dict):
            raise ValueError("data must be a dictionary")
        return value

class UserCreate(BaseModel):
    username: str
    email: str
    hashed_password: str

class RoleCreate(BaseModel):
    name: str

# Consolidated dynamic CRUD route registration
def register_crud_routes():
    menu_crud_router = create_crud_routes(Menu, "menu", MenuCreateSchema, MenuUpdate, MenuUpdate)
    page_crud_router = create_crud_routes(Page, "pages", PageCreate, PageUpdate)
    settings_crud_router = create_crud_routes(Settings, "settings", SettingsSchema)
    user_crud_router = create_crud_routes(User, "user", UserSchema)
    role_crud_router = create_crud_routes(Role, "role", RoleCreate)
    extension_crud_router = create_crud_routes(Extension, "extensions", Extension)

    router.include_router(menu_crud_router)
    router.include_router(page_crud_router)
    router.include_router(settings_crud_router)
    router.include_router(user_crud_router)
    router.include_router(role_crud_router)
    router.include_router(extension_crud_router)

# Call the function to register routes during application initialization
register_crud_routes()

# Ensure `/settings/update` uses the correct schema
@router.put("/settings/update")
def update_settings(settings: SettingsSchema, db: Session = Depends(get_db)):
    try:
        db_settings = db.query(Settings).filter(Settings.id == settings.id).first()
        if not db_settings:
            raise HTTPException(status_code=404, detail="Settings not found")

        db_settings.name = settings.name
        db_settings.language = settings.language
        db_settings.data = settings.data

        db.commit()
        return {"message": "Settings updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {e}")
