from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from backend.routes.settings import router as settings_router
from backend.database import init_db
from backend.routes.user import router as user_router
# Page routes removed - will be provided by PagesExtension
# from backend.routes.page_routes import router as page_router
from fastapi.middleware.cors import CORSMiddleware
import logging
import sys
import os
import asyncio
from pathlib import Path
import backend.db.user  # noqa: F401
import backend.db.audit_log  # noqa: F401
import backend.db.role  # noqa: F401 - Import to ensure tables are created
import backend.db.association_tables  # noqa: F401 - Import to ensure tables are created
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
from backend.utils.extension_updates import update_manager
# Add backend directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Configure logging to file
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("backend_debug.log", mode="w"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("backend_debug")

app = FastAPI()

class CustomErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            response = await call_next(request)
            return response
        except RequestValidationError as exc:
            return JSONResponse(
                status_code=422,
                content={"error": "Validation Error", "details": exc.errors()}
            )
        except Exception as exc:
            return JSONResponse(
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

app.include_router(settings_router)
app.include_router(user_router, prefix="/user")
# Page routes removed - will be provided by PagesExtension
# app.include_router(page_router, prefix="/pages")
app.include_router(display_router)
app.include_router(refresh_router, prefix="/api")
app.include_router(session_router, prefix="/api")
app.include_router(audit_router, prefix="/api")
app.include_router(permission_router, prefix="/api")
app.include_router(role_router)
app.include_router(group_router)
app.include_router(extension_router)
app.include_router(marketplace_router)
app.include_router(monitoring_router)
# Initialize the database schema
init_db()

# Start extension update manager
asyncio.create_task(update_manager.start_update_worker())

# Start extension performance monitoring
from backend.utils.extension_monitoring import performance_monitor
asyncio.create_task(performance_monitor.start_monitoring())

# Load enabled extensions at startup
from backend.utils.extension_manager import extension_manager
from backend.db.extension import Extension
from backend.database import get_db

def load_enabled_extensions():
    """Load all enabled extensions at startup"""
    db = None
    try:
        db = next(get_db())
        enabled_extensions = db.query(Extension).filter(
            Extension.is_enabled == True
        ).all()
        
        for extension in enabled_extensions:
            extension_id = f"{extension.name}_{extension.version}"
            extension_path = Path(extension.file_path)
            
            if extension_path.exists():
                print(f"Loading enabled extension: {extension_id}")
                success = extension_manager.initialize_extension(
                    extension_id=extension_id,
                    extension_path=extension_path,
                    app=app,
                    db=db
                )
                if success:
                    print(f"✅ Extension {extension_id} loaded successfully")
                else:
                    print(f"❌ Failed to load extension {extension_id}")
            else:
                print(f"⚠️ Extension path not found: {extension_path}")
        
    except Exception as e:
        print(f"Error loading extensions: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if db:
            db.close()

# Load extensions after database is initialized
load_enabled_extensions()

logger.debug("Test log: Logging setup verification.")

from fastapi.routing import APIRoute

# Log all registered routes and their operation IDs
def log_registered_routes(app):
    for route in app.routes:
        if isinstance(route, APIRoute):
            logging.debug(f"Route: {route.path}, Operation ID: {route.operation_id}")

# Call the function after app initialization
log_registered_routes(app)

# Log all registered routes
for route in app.routes:
    if hasattr(route, 'path'):
        logger.debug(f"Registered route: {route.path}")

# Extensions removed for MVP cleanup

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8887, reload=True)
