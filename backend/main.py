from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from backend.routes.settings import router as settings_router
from backend.routes.extensions import router as extensions_router
from backend.database import init_db
from backend.routes.user import router as user_router
from backend.routes.page_routes import router as page_router
from fastapi.middleware.cors import CORSMiddleware
import logging
import sys
import os
import importlib
from pathlib import Path
from backend.extensions.raspberry_pi_controller.routes import router as raspberry_pi_controller_router
from backend.extensions.manager.routes import router as manager_router

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
app.include_router(extensions_router)
app.include_router(user_router, prefix="/user")
app.include_router(page_router, prefix="/pages")
app.include_router(raspberry_pi_controller_router, prefix="/extensions/raspberry_pi_controller")
app.include_router(manager_router, prefix="/extensions/manager")

# Initialize the database schema
init_db()

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

# Log routes specifically for extensions_router
for route in extensions_router.routes:
    logger.debug(f"Extensions Route: {route.path}, Operation ID: {route.operation_id}")

# Dynamically register routes for extensions
extensions_path = Path(__file__).parent / "extensions"
for extension_dir in extensions_path.iterdir():
    if extension_dir.is_dir():
        init_file = extension_dir / "__init__.py"
        if init_file.exists():
            try:
                module_name = f"backend.extensions.{extension_dir.name}"
                module = importlib.import_module(module_name)
                if hasattr(module, "router"):
                    app.include_router(module.router, prefix=f"/extensions/{extension_dir.name}")
            except Exception as e:
                logger.error(f"Failed to register extension {extension_dir.name}: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8887, reload=True)
