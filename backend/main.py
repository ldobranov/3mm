import asyncio
import json
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

import backend.db.association_tables  # noqa: F401 - Import to ensure tables are created
import backend.db.audit_log  # noqa: F401
import backend.db.role  # noqa: F401 - Import to ensure tables are created
import backend.db.user  # noqa: F401
from backend.config import get_settings

# Import database and models first
from backend.database import get_db, init_db
from backend.db.extension import Extension
from backend.routes.ai_extension_builder_routes import (
    router as ai_extension_builder_router,
)
from backend.routes.ai_automations import router as ai_automations_router
from backend.routes.extension_projects import router as extension_projects_router
from backend.routes.audit_routes import router as audit_router
from backend.routes.auth_refresh import router as refresh_router
from backend.routes.display_routes import router as display_router
from backend.routes.device_pairing import router as device_pairing_router
from backend.routes.device_ingest import router as device_ingest_router
from backend.routes.device_registry import router as device_registry_router
from backend.routes.device_commands import router as device_commands_router
from backend.routes.device_state import router as device_state_router
from backend.routes.device_capabilities import router as device_capabilities_router
from backend.routes.device_capability_state import router as device_capability_state_router
from backend.routes.device_events import router as device_events_router
from backend.routes.extension_routes import router as extension_router
from backend.routes.group_routes import router as group_router
from backend.routes.language_routes import router as language_router
from backend.routes.marketplace_routes import router as marketplace_router
from backend.routes.monitoring_routes import router as monitoring_router
from backend.routes.modules import router as modules_router
from backend.routes.runtime_extensions import router as runtime_extensions_router
from backend.routes.permission_routes import router as permission_router
from backend.routes.role_routes import router as role_router
from backend.routes.session_routes import router as session_router
from backend.routes.system_updates import router as system_updates_router
from backend.routes.network_recovery import router as network_recovery_router
from backend.services.update_policy import system_update_check_manager

# Import all route routers
from backend.routes.settings import router as settings_router
from backend.routes.user import router as user_router
from backend.utils.extension_manager import extension_manager
from backend.utils.extension_monitoring import performance_monitor

# Import extension utilities
from backend.utils.extension_updates import update_manager

# import backend.db.language_pack  # noqa: F401 - Import to ensure tables are created

app_settings = get_settings()


# Configure logging. Service managers can redirect stdout/stderr to persistent
# storage without the application mutating a tracked file at import time.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
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


async def load_enabled_extensions(app: FastAPI):
    """Load all enabled extensions after application startup."""
    db = None
    try:
        db = next(get_db())
        enabled_extensions = (
            db.query(Extension).filter(Extension.is_enabled.is_(True)).all()
        )

        if not enabled_extensions:
            logger.info("No enabled extensions to load")
            return

        for extension in enabled_extensions:
            extension_id = f"{extension.name}_{extension.version}"
            extension_path = Path(extension.file_path)

            if extension_path.exists():
                success = extension_manager.initialize_extension(
                    extension_id=extension_id,
                    extension_path=extension_path,
                    app=app,
                    db=db,
                )
                if success:
                    logger.info("Extension %s loaded successfully", extension_id)
                else:
                    logger.warning("Failed to load extension %s", extension_id)
            elif extension_path != Path("system"):
                logger.warning("Extension path not found: %s", extension_path)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Error loading enabled extensions")
    finally:
        if db:
            db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Own all application startup and shutdown work."""
    init_db()
    await update_manager.start_update_worker()
    await performance_monitor.start_monitoring()
    await system_update_check_manager.start()
    extension_loader_task = asyncio.create_task(
        load_enabled_extensions(app), name="enabled-extension-loader"
    )

    try:
        yield
    finally:
        if not extension_loader_task.done():
            extension_loader_task.cancel()
        with suppress(asyncio.CancelledError):
            await extension_loader_task
        await performance_monitor.stop_monitoring()
        await update_manager.stop_update_worker()
        await system_update_check_manager.stop()


# Configure FastAPI to use Unicode-preserving JSON encoder
app = FastAPI(default_response_class=UnicodeJSONResponse, lifespan=lifespan)


class CustomErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            response = await call_next(request)
            return response
        except RequestValidationError as exc:
            return UnicodeJSONResponse(
                status_code=422,
                content={"error": "Validation Error", "details": exc.errors()},
            )
        except Exception as exc:
            return UnicodeJSONResponse(
                status_code=500,
                content={"error": "Internal Server Error", "details": str(exc)},
            )


# Add middleware to FastAPI app
app.add_middleware(CustomErrorHandlerMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.backend.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
    expose_headers=["Authorization-Token"],  # Expose Authorization-Token header
)

# Mount static files for uploads
uploads_dir = app_settings.backend.uploads_dir.resolve()
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


@app.get("/ready", tags=["system"])
def readiness():
    db = next(get_db())
    try:
        db.execute(text("SELECT 1"))
    finally:
        db.close()
    return {"status": "ready"}


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
app.include_router(device_pairing_router)
app.include_router(device_ingest_router)
app.include_router(device_registry_router)
app.include_router(device_commands_router)
app.include_router(device_state_router)
app.include_router(device_capabilities_router)
app.include_router(device_capability_state_router)
app.include_router(device_events_router)
app.include_router(modules_router)
app.include_router(runtime_extensions_router)
app.include_router(ai_automations_router)
app.include_router(extension_projects_router)
app.include_router(system_updates_router)
app.include_router(network_recovery_router)
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

# Removed excessive debug logging for cleaner startup

# Extensions removed for MVP cleanup

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=app_settings.backend.host,
        port=app_settings.backend.port,
        reload=True,
    )
