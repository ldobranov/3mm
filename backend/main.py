import sys
import os
from pathlib import Path

# Fix path inconsistency - use the same approach as database.py
# Add project root to sys.path FIRST - before any imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware
import logging
import asyncio
import json
from fastapi.encoders import jsonable_encoder
import os

# Load config from root config.json
config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
with open(config_path, 'r') as f:
    config = json.load(f)

# Import database and models first
from backend.database import init_db, get_db
import backend.db.user  # noqa: F401
import backend.db.audit_log  # noqa: F401
import backend.db.role  # noqa: F401 - Import to ensure tables are created
import backend.db.association_tables  # noqa: F401 - Import to ensure tables are created
#import backend.db.language_pack  # noqa: F401 - Import to ensure tables are created

# Import all route routers
from backend.routes.settings import router as settings_router
from backend.routes.user import router as user_router
from backend.routes.display_routes import router as display_router
from backend.routes.auth_refresh import router as refresh_router
from backend.routes.session_routes import router as session_router
from backend.routes.audit_routes import router as audit_router
from backend.routes.permission_routes import router as permission_router
from backend.routes.extension_routes import router as extension_router
from backend.routes.marketplace_routes import router as marketplace_router
from backend.routes.monitoring_routes import router as monitoring_router
from backend.routes.role_routes import router as role_router
from backend.routes.group_routes import router as group_router
from backend.routes.language_routes import router as language_router
from backend.routes.ai_extension_builder_routes import router as ai_extension_builder_router

# Import extension utilities
from backend.utils.extension_updates import update_manager
from backend.utils.extension_monitoring import performance_monitor
from backend.utils.extension_manager import extension_manager
from backend.db.extension import Extension

# Configure logging to file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("backend_debug.log", mode="w"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("backend_debug")

# Custom JSON response class that preserves Unicode characters
class UnicodeJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")

# Configure FastAPI to use Unicode-preserving JSON encoder
app = FastAPI(default_response_class=UnicodeJSONResponse)

class CustomErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            response = await call_next(request)
            return response
        except RequestValidationError as exc:
            return UnicodeJSONResponse(
                status_code=422,
                content={"error": "Validation Error", "details": exc.errors()}
            )
        except Exception as exc:
            return UnicodeJSONResponse(
                status_code=500,
                content={"error": "Internal Server Error", "details": str(exc)}
            )

# Add middleware to FastAPI app
app.add_middleware(CustomErrorHandlerMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Frontend origin
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
    expose_headers=["Authorization-Token"],  # Expose Authorization-Token header
)

# Mount static files for uploads
uploads_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads')
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# Debug: log the uploads directory path
print(f"DEBUG: Uploads directory mounted at: {uploads_dir}")
print(f"DEBUG: Uploads directory exists: {os.path.exists(uploads_dir)}")
print(f"DEBUG: Uploads/settings directory exists: {os.path.exists(os.path.join(uploads_dir, 'settings'))}")

# List files in uploads/settings for debugging
settings_dir = os.path.join(uploads_dir, 'settings')
if os.path.exists(settings_dir):
    try:
        files = os.listdir(settings_dir)
        print(f"DEBUG: Files in uploads/settings: {files}")
    except Exception as e:
        print(f"DEBUG: Error listing files in uploads/settings: {e}")
else:
    print("DEBUG: uploads/settings directory does not exist")

# Add logging for static file requests
@app.middleware("http")
async def log_static_requests(request, call_next):
    response = await call_next(request)
    return response

app.include_router(settings_router)
app.include_router(user_router, prefix="/api/user")
# Page routes removed - will be provided by PagesExtension
# app.include_router(page_router, prefix="/pages")
app.include_router(display_router)
app.include_router(refresh_router, prefix="/api")
app.include_router(session_router, prefix="/api")
app.include_router(audit_router, prefix="/api")
app.include_router(permission_router, prefix="/api")
# Remove duplicated role and group routes - they are handled by /api/ prefixed routes
app.include_router(role_router, prefix="/api")
app.include_router(group_router, prefix="/api")
app.include_router(extension_router)
app.include_router(marketplace_router)
app.include_router(monitoring_router)
app.include_router(language_router, prefix="/api")
app.include_router(ai_extension_builder_router)

# Initialize the database schema
init_db()

# Start extension update manager (non-blocking)
asyncio.create_task(update_manager.start_update_worker())

# Start extension performance monitoring (non-blocking)
asyncio.create_task(performance_monitor.start_monitoring())

# Load enabled extensions at startup (non-blocking)
async def load_enabled_extensions():
    """Load all enabled extensions at startup - non-blocking"""
    db = None
    try:
        # Wait a moment for database to be fully initialized
        await asyncio.sleep(0.1)
        db = next(get_db())
        enabled_extensions = db.query(Extension).filter(
            Extension.is_enabled == True
        ).all()
        
        if not enabled_extensions:
            logger.info("No enabled extensions to load")
            return

        for extension in enabled_extensions:
            extension_id = f"{extension.name}_{extension.version}"
            extension_path = Path(extension.file_path)

            if extension_path.exists():
                try:
                    success = extension_manager.initialize_extension(
                        extension_id=extension_id,
                        extension_path=extension_path,
                        app=app,
                        db=db
                    )
                    if success:
                        logger.info(f"✅ Extension {extension_id} loaded successfully")
                    else:
                        logger.warning(f"❌ Failed to load extension {extension_id}")
                except Exception as e:
                    logger.error(f"❌ Error loading extension {extension_id}: {e}")
            else:
                # Skip warning for system extension (core functionality)
                if extension_path != Path("system"):
                    logger.warning(f"⚠️ Extension path not found: {extension_path}")

    except Exception as e:
        print(f"Error loading extensions: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if db:
            db.close()

# Start extension loading as background task
asyncio.create_task(load_enabled_extensions())

# Removed excessive debug logging for cleaner startup

# Extensions removed for MVP cleanup

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config['backend']['host'], port=config['backend']['port'], reload=True)
