# backend/schemas/extension.py
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

class ExtensionManifest(BaseModel):
    name: str
    version: str
    type: str  # 'widget', 'theme', 'backend-api', etc.
    description: Optional[str] = None
    author: Optional[str] = None
    dependencies: Optional[Dict[str, str]] = None  # version constraints
    entry_point: Optional[str] = None  # for backend extensions
    backend_entry: Optional[str] = None  # for backend extensions
    frontend_entry: Optional[str] = None  # for frontend extensions
    frontend_editor: Optional[str] = None  # for widget editor extensions
    config_schema: Optional[Dict[str, Any]] = None  # JSON schema for config
    permissions: Optional[list[str]] = None  # required permissions

class ExtensionCreate(BaseModel):
    file: bytes  # The uploaded extension file

class ExtensionUpdate(BaseModel):
    is_enabled: Optional[bool] = None

class ExtensionSchema(BaseModel):
    id: int
    user_id: int
    name: str
    type: str
    version: str
    description: Optional[str] = None
    author: Optional[str] = None
    manifest: Dict[str, Any]
    status: str
    error_message: Optional[str] = None
    is_enabled: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True