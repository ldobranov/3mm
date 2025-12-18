from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session
from backend.db.universal_translation import Menu
# Define MenuCreateSchema inline to avoid import conflicts
from pydantic import BaseModel as PydanticBaseModel, ConfigDict as PydanticConfigDict
import os
import json

# Load config from root config.json
config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config.json')
with open(config_path, 'r') as f:
    app_config = json.load(f)

class MenuCreateSchema(PydanticBaseModel):
    name: str
    items: list | None = []
    is_active: bool = False

    model_config = PydanticConfigDict(from_attributes=True)
from backend.db.page import Page
from backend.db.settings import Settings
from backend.db.user import User, UserSchema
from backend.db.role import Role
from backend.utils.db_utils import get_db
from backend.utils.crud import create_crud_routes
from backend.utils.jwt_utils import decode_token
from backend.utils.auth_dep import require_user, try_get_claims
from backend.utils.i18n import set_language, get_current_language, i18n_manager
from pydantic import BaseModel, field_validator, ConfigDict
import json
import time
from urllib.parse import urlparse

router = APIRouter()

# Dependency to restrict access to admin users for certain routers
from typing import Optional, Dict, Any

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
    name: dict  # {"en": "Dashboard", "bg": "Табло"}
    items: list | None = []
    is_active: bool = False

    model_config = {
        "from_attributes": True
    }

    def get_localized_name(self, language: str = "bg") -> str:
        """Get the menu name in the specified language, with fallback"""
        if isinstance(self.name, dict):
            return self.name.get(language, self.name.get("bg", self.name.get("en", "")))
        return str(self.name) if self.name else ""

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
    language_code: str | None = None

    model_config = ConfigDict(from_attributes=True)

class SettingsCreateSchema(BaseModel):
    key: str
    value: str | None = None
    description: str | None = None
    language_code: str | None = None

    model_config = ConfigDict(from_attributes=True)

class SettingsSyncRequest(BaseModel):
    key: str
    values: dict  # {"en": "value1", "bg": "value2"}
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)

class FrontendConfigRequest(BaseModel):
    backend_url: str
    frontend_url: str | None = None
    description: str | None = "Frontend backend URL configuration"

    model_config = ConfigDict(from_attributes=True)

class UserCreate(BaseModel):
    username: str
    email: str
    hashed_password: str

class RoleCreate(BaseModel):
    name: str

# Consolidated dynamic CRUD route registration
def register_crud_routes():
    # Menu CRUD routes - use custom menu routes instead of generic CRUD
    # menu_crud_router = create_crud_routes(Menu, "menu", MenuCreateSchema, MenuUpdate, MenuUpdate)
    
    # Don't register page CRUD routes here - we have custom page routes in page_routes.py
    # page_crud_router = create_crud_routes(Page, "pages", PageCreate, PageUpdate)
    
    # Settings CRUD routes - we'll handle these with custom routes for proper access control
    # settings_crud_router = create_crud_routes(Settings, "settings", SettingsCreateSchema, SettingsUpdateSchema)
    
    # Don't register user CRUD routes here - we have custom user routes in user.py
    # that handle authentication, registration, profile management etc.
    # user_crud_router = create_crud_routes(User, "user", UserSchema)
    
    # Role CRUD routes - add admin dependency since only admins should manage roles
    role_crud_router = create_crud_routes(Role, "role", RoleCreate)

    # router.include_router(menu_crud_router)  # Disabled - using custom menu routes
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
def read_settings(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 10000,
    language: str = None,
    current_user: Optional[dict] = Depends(try_get_claims)
):
    """Get settings - includes global and user-specific settings"""
    try:
        user_id = current_user.get('user_id') if current_user else None

        # Try to use the language_code column (if it exists)
        try:
            query = db.query(Settings)

            # If language specified, prefer language-specific settings but include global ones
            if language:
                # First get all global settings (language_code IS NULL and user_id IS NULL)
                global_settings = query.filter(Settings.language_code.is_(None), Settings.user_id.is_(None)).all()

                # Then get user-specific global settings
                if user_id:
                    user_global_settings = query.filter(Settings.language_code.is_(None), Settings.user_id == user_id).all()
                else:
                    user_global_settings = []

                # Then get language-specific settings (global)
                lang_settings = query.filter(Settings.language_code == language, Settings.user_id.is_(None)).all()

                # Then get user-specific language settings
                if user_id:
                    user_lang_settings = query.filter(Settings.language_code == language, Settings.user_id == user_id).all()
                else:
                    user_lang_settings = []

                # Merge them: global -> user global -> lang -> user lang
                settings_dict = {}
                for setting in global_settings:
                    settings_dict[setting.key] = setting

                for setting in user_global_settings:
                    settings_dict[setting.key] = setting

                for setting in lang_settings:
                    settings_dict[setting.key] = setting

                for setting in user_lang_settings:
                    settings_dict[setting.key] = setting

                settings = list(settings_dict.values())
            else:
                # Get all settings for the user
                if user_id:
                    settings = query.filter(
                        (Settings.user_id.is_(None)) | (Settings.user_id == user_id)
                    ).offset(skip).limit(limit).all()
                else:
                    settings = query.filter(Settings.user_id.is_(None)).offset(skip).limit(limit).all()

        except Exception as col_error:
            # If columns don't exist, fall back to simple query
            from sqlalchemy import text
            try:
                result = db.execute(
                    text(f"SELECT id, key, value, description FROM settings ORDER BY id LIMIT {limit} OFFSET {skip}")
                )
                settings_data = []
                for row in result:
                    settings_data.append({
                        'id': row[0],
                        'key': row[1],
                        'value': row[2],
                        'description': row[3],
                        'language_code': None,
                        'user_id': None
                    })
                settings = settings_data
            except Exception as fallback_error:
                settings = []

        return {"items": settings}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading settings: {e}")

@router.post("/settings/create")
def create_setting(setting: SettingsCreateSchema, db: Session = Depends(get_db), current_user: dict = Depends(require_user)):
    """Create a new setting - ultra-safe implementation"""
    try:
        print(f"DEBUG: Setting creation request: {setting.model_dump()}")

        # Simple validation
        if not setting.key:
            raise HTTPException(status_code=400, detail="Setting key is required")

        user_id = current_user.get('user_id') if current_user else None

        # Ultra-safe query - check if key+language_code+user_id combination exists
        try:
            query = db.query(Settings).filter(Settings.key == setting.key)

            if setting.language_code:
                query = query.filter(Settings.language_code == setting.language_code)
            else:
                query = query.filter(Settings.language_code.is_(None))

            if user_id:
                query = query.filter(Settings.user_id == user_id)
            else:
                query = query.filter(Settings.user_id.is_(None))

            existing = query.first()

        except Exception as query_error:
            print(f"DEBUG: Query error: {query_error}")
            existing = None

        if existing:
            print(f"DEBUG: Updating existing setting: {existing.id}")
            # Update with safe field access
            existing.value = setting.value
            existing.description = setting.description

            # Try to set language_code safely
            if setting.language_code:
                try:
                    if hasattr(existing, 'language_code'):
                        existing.language_code = setting.language_code
                    else:
                        print("DEBUG: Setting model doesn't have language_code field")
                except Exception as lang_error:
                    print(f"DEBUG: Error setting language_code: {lang_error}")

            # Try to set user_id safely
            if user_id:
                try:
                    if hasattr(existing, 'user_id'):
                        existing.user_id = user_id
                    else:
                        print("DEBUG: Setting model doesn't have user_id field")
                except Exception as user_error:
                    print(f"DEBUG: Error setting user_id: {user_error}")

            db.commit()
            db.refresh(existing)
            return existing

        print("DEBUG: Creating new setting")

        # Create new setting with maximum compatibility
        try:
            # Always try the basic fields first
            setting_data = {
                'key': setting.key,
                'value': setting.value,
                'description': setting.description
            }

            # Only try to add language_code if it exists and has a value
            if setting.language_code and hasattr(Settings, 'language_code'):
                try:
                    setting_data['language_code'] = setting.language_code
                except Exception as lang_error:
                    print(f"DEBUG: Can't add language_code to setting_data: {lang_error}")

            # Add user_id if authenticated
            if user_id and hasattr(Settings, 'user_id'):
                try:
                    setting_data['user_id'] = user_id
                except Exception as user_error:
                    print(f"DEBUG: Can't add user_id to setting_data: {user_error}")

            db_setting = Settings(**setting_data)
            db.add(db_setting)
            db.commit()
            db.refresh(db_setting)

            print(f"DEBUG: Setting created successfully: {db_setting.id}")
            return db_setting

        except Exception as create_error:
            print(f"DEBUG: Error creating setting: {create_error}")
            # Try creating with minimal data if full creation fails
            try:
                db_setting = Settings(
                    key=setting.key,
                    value=setting.value,
                    description=setting.description
                )
                db.add(db_setting)
                db.commit()
                db.refresh(db_setting)
                print(f"DEBUG: Minimal setting created successfully: {db_setting.id}")
                return db_setting
            except Exception as minimal_error:
                print(f"DEBUG: Even minimal creation failed: {minimal_error}")
                raise create_error

    except HTTPException:
        raise
    except Exception as e:
        print(f"DEBUG: Full error in create_setting: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating setting: {str(e)}")

@router.put("/settings/update")
def update_settings(settings: SettingsUpdateSchema, db: Session = Depends(get_db)):
    """Update settings - temporarily without authentication for testing"""
    try:
        query = db.query(Settings).filter(Settings.id == settings.id)
        db_settings = query.first()
        if not db_settings:
            raise HTTPException(status_code=404, detail="Settings not found")

        db_settings.key = settings.key
        db_settings.value = settings.value
        db_settings.description = settings.description
        db_settings.language_code = settings.language_code

        db.commit()
        db.refresh(db_settings)
        return db_settings
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {str(e)}")

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

# Language-specific settings endpoints

@router.get("/settings/language/{language_code}")
def get_language_settings(language_code: str, db: Session = Depends(get_db)):
    """Get all settings for a specific language (with global fallbacks)"""
    try:
        # Get all settings for this language with global fallbacks
        global_settings = db.query(Settings).filter(Settings.language_code.is_(None)).all()
        lang_settings = db.query(Settings).filter(Settings.language_code == language_code).all()
        
        # Merge settings (language-specific overrides global)
        settings_dict = {}
        for setting in global_settings:
            settings_dict[setting.key] = setting
        
        for setting in lang_settings:
            settings_dict[setting.key] = setting
            
        return {"items": list(settings_dict.values())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching language settings: {e}")

@router.post("/settings/sync")
def sync_setting_across_languages(
    sync_request: SettingsSyncRequest,
    user = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Sync a setting across multiple languages"""
    try:
        results = []
        
        for language_code, value in sync_request.values.items():
            # Check if setting exists
            existing = db.query(Settings).filter(
                Settings.key == sync_request.key,
                Settings.language_code == language_code
            ).first()
            
            if existing:
                existing.value = value
                if sync_request.description:
                    existing.description = sync_request.description
            else:
                # Create new language-specific setting
                new_setting = Settings(
                    key=sync_request.key,
                    value=value,
                    description=sync_request.description or f"{sync_request.key} for {language_code}",
                    language_code=language_code
                )
                db.add(new_setting)
            
            results.append({"language": language_code, "status": "updated"})
        
        db.commit()
        return {
            "message": f"Setting '{sync_request.key}' synced across {len(sync_request.values)} languages",
            "results": results
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error syncing setting: {e}")

@router.get("/settings/keys")
def get_setting_keys(db: Session = Depends(get_db)):
    """Get all unique setting keys"""
    try:
        result = db.query(Settings.key).distinct().all()
        keys = [row[0] for row in result]
        return {"keys": keys}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching setting keys: {e}")

@router.get("/settings/keys/{key}")
def get_setting_variations(key: str, db: Session = Depends(get_db)):
    """Get all variations of a specific setting across languages"""
    try:
        settings = db.query(Settings).filter(Settings.key == key).all()
        variations = {}
        
        for setting in settings:
            lang = setting.language_code or "global"
            variations[lang] = {
                "value": setting.value,
                "description": setting.description,
                "language_code": setting.language_code
            }
        
        return {
            "key": key,
            "variations": variations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching setting variations: {e}")

# Language management routes

@router.get("/language/current")
def get_current_language():
    """Get the current language"""
    return {"language": get_current_language()}

@router.get("/language/available")
def get_available_languages():
    """Get available languages"""
    return {"languages": i18n_manager.get_available_languages()}

@router.post("/language/set")
def set_current_language(language: str, user = Depends(require_user)):
    """Set the current language - requires authentication"""
    if language not in i18n_manager.get_available_languages():
        raise HTTPException(status_code=400, detail="Language not available")
    set_language(language)
    return {"message": f"Language set to {language}"}

# Frontend configuration endpoints

@router.post("/frontend-config")
def set_frontend_config(config: FrontendConfigRequest, db: Session = Depends(get_db)):
    """Set frontend backend URL configuration - admin only"""
    try:
        # Store both frontend and backend URLs as JSON
        config_data = {
            "backend_url": config.backend_url,
            "frontend_url": config.frontend_url
        }

        # Check if config already exists
        existing = db.query(Settings).filter(Settings.key == "frontend_backend_url").first()

        if existing:
            # Update existing config with JSON data
            existing.value = json.dumps(config_data)
            existing.description = config.description
            db.commit()
            db.refresh(existing)
            return {"message": "Frontend configuration updated", "config": existing}
        else:
            # Create new config with JSON data
            new_config = Settings(
                key="frontend_backend_url",
                value=json.dumps(config_data),
                description=config.description
            )
            db.add(new_config)
            db.commit()
            db.refresh(new_config)
            return {"message": "Frontend configuration created", "config": new_config}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error setting frontend config: {e}")

@router.get("/frontend-config")
def get_frontend_config(db: Session = Depends(get_db)):
    """Get current frontend backend URL configuration"""
    try:
        # Use the already loaded app_config

        try:
            config = db.query(Settings).filter(Settings.key == "frontend_backend_url").first()
            if not config:
                # Return default configuration from config.json
                return {
                    "backend_url": app_config['frontend']['backend_url'],
                    "frontend_url": app_config['frontend']['frontend_url'],
                    "is_default": True
                }

            # Parse the stored JSON data
            try:
                config_data = json.loads(config.value)
                return {
                    "backend_url": config_data.get("backend_url", app_config['frontend']['backend_url']),
                    "frontend_url": config_data.get("frontend_url", app_config['frontend']['frontend_url']),
                    "description": config.description,
                    "is_default": False
                }
            except json.JSONDecodeError:
                # Fallback for old format (just backend_url)
                return {
                    "backend_url": config.value,
                    "frontend_url": app_config['frontend']['frontend_url'],
                    "description": config.description,
                    "is_default": False
                }
        except Exception as db_error:
            # If database is not available, return config defaults
            print(f"Database error in get_frontend_config, returning config defaults: {db_error}")
            return {
                "backend_url": app_config['frontend']['backend_url'],
                "frontend_url": app_config['frontend']['frontend_url'],
                "is_default": True
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting frontend config: {e}")

# Custom menu routes with proper multilingual support
@router.get("/menu/read")
def read_menus(db: Session = Depends(get_db)):
    """Get all menus with multilingual support"""
    try:
        menus = db.query(Menu).order_by(Menu.id).all()
        return {"items": menus}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading menus: {e}")

@router.get("/menu/read/{language}")
def read_menus_for_language(language: str, db: Session = Depends(get_db)):
    """Get menus with items for the specified language"""
    try:
        menus = db.query(Menu).order_by(Menu.id).all()
        translated_menus = []

        for menu in menus:
            # Return the items field directly (contains full multilingual menu data)
            menu_items = menu.items or []

            translated_menus.append({
                "id": menu.id,
                "name": menu.name,
                "items": menu_items,
                "is_active": menu.is_active,
                "language": language
            })

        return {"items": translated_menus}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading menus for language {language}: {e}")

@router.put("/menu/update")
def update_menu(menu_data: dict, db: Session = Depends(get_db)):
    """Update menu with multilingual support"""
    try:
        menu_id = menu_data.get("id")
        if not menu_id:
            raise HTTPException(status_code=400, detail="Menu ID is required")

        db_menu = db.query(Menu).filter(Menu.id == menu_id).first()
        if not db_menu:
            raise HTTPException(status_code=404, detail="Menu not found")

        # Extract language code from menu data (passed from frontend)
        language_code = menu_data.get("language", "en")

        # Get items directly from menu data (new optimal structure)
        items = menu_data.get("items", [])

        # Update menu fields
        db_menu.name = menu_data.get("name", db_menu.name)
        db_menu.items = items  # Store multilingual menu items directly
        db_menu.default_language = language_code
        db_menu.has_translations = any(
            isinstance(item.get("label"), dict) and len(item.get("label", {})) > 1
            for item in items
        )

        # Update structure for backward compatibility (contains config only)
        structure_data = menu_data.get("structure", {})
        if not structure_data:
            # Create minimal structure if not provided
            structure_data = {"config": {"position": "sidebar", "style": "vertical"}}
        db_menu.structure = structure_data

        db.commit()
        db.refresh(db_menu)

        return db_menu
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating menu: {e}")

@router.post("/frontend-config/detect")
def detect_frontend_config(request: Request, db: Session = Depends(get_db)):
    """Auto-detect frontend configuration based on request origin with improved IP detection"""
    try:
        # Get the host and protocol from the request
        forwarded_for = request.headers.get("x-forwarded-for")
        real_ip = request.headers.get("x-real-ip")
        host = request.headers.get("host")
        client_ip = "unknown"
        
        # Enhanced IP detection logic
        if forwarded_for:
            # Use the first IP from the forwarded list (handles load balancers)
            client_ip = forwarded_for.split(",")[0].strip()
        elif real_ip:
            client_ip = real_ip
        
        # Determine if this is an external IP (not localhost/private)
        is_external_ip = client_ip not in ["unknown", "127.0.0.1", "localhost"] and not client_ip.startswith(("192.168.", "10.", "172."))
        
        # Build frontend URL from host header with better logic
        frontend_url = app_config['frontend']['frontend_url']
        backend_url = app_config['frontend']['backend_url']
        
        if host:
            # Check if request is HTTPS
            if "x-forwarded-proto" in request.headers:
                protocol = request.headers.get("x-forwarded-proto")
            elif request.url.scheme:
                protocol = request.url.scheme
            else:
                protocol = "http"
            
            # Extract hostname (remove port if present)
            hostname = host.split(":")[0]
            
            # If we have a valid hostname and it's not localhost, use it
            if hostname and hostname not in ["localhost", "127.0.0.1"]:
                # For external IPs, detect the correct ports
                if is_external_ip or hostname not in ["localhost", "127.0.0.1"]:
                    # Try to determine if this is a different port
                    if ":" in host:
                        actual_port = host.split(":")[1]
                        # If accessing on port 5173, backend should be on 8887
                        if actual_port == "5173":
                            frontend_url = f"{protocol}://{hostname}:5173"
                            backend_url = f"{protocol}://{hostname}:8887"
                        # If accessing on port 8887, set both to the same host/port
                        elif actual_port == "8887":
                            frontend_url = f"{protocol}://{hostname}:5173"
                            backend_url = f"{protocol}://{hostname}:8887"
                        # For other ports, use the detected port
                        else:
                            frontend_url = f"{protocol}://{host}"
                            backend_url = f"{protocol}://{hostname}:8887"
                    else:
                        # No port in host header, use default ports
                        frontend_url = f"{protocol}://{hostname}:5173"
                        backend_url = f"{protocol}://{hostname}:8887"
            else:
                # Localhost fallback
                frontend_url = app_config['frontend']['frontend_url']
                backend_url = app_config['frontend']['backend_url']
        else:
            # No host header, check if we can determine from client IP
            if client_ip != "unknown" and is_external_ip:
                # Use the client IP as the hostname
                frontend_url = f"http://{client_ip}:5173"
                backend_url = f"http://{client_ip}:8887"
        
        return {
            "frontend_url": frontend_url,
            "backend_url": backend_url,
            "detected_ip": client_ip,
            "host": host,
            "is_external": is_external_ip,
            "detection_method": "header_based" if host else "ip_based"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error detecting frontend config: {e}")

@router.post("/settings/auto-configure")
def auto_configure_frontend(config_request: dict = None, request: Request = None, db: Session = Depends(get_db)):
    """Auto-configure frontend with detected backend URL"""
    try:
        # Get detected configuration
        detect_result = detect_frontend_config(request, db)

        # Use provided URL or detected URL
        backend_url = config_request.get("backend_url", detect_result["backend_url"]) if config_request else detect_result["backend_url"]
        frontend_url = detect_result["frontend_url"]

        # Store both URLs as JSON
        config_data = {
            "backend_url": backend_url,
            "frontend_url": frontend_url
        }

        # Update or create the configuration
        existing = db.query(Settings).filter(Settings.key == "frontend_backend_url").first()

        if existing:
            existing.value = json.dumps(config_data)
            existing.description = "Auto-configured frontend backend URL"
            db.commit()
            db.refresh(existing)
            message = "Frontend configuration auto-updated"
        else:
            new_config = Settings(
                key="frontend_backend_url",
                value=json.dumps(config_data),
                description="Auto-configured frontend backend URL"
            )
            db.add(new_config)
            db.commit()
            db.refresh(new_config)
            message = "Frontend configuration auto-created"

        return {
            "message": message,
            "backend_url": backend_url,
            "frontend_url": frontend_url,
            "detected_info": detect_result
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error auto-configuring frontend: {e}")

# Network discovery endpoints for mobile access

@router.get("/network/discovery")
def network_discovery(request: Request):
    """Network discovery endpoint for mobile device detection"""
    try:
        # Get various network information
        forwarded_for = request.headers.get("x-forwarded-for")
        real_ip = request.headers.get("x-real-ip")
        host = request.headers.get("host")
        user_agent = request.headers.get("user-agent", "")
        
        # Determine client IP
        client_ip = "unknown"
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        elif real_ip:
            client_ip = real_ip
        
        # Detect if this is a mobile device
        is_mobile = any(mobile_term in user_agent.lower() for mobile_term in [
            'mobile', 'android', 'iphone', 'ipad', 'tablet'
        ])
        
        # Determine if external IP
        is_external_ip = client_ip not in ["unknown", "127.0.0.1", "localhost"] and not client_ip.startswith(("192.168.", "10.", "172."))
        
        # Build detection results
        detection_results = {
            "client_ip": client_ip,
            "host": host,
            "user_agent": user_agent[:100],  # Truncate for privacy
            "is_mobile": is_mobile,
            "is_external_ip": is_external_ip,
            "timestamp": str(int(time.time())) if 'time' in dir() else "unknown"
        }

        # If we have a host, generate possible backend URLs
        if host:
            hostname = host.split(":")[0]
            protocol = "http"
            
            # Check for HTTPS
            if "x-forwarded-proto" in request.headers:
                protocol = request.headers.get("x-forwarded-proto")
            elif request.url.scheme:
                protocol = request.url.scheme
            
            # Generate possible backend URLs
            possible_backends = [
                f"{protocol}://{hostname}:8887",  # Standard backend port
                f"{protocol}://{hostname}:80",    # HTTP default
                f"{protocol}://{hostname}:443",   # HTTPS default
                app_config['frontend']['backend_url'],  # Config fallback
            ]
            
            detection_results["possible_backend_urls"] = possible_backends
            detection_results["recommended_backend"] = f"{protocol}://{hostname}:8887"
        
        # If we have external IP, suggest using it
        if is_external_ip and client_ip != "unknown":
            detection_results["external_ip_backend"] = f"http://{client_ip}:{app_config['backend']['port']}"
        
        return detection_results
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in network discovery: {e}")

@router.post("/network/test-connection")
def test_network_connection(test_request: dict, request: Request):
    """Test connection to a specific backend URL"""
    try:
        backend_url = test_request.get("backend_url")
        frontend_url = test_request.get("frontend_url", "unknown")
        
        if not backend_url:
            raise HTTPException(status_code=400, detail="backend_url is required")
        
        # Get client info
        client_ip = request.headers.get("x-forwarded-for", request.headers.get("x-real-ip", "unknown"))
        
        # Perform basic connectivity test
        test_result = {
            "backend_url": backend_url,
            "frontend_url": frontend_url,
            "client_ip": client_ip,
            "test_timestamp": str(int(time.time())) if 'time' in dir() else "unknown",
            "connection_status": "pending"
        }
        
        # Add the backend URL to the test result
        # In a real implementation, you might want to actually test the connection
        # For now, we'll just validate the URL format
        try:
            from urllib.parse import urlparse
            parsed = urlparse(backend_url)
            
            if not parsed.scheme or not parsed.netloc:
                test_result["connection_status"] = "invalid_url"
                test_result["error"] = "Invalid URL format"
            elif parsed.scheme not in ["http", "https"]:
                test_result["connection_status"] = "invalid_scheme"
                test_result["error"] = "Only HTTP and HTTPS are supported"
            else:
                test_result["connection_status"] = "url_valid"
                test_result["message"] = "URL format is valid"
                
        except Exception as parse_error:
            test_result["connection_status"] = "parse_error"
            test_result["error"] = str(parse_error)
        
        return test_result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error testing connection: {e}")

# Mobile-specific endpoints

@router.get("/mobile/config")
def mobile_configuration(request: Request):
    """Get mobile-optimized configuration"""
    try:
        # Get the standard detection
        detect_result = detect_frontend_config(request, None)
        
        # Add mobile-specific optimizations
        user_agent = request.headers.get("user-agent", "")
        is_mobile = any(mobile_term in user_agent.lower() for mobile_term in [
            'mobile', 'android', 'iphone', 'ipad', 'tablet'
        ])
        
        # Mobile optimizations
        mobile_config = detect_result.copy()
        mobile_config.update({
            "is_mobile": is_mobile,
            "mobile_optimized": True,
            "recommended_action": "auto_detect",
            "fallback_urls": [
                detect_result["backend_url"],
                app_config['frontend']['backend_url'],
                f"http://{request.headers.get('host', 'localhost').split(':')[0]}:8887"
            ]
        })
        
        # If mobile, suggest using the detected IP if it's external
        if is_mobile and detect_result.get("is_external"):
            mobile_config["recommended_backend"] = detect_result["backend_url"]
            mobile_config["recommended_action"] = "use_detected_ip"
        
        return mobile_config
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting mobile config: {e}")

@router.post("/mobile/setup")
def mobile_setup(setup_request: dict, request: Request):
    """Set up mobile access with best available backend URL"""
    try:
        # Get detection results
        detect_result = detect_frontend_config(request, None)

        # Determine the best backend URL to use
        backend_url = setup_request.get("backend_url") or detect_result["backend_url"]
        frontend_url = setup_request.get("frontend_url") or detect_result["frontend_url"]

        # Store both URLs as JSON
        config_data = {
            "backend_url": backend_url,
            "frontend_url": frontend_url
        }

        # Save the configuration
        from sqlalchemy.orm import Session
        db = next(get_db())

        try:
            existing = db.query(Settings).filter(Settings.key == "frontend_backend_url").first()

            if existing:
                existing.value = json.dumps(config_data)
                existing.description = f"Mobile setup - {setup_request.get('description', 'Auto-configured for mobile access')}"
                db.commit()
                message = "Mobile configuration updated"
            else:
                new_config = Settings(
                    key="frontend_backend_url",
                    value=json.dumps(config_data),
                    description=f"Mobile setup - {setup_request.get('description', 'Auto-configured for mobile access')}"
                )
                db.add(new_config)
                db.commit()
                message = "Mobile configuration created"

        finally:
            db.close()

        return {
            "message": message,
            "backend_url": backend_url,
            "frontend_url": frontend_url,
            "detection_info": detect_result,
            "setup_timestamp": str(int(time.time())) if 'time' in dir() else "unknown"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error setting up mobile access: {e}")

# Translation endpoints for dynamic loading
@router.get("/api/translations/{language_code}")
def get_translations(language_code: str):
    """Serve translations for a specific language from installed extensions"""
    try:
        import os
        import json

        translations = {}

        # Language name mapping
        language_name_map = {
            'bg': 'Bulgarian',
            'en': 'English',
            'fr': 'French',
            'de': 'German',
            'es': 'Spanish'
        }

        language_name = language_name_map.get(language_code, language_code.capitalize())

        # Get the absolute path to the project root
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        extension_path = os.path.join(project_root, "frontend", "src", "extensions", f"{language_name}LanguagePack_1.0.0")

        # Check if extension exists
        if not os.path.exists(extension_path):
            return {"frontend": {}, "backend": {}, "extensions": {}}

        # Load translation files
        translation_files = [
            'Settings.json', 'Login.json', 'Register.json', 'User.json',
            'PagesExtension.json', 'ClockWidget.json', 'Extensions.json'
        ]

        for file_name in translation_files:
            file_path = os.path.join(extension_path, file_name)
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_translations = json.load(f)
                        translations.update(file_translations)
                except Exception as e:
                    print(f"Error loading {file_name}: {e}")
                    continue

        return {
            "frontend": translations,
            "backend": {},
            "extensions": {}
        }

    except Exception as e:
        print(f"Error serving translations for {language_code}: {e}")
        return {"frontend": {}, "backend": {}, "extensions": {}}

# Global settings image upload endpoint
from fastapi import UploadFile, File
import uuid
from datetime import datetime
import os

@router.post("/upload/settings-image")
def upload_settings_image(
    file: UploadFile = File(...),
    claims: dict = Depends(require_user)
):
    """Upload image for global app settings (logos, etc.)"""
    try:
        # Validate file type
        allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"]
        if file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Invalid file type. Only JPEG, PNG, GIF, WebP, and SVG are allowed.")

        # Validate file size (max 2MB for settings images)
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        if file_size > 2 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large. Maximum size is 2MB.")

        # Generate simpler filename - use "logo.png" for logo uploads
        file_extension = os.path.splitext(file.filename)[1]
        # For logo uploads, use a simple consistent filename
        unique_filename = f"logo{file_extension}"

        # Use the same path construction as main.py to ensure consistency
        # Get the project root path (backend directory)
        project_root = os.path.join(os.path.dirname(__file__), '..', '..')
        uploads_dir = os.path.join(project_root, 'uploads', 'settings')
        os.makedirs(uploads_dir, exist_ok=True)

        # Debug: log the uploads directory path
        print(f"DEBUG: Settings upload directory: {uploads_dir}")
        print(f"DEBUG: Settings upload directory exists: {os.path.exists(uploads_dir)}")
        print(f"DEBUG: Project root: {project_root}")
        print(f"DEBUG: Main uploads directory: {os.path.join(project_root, 'uploads')}")

        # For logo uploads, use a simple consistent filename
        file_extension = os.path.splitext(file.filename)[1]
        simple_filename = f"logo{file_extension}"
        file_path = os.path.join(uploads_dir, simple_filename)

        # If file already exists, remove it first to avoid conflicts
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"DEBUG: Removed existing logo file: {file_path}")
            except Exception as e:
                print(f"DEBUG: Error removing existing logo file: {e}")

        # Save the file
        with open(file_path, "wb") as buffer:
            buffer.write(file.file.read())

        # Debug: verify file was saved
        print(f"DEBUG: Saved file to: {file_path}")
        print(f"DEBUG: File exists after save: {os.path.exists(file_path)}")

        return {
            "filename": simple_filename,
            "url": f"/uploads/settings/{simple_filename}",
            "message": "Settings image uploaded successfully"
        }

    except Exception as e:
        print(f"Error uploading settings image: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.get("/api/images/list")
def list_images(
    directory: str = "uploads",
    claims: dict = Depends(try_get_claims)
):
    """List all images in a specific upload directory"""
    try:
        # Security: restrict to allowed directories only
        allowed_directories = ["uploads", "uploads/settings", "uploads/store"]
        if directory not in allowed_directories:
            raise HTTPException(status_code=400, detail="Invalid directory specified")

        # Get the project root path
        project_root = os.path.join(os.path.dirname(__file__), '..', '..')
        target_dir = os.path.join(project_root, directory)

        # Debug logging
        print(f"DEBUG: Project root: {project_root}")
        print(f"DEBUG: Target directory: {target_dir}")
        print(f"DEBUG: Directory exists: {os.path.exists(target_dir)}")

        # Security: ensure the path is within our project
        if not os.path.abspath(target_dir).startswith(os.path.abspath(project_root)):
            raise HTTPException(status_code=403, detail="Access to this directory is not allowed")

        # Check if directory exists
        if not os.path.exists(target_dir):
            return {"images": [], "directory": directory, "message": "Directory does not exist"}

        # List all image files
        image_files = []
        try:
            files = os.listdir(target_dir)
            print(f"DEBUG: Files in directory: {files}")
        except Exception as list_error:
            print(f"DEBUG: Error listing directory: {list_error}")
            files = []

        for filename in files:
            file_path = os.path.join(target_dir, filename)

            # Only include image files
            if os.path.isfile(file_path) and filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg')):
                try:
                    # Get file stats
                    stat = os.stat(file_path)
                    image_files.append({
                        "name": filename,
                        "url": f"/{directory}/{filename}",
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "type": "image"
                    })
                    print(f"DEBUG: Added image file: {filename}")
                except Exception as e:
                    print(f"Error reading file {filename}: {e}")
                    continue

        print(f"DEBUG: Found {len(image_files)} image files")
        return {
            "images": image_files,
            "directory": directory,
            "count": len(image_files)
        }

    except Exception as e:
        print(f"Error listing images: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to list images: {str(e)}")

# Settings extension endpoints
@router.get("/api/settings/images/list")
def list_settings_images(
    directory: str = "settings",
    search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    claims: dict = Depends(try_get_claims)
):
    """List images in the settings directory"""
    try:
        # Map directory to full path
        if directory == "settings":
            full_directory = "uploads/settings"
        else:
            full_directory = f"uploads/{directory}"

        # Security: restrict to allowed directories only
        allowed_directories = ["uploads/settings"]
        if full_directory not in allowed_directories:
            raise HTTPException(status_code=400, detail="Invalid directory specified")

        # Get the project root path
        project_root = os.path.join(os.path.dirname(__file__), '..', '..')
        target_dir = os.path.join(project_root, full_directory)

        # Ensure directory exists
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        # List all image files
        image_files = []
        try:
            files = os.listdir(target_dir)
        except Exception as list_error:
            files = []

        for filename in files:
            file_path = os.path.join(target_dir, filename)

            # Only include image files
            if os.path.isfile(file_path) and filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg')):
                try:
                    # Get file stats
                    stat = os.stat(file_path)
                    image_files.append({
                        "name": filename,
                        "url": f"/{full_directory}/{filename}",
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "type": "image"
                    })
                except Exception as e:
                    continue

        # Apply search filter if provided
        if search:
            search_lower = search.lower()
            filtered_images = [
                img for img in image_files
                if search_lower in img["name"].lower() or search_lower in img["url"].lower()
            ]
        else:
            filtered_images = image_files

        # Apply pagination
        total_images = len(filtered_images)
        paginated_images = filtered_images[offset:offset + limit]

        # Build breadcrumb path
        breadcrumb = [{"name": "Settings", "path": "settings"}]

        return {
            "folders": [],
            "images": paginated_images,
            "total": total_images,
            "limit": limit,
            "offset": offset,
            "directory": directory,
            "breadcrumb": breadcrumb,
            "can_create_folder": True
        }

    except Exception as e:
        print(f"Error listing settings images: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list images: {str(e)}")

@router.post("/api/settings/upload-image")
def upload_settings_image_ext(
    file: UploadFile = File(...),
    directory: str = "settings",
    claims: dict = Depends(require_user)
):
    """Upload image for settings extension"""
    try:
        # Validate file type
        allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml"]
        if file.content_type not in allowed_types:
            raise HTTPException(status_code=400, detail="Invalid file type. Only JPEG, PNG, GIF, WebP, and SVG are allowed.")

        # Validate file size (max 2MB for settings images)
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        if file_size > 2 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large. Maximum size is 2MB.")

        # Generate unique filename
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex}{file_extension}"

        # Get the project root path
        project_root = os.path.join(os.path.dirname(__file__), '..', '..')
        uploads_dir = os.path.join(project_root, 'uploads', directory)
        os.makedirs(uploads_dir, exist_ok=True)

        # Save the file
        file_path = os.path.join(uploads_dir, unique_filename)
        with open(file_path, "wb") as buffer:
            buffer.write(file.file.read())

        return {
            "filename": unique_filename,
            "url": f"/uploads/{directory}/{unique_filename}",
            "message": "Settings image uploaded successfully"
        }

    except Exception as e:
        print(f"Error uploading settings image: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.post("/api/settings/images/folder")
def create_settings_folder(
    data: dict,
    claims: dict = Depends(require_user)
):
    """Create a folder in settings directory"""
    try:
        folder_name = data.get("folder_name")
        directory = data.get("directory", "settings")

        # Validate folder name
        if not folder_name or not folder_name.strip():
            raise HTTPException(status_code=400, detail="Folder name is required")

        # Sanitize folder name
        safe_name = "".join(c for c in folder_name.strip() if c.isalnum() or c in (' ', '-', '_')).rstrip()
        if not safe_name:
            raise HTTPException(status_code=400, detail="Invalid folder name")

        # Get the project root path
        project_root = os.path.join(os.path.dirname(__file__), '..', '..')
        base_dir = os.path.join(project_root, 'uploads', directory)
        new_folder_path = os.path.join(base_dir, safe_name)

        # Check if folder already exists
        if os.path.exists(new_folder_path):
            raise HTTPException(status_code=400, detail="Folder already exists")

        os.makedirs(new_folder_path, exist_ok=True)

        return {
            "message": "Folder created successfully",
            "folder": {
                "name": safe_name,
                "path": f"{directory}/{safe_name}".lstrip("/"),
                "type": "folder",
                "image_count": 0,
                "directory": directory
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating settings folder: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create folder: {str(e)}")

@router.delete("/api/settings/images/delete")
def delete_settings_image(
    data: dict,
    claims: dict = Depends(require_user)
):
    """Delete an image from settings directory"""
    try:
        image_name = data.get("image_name")
        directory = data.get("directory", "settings")

        if not image_name:
            raise HTTPException(status_code=400, detail="Image name is required")

        # Map directory to full path
        if directory == "settings":
            full_directory = "uploads/settings"
        else:
            full_directory = f"uploads/{directory}"

        # Security: restrict to allowed directories only
        allowed_directories = ["uploads/settings"]
        if full_directory not in allowed_directories:
            raise HTTPException(status_code=400, detail="Invalid directory specified")

        # Get the project root path
        project_root = os.path.join(os.path.dirname(__file__), '..', '..')
        file_path = os.path.join(project_root, full_directory, image_name)

        # Security: ensure the path is within our project
        if not os.path.abspath(file_path).startswith(os.path.abspath(project_root)):
            raise HTTPException(status_code=403, detail="Access to this file is not allowed")

        # Check if file exists
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Image not found")

        # Delete the file
        os.remove(file_path)

        return {"message": "Image deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting settings image: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete image: {str(e)}")

@router.post("/api/settings/images/rename")
def rename_settings_image(
    data: dict,
    claims: dict = Depends(require_user)
):
    """Rename an image in settings directory"""
    try:
        current_name = data.get("current_name")
        new_name = data.get("new_name")
        directory = data.get("directory", "settings")

        if not current_name or not new_name:
            raise HTTPException(status_code=400, detail="Current name and new name are required")

        # Map directory to full path
        if directory == "settings":
            full_directory = "uploads/settings"
        else:
            full_directory = f"uploads/{directory}"

        # Security: restrict to allowed directories only
        allowed_directories = ["uploads/settings"]
        if full_directory not in allowed_directories:
            raise HTTPException(status_code=400, detail="Invalid directory specified")

        # Get the project root path
        project_root = os.path.join(os.path.dirname(__file__), '..', '..')
        current_path = os.path.join(project_root, full_directory, current_name)
        new_path = os.path.join(project_root, full_directory, new_name)

        # Security: ensure the paths are within our project
        if not (os.path.abspath(current_path).startswith(os.path.abspath(project_root)) and
                os.path.abspath(new_path).startswith(os.path.abspath(project_root))):
            raise HTTPException(status_code=403, detail="Access to these files is not allowed")

        # Check if current file exists
        if not os.path.exists(current_path):
            raise HTTPException(status_code=404, detail="Image not found")

        # Check if new file already exists
        if os.path.exists(new_path):
            raise HTTPException(status_code=400, detail="A file with this name already exists")

        # Rename the file
        os.rename(current_path, new_path)

        return {
            "message": "Image renamed successfully",
            "old_name": current_name,
            "new_name": new_name,
            "new_url": f"/{full_directory}/{new_name}"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error renaming settings image: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to rename image: {str(e)}")

@router.get("/api/debug/cropper")
def debug_cropper():
    """Debug endpoint to test cropper functionality"""
    try:
        # This is just a test endpoint to verify backend is working
        return {
            "status": "ok",
            "message": "Backend debug endpoint working",
            "timestamp": str(datetime.now())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Debug error: {str(e)}")

# Add CORS headers to the debug endpoint
@router.options("/api/debug/cropper")
def debug_cropper_options():
    """Handle OPTIONS request for debug endpoint"""
    return {"message": "CORS preflight handled"}
