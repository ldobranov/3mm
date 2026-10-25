import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.routing import iter_route_contexts
from backend.utils.auth_dep import guard_user_session
from backend.utils.device_body_limit import DeviceBodyLimitMiddleware
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
from backend.services.asset_storage import get_asset_storage

# Import database and models first
from backend.database import get_db, init_db
from backend.routes.ai_extension_builder_routes import (
    router as ai_extension_builder_router,
)
from backend.routes.application_extensions import router as application_extensions_router
from backend.routes.application_authority import router as application_authority_router
from backend.routes.application_events import router as application_events_router
from backend.routes.application_operations import router as application_operations_router
from backend.routes.installation_peers import router as installation_peers_router
from backend.routes.backups import router as backups_router
from backend.routes.diagnostics import router as diagnostics_router
from backend.routes.ai_automations import router as ai_automations_router
from backend.routes.extension_projects import router as extension_projects_router
from backend.routes.audit_routes import router as audit_router
from backend.routes.auth_refresh import router as refresh_router
from backend.routes.display_routes import router as display_router
from backend.routes.device_pairing import router as device_pairing_router
from backend.routes.device_platform import router as device_platform_router
from backend.routes.device_ingest import router as device_ingest_router
from backend.routes.device_registry import router as device_registry_router
from backend.routes.device_commands import router as device_commands_router
from backend.routes.device_state import router as device_state_router
from backend.routes.device_capabilities import router as device_capabilities_router
from backend.routes.device_runtime_features import router as device_runtime_features_router
from backend.routes.device_capability_state import router as device_capability_state_router
from backend.routes.device_events import router as device_events_router
from backend.routes.node_update_delivery import router as node_update_delivery_router
from backend.routes.group_routes import router as group_router
from backend.routes.language_routes import router as language_router
from backend.routes.modules import router as modules_router
from backend.routes.runtime_extensions import router as runtime_extensions_router
from backend.routes.permission_routes import router as permission_router
from backend.routes.role_routes import router as role_router
from backend.routes.session_routes import router as session_router
from backend.routes.system_updates import router as system_updates_router
from backend.routes.system_control import router as system_control_router
from backend.routes.network_recovery import router as network_recovery_router
from backend.routes.node_updates import router as node_updates_router
from backend.services.update_policy import system_update_check_manager
from backend.services.core_components import CoreComponents

# Import all route routers
from backend.routes.settings import router as settings_router
from backend.routes.user import router as user_router


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


def _language_packages():
    from backend.services.language_extensions import BundledLanguagePackages
    return BundledLanguagePackages(get_db, app_settings)


def _runtime_authority():
    import pwd,grp
    from backend.services.application_platform import CoreRuntimeAuthorityServer
    runtime=pwd.getpwnam(app_settings.applications.runtime_user)
    if runtime.pw_uid==os.geteuid():
        raise ValueError("Core and Runtime require distinct OS principals")
    # Missing optional connector principal must not take down SDK admission.
    try:
        connector_uid = pwd.getpwnam(app_settings.applications.connector_worker_user).pw_uid
        if connector_uid in {0, os.geteuid(), runtime.pw_uid}: connector_uid = None
    except KeyError: connector_uid = None
    return CoreRuntimeAuthorityServer(app_settings.applications.authority_socket,
        app_settings.applications.key_root,runtime_uid=runtime.pw_uid,
        group=grp.getgrgid(runtime.pw_gid).gr_name,runtime_root=app_settings.applications.root,
        connector_worker_path=app_settings.applications.connector_worker_socket, connector_worker_uid=connector_uid)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Database readiness is required; optional functionality may be degraded."""
    init_db()
    # The pinned FastAPI builds included-router dependencies lazily. Prepare
    # their cached schemas before readiness, without executing any request.
    for _ in iter_route_contexts(app.routes):
        pass
    components = CoreComponents()
    app.state.core_components = components
    try:
        await components.start("language_extensions", _language_packages)
        await components.start("runtime_authority", _runtime_authority, check=lambda service: service.is_running)
        await components.start("system_updates", lambda: system_update_check_manager, task_attribute="_worker_task")
        yield
    finally:
        await components.close()


# Configure FastAPI to use Unicode-preserving JSON encoder
app = FastAPI(default_response_class=UnicodeJSONResponse, lifespan=lifespan,
              dependencies=[Depends(guard_user_session)])


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
app.add_middleware(DeviceBodyLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.backend.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
    expose_headers=["Authorization-Token"],  # Expose Authorization-Token header
)

# Mount static files for uploads
uploads_dir = get_asset_storage(app_settings).directory(create=True)
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
app.include_router(device_platform_router)
app.include_router(device_ingest_router)
app.include_router(device_registry_router)
app.include_router(device_commands_router)
app.include_router(node_update_delivery_router)
app.include_router(node_updates_router)
app.include_router(device_state_router)
app.include_router(device_capabilities_router)
app.include_router(device_runtime_features_router)
app.include_router(device_capability_state_router)
app.include_router(device_events_router)
app.include_router(modules_router)
app.include_router(application_extensions_router)
app.include_router(application_authority_router)
if os.getenv("THREE_MM_LOCAL_SESSIONS") == "1" or os.getenv("THREE_MM_SESSION_LINKS") == "1":
    # Never mount the old user-id-only prototype. Both M20 and human authority
    # are checked continuously by this exact UI-bound isolated-worker connector.
    from backend.database import engine
    from backend.routes.application_sessions import application_session_router
    from backend.services.application_session_runtimes import configured_browser_service
    app.include_router(application_session_router(configured_browser_service(engine)))
app.include_router(application_events_router)
app.include_router(application_operations_router)
app.include_router(installation_peers_router)
app.include_router(runtime_extensions_router)
app.include_router(ai_automations_router)
app.include_router(extension_projects_router)
app.include_router(system_updates_router)
app.include_router(system_control_router)
app.include_router(network_recovery_router)
app.include_router(backups_router)
app.include_router(diagnostics_router)
app.include_router(refresh_router, prefix="/api")
app.include_router(session_router, prefix="/api")
app.include_router(audit_router, prefix="/api")
app.include_router(permission_router, prefix="/api")
# Remove duplicated role and group routes - they are handled by /api/ prefixed routes
app.include_router(role_router, prefix="/api")
app.include_router(group_router, prefix="/api")
app.include_router(language_router, prefix="/api")
app.include_router(ai_extension_builder_router)

# Removed excessive debug logging for cleaner startup


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=app_settings.backend.host,
        port=app_settings.backend.port,
        reload=True,
    )
