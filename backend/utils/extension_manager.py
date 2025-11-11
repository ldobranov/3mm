"""
Extension Manager - Core component for managing extension lifecycle
"""

import sys
import importlib.util
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, APIRouter
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.utils.extension_security import security_manager
from backend.utils.extension_database import extension_db_manager
from backend.utils.extension_communication import event_bus, service_registry, data_sharing
from backend.utils.i18n import i18n_manager


class ExtensionContext:
    """Context object passed to extensions during initialization"""

    def __init__(self, app: FastAPI, db: Session, extension_id: str, version: str, config: dict = None):
        self.app = app
        self.db = db
        self.extension_id = extension_id
        self.version = version
        self.config = config or {}
        self.routes_registered: List[APIRouter] = []
        self.db_session = None  # Extension-specific database session
        self.initialized = False

    def register_router(self, router: APIRouter) -> None:
        """Register a router with the extension context"""
        self.routes_registered.append(router)
        self.app.include_router(router)

    def unregister_routes(self) -> None:
        """Unregister all routes for this extension"""
        # Note: FastAPI doesn't have a built-in way to remove routes
        # This would require more complex route management
        # For now, we'll track routes but not remove them
        pass

    def execute_query(self, query: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Execute a database query for this extension"""
        if not self.db_session:
            raise Exception("No database session available for extension")
        return extension_db_manager.execute_extension_query(self.extension_id, query, params)


class ExtensionManager:
    """Manages the lifecycle of extensions"""

    def __init__(self):
        self.loaded_extensions: Dict[str, Any] = {}
        self.extension_contexts: Dict[str, ExtensionContext] = {}
        self.extension_modules: Dict[str, Any] = {}

    def load_extension_module(self, extension_path: Path, extension_id: str) -> Optional[Any]:
        """Load an extension module from file path"""
        try:
            # Look for backend_entry in manifest
            manifest_path = extension_path / "manifest.json"
            if not manifest_path.exists():
                print(f"No manifest.json found for extension {extension_id}")
                return None

            with open(manifest_path, 'r') as f:
                manifest = json.load(f)

            backend_entry = manifest.get('backend_entry')
            if not backend_entry:
                print(f"No backend_entry specified for extension {extension_id}")
                return None

            backend_file = extension_path / backend_entry
            if not backend_file.exists():
                print(f"Backend entry file {backend_entry} not found for extension {extension_id}")
                return None

            # Load the module
            spec = importlib.util.spec_from_file_location(f"extension_{extension_id}", backend_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[f"extension_{extension_id}"] = module
                spec.loader.exec_module(module)

                self.extension_modules[extension_id] = module
                return module
            else:
                print(f"Failed to create module spec for {extension_id}")
                return None

        except Exception as e:
            print(f"Error loading extension module {extension_id}: {e}")
            return None

    def initialize_extension(self, extension_id: str, extension_path: Path, app: FastAPI, db: Session) -> bool:
        """Initialize an extension"""
        try:
            # Load manifest to check type
            manifest_path = extension_path / "manifest.json"
            manifest = {}
            if manifest_path.exists():
                with open(manifest_path, 'r') as f:
                    manifest = json.load(f)

            extension_type = manifest.get('type', 'widget')

            # Load the module if not already loaded (for non-language extensions)
            module = None
            if extension_type != 'language':
                module = self.extension_modules.get(extension_id)
                if not module:
                    module = self.load_extension_module(extension_path, extension_id)
                    if not module:
                        return False

            # Handle language packs
            if extension_type == 'language':
                language_info = manifest.get('language', {})
                language_code = language_info.get('code', extension_id.lower())
                translations = manifest.get('translations', {})

                # Load backend translations
                backend_translations = translations.get('backend')
                if backend_translations:
                    translations_dir = extension_path / backend_translations
                    if translations_dir.exists() and translations_dir.is_dir():
                        i18n_manager.load_language_pack(language_code, translations_dir)
                    elif translations_dir.exists() and translations_dir.is_file():
                        # Single file
                        i18n_manager.load_language_pack(language_code, translations_dir.parent)

                print(f"Language pack {extension_id} loaded for {language_code}")
                # Language packs don't need further initialization
                return True

            # Initialize extension database if needed
            db_initialized = extension_db_manager.initialize_extension_database(extension_path, extension_id)
            if not db_initialized:
                print(f"Warning: Failed to initialize database for extension {extension_id}")

            # Create extension context
            context = ExtensionContext(
                app=app,
                db=db,
                extension_id=extension_id,
                version=manifest.get('version', '1.0.0')
            )

            # Add database session to context
            context.db_session = extension_db_manager.get_extension_session(extension_id)

            # Set up communication channels
            context.event_bus = event_bus
            context.service_registry = service_registry
            context.data_sharing = data_sharing

            # Call initialization function
            if hasattr(module, 'initialize_extension'):
                result = module.initialize_extension(context)
                print(f"Extension {extension_id} initialized: {result}")
                context.initialized = True
                self.extension_contexts[extension_id] = context
                self.loaded_extensions[extension_id] = module
                return True
            else:
                print(f"Extension {extension_id} has no initialize_extension function")
                return False

        except Exception as e:
            print(f"Error initializing extension {extension_id}: {e}")
            return False

    def cleanup_extension(self, extension_id: str) -> bool:
        """Cleanup an extension"""
        try:
            context = self.extension_contexts.get(extension_id)
            module = self.loaded_extensions.get(extension_id)

            if context and module and hasattr(module, 'cleanup_extension'):
                module.cleanup_extension(context)
                print(f"Extension {extension_id} cleaned up")

            # Clean up communication resources
            event_bus.unregister_handler(extension_id)
            service_registry.unregister_service(extension_id)
            data_sharing.revoke_data_access(extension_id)

            # Unregister from monitoring
            from backend.utils.extension_monitoring import performance_monitor
            performance_monitor.unregister_extension(extension_id)

            # Drop extension database tables
            extension_db_manager.drop_extension_database(extension_id)

            # Remove from tracking
            if extension_id in self.extension_contexts:
                del self.extension_contexts[extension_id]
            if extension_id in self.loaded_extensions:
                del self.loaded_extensions[extension_id]
            if extension_id in self.extension_modules:
                del self.extension_modules[extension_id]

            return True

        except Exception as e:
            print(f"Error cleaning up extension {extension_id}: {e}")
            return False

    def get_extension_context(self, extension_id: str) -> Optional[ExtensionContext]:
        """Get the context for an extension"""
        return self.extension_contexts.get(extension_id)

    def is_extension_loaded(self, extension_id: str) -> bool:
        """Check if an extension is loaded"""
        return extension_id in self.loaded_extensions

    def list_loaded_extensions(self) -> List[str]:
        """List all loaded extensions"""
        return list(self.loaded_extensions.keys())


# Global extension manager instance
extension_manager = ExtensionManager()