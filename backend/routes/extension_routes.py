from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import os
import json
import zipfile
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from backend.database import get_db
from backend.utils.auth_dep import require_user
from backend.db.extension import Extension
from backend.db.extension_multilingual import ExtensionMultilingualContent
from backend.schemas.extension import ExtensionSchema, ExtensionCreate, ExtensionUpdate, ExtensionManifest
try:
    from backend.utils.extension_security import security_manager, permission_manager
    from backend.utils.extension_manager import extension_manager
    from backend.utils.extension_sandbox import extension_sandbox
    from backend.utils.extension_dependencies import dependency_resolver, version_manager
    from backend.utils.extension_monitoring import performance_monitor, record_extension_request
except ImportError:
    # Create dummy objects if security module is not available
    class DummySecurityManager:
        def validate_extension_package(self, path): return {}
        def quarantine_extension(self, path, reason): pass
        def calculate_extension_hash(self, path): return "dummy_hash"

    class DummyPermissionManager:
        def validate_manifest_permissions(self, manifest): return []

    class DummyVersionManager:
        def validate_extension_version(self, version): return True

    class DummyDependencyResolver:
        def resolve_dependencies(self, extension_id, dependencies): return {'can_install': True, 'unresolved': [], 'conflicts': []}

    security_manager = DummySecurityManager()
    permission_manager = DummyPermissionManager()
    version_manager = DummyVersionManager()
    dependency_resolver = DummyDependencyResolver()

router = APIRouter()

EXTENSIONS_DIR = Path("backend/extensions")
EXTENSIONS_DIR.mkdir(parents=True, exist_ok=True)

def validate_extension_file(file_path: Path) -> ExtensionManifest:
    """Validate extension file and extract manifest"""
    if not zipfile.is_zipfile(file_path):
        raise HTTPException(status_code=400, detail="Extension must be a valid ZIP file")

    with zipfile.ZipFile(file_path, 'r') as zip_ref:
        # Check for manifest.json
        if 'manifest.json' not in zip_ref.namelist():
            raise HTTPException(status_code=400, detail="Extension must contain manifest.json")

        # Extract and validate manifest
        with zip_ref.open('manifest.json') as f:
            try:
                manifest_data = json.load(f)
                manifest = ExtensionManifest(**manifest_data)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid manifest.json: {str(e)}")

        # Validate extension type
        if manifest.type not in ['widget', 'theme', 'backend-api', 'extension', 'language']:
            raise HTTPException(status_code=400, detail=f"Unsupported extension type: {manifest.type}")

        # Validate version format
        if not version_manager.validate_extension_version(manifest.version):
            raise HTTPException(status_code=400, detail=f"Invalid version format: {manifest.version}. Must follow semantic versioning.")

        # Check dependencies if specified
        if hasattr(manifest, 'dependencies') and manifest.dependencies:
            dep_resolution = dependency_resolver.resolve_dependencies(
                f"{manifest.name}_{manifest.version}",
                manifest.dependencies
            )

            if not dep_resolution['can_install']:
                error_msg = "Dependency resolution failed:\n"
                if dep_resolution['unresolved']:
                    error_msg += f"Unresolved dependencies: {dep_resolution['unresolved']}\n"
                if dep_resolution['conflicts']:
                    error_msg += f"Version conflicts: {dep_resolution['conflicts']}"
                raise HTTPException(status_code=400, detail=error_msg)

        # For widgets, check for required frontend files
        if manifest.type == 'widget':
            if not manifest.frontend_entry:
                raise HTTPException(status_code=400, detail="Widget extensions must specify frontend_entry")
            # Check if frontend_entry exists (could be in frontend/ directory, flattened, or already in extension structure)
            frontend_entry_found = (
                manifest.frontend_entry in zip_ref.namelist() or
                f"frontend/{manifest.frontend_entry}" in zip_ref.namelist() or
                f"frontend/src/extensions/{manifest.name}_{manifest.version}/{manifest.frontend_entry}" in zip_ref.namelist()
            )
            if not frontend_entry_found:
                raise HTTPException(status_code=400, detail=f"Widget entry file {manifest.frontend_entry} not found in extension")
            # Check for optional editor file
            if manifest.frontend_editor:
                frontend_editor_found = (
                    manifest.frontend_editor in zip_ref.namelist() or
                    f"frontend/{manifest.frontend_editor}" in zip_ref.namelist() or
                    f"frontend/src/extensions/{manifest.name}_{manifest.version}/{manifest.frontend_editor}" in zip_ref.namelist()
                )
                if not frontend_editor_found:
                    raise HTTPException(status_code=400, detail=f"Widget editor file {manifest.frontend_editor} not found in extension")

        # Check for backend entry file if specified
        if hasattr(manifest, 'backend_entry') and manifest.backend_entry:
            # Check if backend_entry exists (could be in backend/ directory, flattened, or already in extension structure)
            backend_entry_found = (
                manifest.backend_entry in zip_ref.namelist() or
                f"backend/{manifest.backend_entry}" in zip_ref.namelist() or
                f"backend/extensions/{manifest.name}_{manifest.version}/{manifest.backend_entry}" in zip_ref.namelist()
            )
            if not backend_entry_found:
                raise HTTPException(status_code=400, detail=f"Backend entry file {manifest.backend_entry} not found in extension")

        # Validate locales configuration if present
        if hasattr(manifest, 'locales') and manifest.locales:
            locales_config = manifest.locales
            if not isinstance(locales_config, dict):
                raise HTTPException(status_code=400, detail="locales must be an object")

            # Check for required fields
            if 'supported' not in locales_config:
                raise HTTPException(status_code=400, detail="locales.supported is required")
            if not isinstance(locales_config['supported'], list):
                raise HTTPException(status_code=400, detail="locales.supported must be an array of language codes")

            # Validate default language is in supported list
            default_lang = locales_config.get('default', 'en')
            if default_lang not in locales_config['supported']:
                raise HTTPException(status_code=400, detail=f"locales.default '{default_lang}' must be in locales.supported")

            # Check locales directory exists and contains required files
            locales_dir = locales_config.get('directory', 'locales/')
            if not locales_dir.endswith('/'):
                locales_dir += '/'

            required_files = [f"{locales_dir}{lang}.json" for lang in locales_config['supported']]
            missing_files = []
            for file_path in required_files:
                if file_path not in zip_ref.namelist():
                    missing_files.append(file_path)

            if missing_files:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing locale files: {', '.join(missing_files)}"
                )

        # Validate multilingual configuration if present
        if hasattr(manifest, 'multilingual') and manifest.multilingual:
            multilingual_config = manifest.multilingual
            if not isinstance(multilingual_config, dict):
                raise HTTPException(status_code=400, detail="multilingual must be an object")

            # Check for content_fields
            if 'content_fields' in multilingual_config:
                if not isinstance(multilingual_config['content_fields'], list):
                    raise HTTPException(status_code=400, detail="multilingual.content_fields must be an array")

    return manifest

@router.get("/api/extensions/security-report/{extension_id}")
def get_extension_security_report(
    extension_id: int,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Get security analysis report for an extension"""
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)

    extension = db.query(Extension).filter(
        Extension.id == extension_id,
        Extension.user_id == user_id
    ).first()
    if not extension:
        raise HTTPException(status_code=404, detail="Extension not found")

    extension_dir = Path(extension.file_path)
    if not extension_dir.exists():
        raise HTTPException(status_code=404, detail="Extension files not found")

    # Re-run security analysis
    security_report = security_manager.validate_extension_package(extension_dir)

    return {
        "extension_id": extension_id,
        "extension_name": extension.name,
        "security_status": extension.security_status,
        "report": security_report,
        "integrity_hash": extension.integrity_hash
    }

@router.post("/api/extensions/approve/{extension_id}")
def approve_extension(
    extension_id: int,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Manually approve a quarantined extension (admin only)"""
    user_id = claims.get("sub") or claims.get("user_id")
    user_role = claims.get("role", "user")

    if user_role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    extension = db.query(Extension).filter(Extension.id == extension_id).first()
    if not extension:
        raise HTTPException(status_code=404, detail="Extension not found")

    if extension.status != "quarantined":
        raise HTTPException(status_code=400, detail="Extension is not quarantined")

    # Move from quarantine back to user directory
    quarantine_path = Path("backend/extensions/quarantine") / f"user_{extension.user_id}" / f"{extension.name}_{extension.version}"
    user_path = Path("backend/extensions") / f"user_{extension.user_id}" / f"{extension.name}_{extension.version}"

    if quarantine_path.exists():
        user_path.parent.mkdir(parents=True, exist_ok=True)
        quarantine_path.rename(user_path)

    extension.status = "inactive"
    extension.security_status = "warning"  # Mark as manually approved
    db.commit()

    return {"message": "Extension approved and restored"}

@router.post("/api/extensions/quarantine/{extension_id}")
def quarantine_extension_endpoint(
    extension_id: int,
    reason: str = Form(...),
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Manually quarantine an extension"""
    user_id = claims.get("sub") or claims.get("user_id")
    user_role = claims.get("role", "")

    if user_role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    extension = db.query(Extension).filter(Extension.id == extension_id).first()
    if not extension:
        raise HTTPException(status_code=404, detail="Extension not found")

    extension_dir = Path(extension.file_path)
    if extension_dir.exists():
        security_manager.quarantine_extension(extension_dir, reason)

    extension.status = "quarantined"
    extension.security_status = "quarantined"
    extension.error_message = reason
    db.commit()

    return {"message": "Extension quarantined"}

@router.get("/api/extensions")
def list_extensions(
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)

    extensions = db.query(Extension).filter(Extension.user_id == user_id).all()
    return {"items": [ExtensionSchema.from_orm(ext) for ext in extensions]}

@router.get("/api/extensions/public")
def list_public_extensions(
    db: Session = Depends(get_db)
):
    """Get public extension metadata needed for routing (no auth required)"""
    # Return only enabled extensions with frontend routes
    extensions = db.query(Extension).filter(Extension.is_enabled == True).all()

    public_extensions = []
    for ext in extensions:
        # Try to read manifest from file system first (more up-to-date)
        manifest_path = f"backend/extensions/{ext.name}_{ext.version}/manifest.json"
        manifest_data = None

        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"DEBUG: Could not load manifest from file for {ext.name}_{ext.version}: {e}")
            # Fall back to stored manifest
            manifest_data = ext.manifest


        if isinstance(manifest_data, dict):
            # Only include extensions that have frontend routes or entry
            if manifest_data.get('frontend_routes') or manifest_data.get('frontend_entry'):
                public_extensions.append({
                    "id": ext.id,
                    "name": ext.name,
                    "version": ext.version,
                    "type": ext.type,
                    "frontend_routes": manifest_data.get('frontend_routes', []),
                    "frontend_entry": manifest_data.get('frontend_entry'),
                    "frontend_components": manifest_data.get('frontend_components', [])
                })
            else:
                print(f"DEBUG: Extension {ext.name} has no frontend routes or entry")
        else:
            print(f"DEBUG: Extension {ext.name} manifest is not a dict: {manifest_data}")

    return {"items": public_extensions}

@router.post("/api/extensions/upload")
async def upload_extension(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    print(f"DEBUG: Starting extension upload for file: {file.filename}")
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)
    print(f"DEBUG: User ID: {user_id}")

    # Validate file type
    if not file.filename or not file.filename.endswith('.zip'):
        print(f"DEBUG: Invalid file type: {file.filename}")
        raise HTTPException(status_code=400, detail="Extension must be a ZIP file")

    # Check file size (limit to 10MB)
    file_size = 0
    content = await file.read()
    file_size = len(content)
    print(f"DEBUG: File size: {file_size} bytes")
    if file_size > 10 * 1024 * 1024:  # 10MB limit
        print(f"DEBUG: File too large: {file_size}")
        raise HTTPException(status_code=400, detail="Extension file too large (max 10MB)")

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_file:
        temp_file.write(content)
        temp_path = Path(temp_file.name)
    print(f"DEBUG: Temp file saved at: {temp_path}")

    try:
        # Validate extension
        print(f"DEBUG: Validating extension file")
        manifest = validate_extension_file(temp_path)
        print(f"DEBUG: Manifest validated: {manifest.name} v{manifest.version}")

        # Check if extension with same name/version already exists for user
        print(f"DEBUG: Checking for existing extension: {manifest.name} v{manifest.version}")
        existing = db.query(Extension).filter(
            Extension.user_id == user_id,
            Extension.name == manifest.name,
            Extension.version == manifest.version
        ).first()
        if existing:
            print(f"DEBUG: Extension already exists")
            raise HTTPException(status_code=400, detail="Extension with this name and version already exists")

        # Create extension directory
        extension_dir = EXTENSIONS_DIR / f"{manifest.name}_{manifest.version}"
        print(f"DEBUG: Creating extension directory: {extension_dir}")
        extension_dir.mkdir(parents=True, exist_ok=True)

        # Extract extension files, keeping only backend-relevant files
        print(f"DEBUG: Extracting extension files")
        with zipfile.ZipFile(temp_path, 'r') as zip_ref:
            print(f"DEBUG: ZIP file opened, {len(zip_ref.filelist)} files")
            # Security: Check for dangerous files
            for file_info in zip_ref.filelist:
                if '..' in file_info.filename or file_info.filename.startswith('/'):
                    print(f"DEBUG: Dangerous file path detected: {file_info.filename}")
                    raise HTTPException(status_code=400, detail="Extension contains invalid file paths")

            # Extract only non-frontend files, and flatten backend directory
            extracted_count = 0
            for file_info in zip_ref.filelist:
                # Skip frontend directory and its contents (handled separately below)
                if file_info.filename.startswith('frontend/'):
                    continue

                # Flatten backend directory structure
                if file_info.filename.startswith('backend/'):
                    # Remove 'backend/' prefix to flatten the structure
                    flattened_path = file_info.filename[len('backend/'):]
                    if flattened_path and not flattened_path.endswith('/'):  # Skip directory entries
                        extract_path = extension_dir / flattened_path
                        extract_path.parent.mkdir(parents=True, exist_ok=True)
                        with zip_ref.open(file_info) as src, open(extract_path, 'wb') as dst:
                            dst.write(src.read())
                        extracted_count += 1
                    elif flattened_path and flattened_path.endswith('/'):
                        # Create directory
                        dir_path = extension_dir / flattened_path.rstrip('/')
                        dir_path.mkdir(parents=True, exist_ok=True)
                elif file_info.filename.startswith(f'backend/extensions/{manifest.name}_{manifest.version}/'):
                    # Handle files that are already in the correct backend extension directory structure
                    # This allows packaging extensions that are already installed/developed in place
                    relative_path = file_info.filename[len(f'backend/extensions/{manifest.name}_{manifest.version}/'):]
                    if relative_path and not relative_path.endswith('/'):  # Skip directory entries
                        extract_path = extension_dir / relative_path
                        extract_path.parent.mkdir(parents=True, exist_ok=True)
                        with zip_ref.open(file_info) as src, open(extract_path, 'wb') as dst:
                            dst.write(src.read())
                        extracted_count += 1
                    elif relative_path and relative_path.endswith('/'):
                        # Create directory
                        dir_path = extension_dir / relative_path.rstrip('/')
                        dir_path.mkdir(parents=True, exist_ok=True)
                else:
                    # Extract other files normally (like manifest.json)
                    zip_ref.extract(file_info, extension_dir)
                    extracted_count += 1
            print(f"DEBUG: Extracted {extracted_count} files to {extension_dir}")

        # For widget and extension type, also copy to frontend extensions directory
        print(f"DEBUG: Copying to frontend extensions directory")
        if manifest.type in ['widget', 'extension', 'language']:
            frontend_extensions_dir = Path("frontend/src/extensions")
            frontend_extensions_dir.mkdir(exist_ok=True)

            # Copy the extension files to frontend
            frontend_extension_dir = frontend_extensions_dir / f"{manifest.name}_{manifest.version}"
            print(f"DEBUG: Frontend extension dir: {frontend_extension_dir}")
            if frontend_extension_dir.exists():
                import shutil
                shutil.rmtree(frontend_extension_dir)
                print(f"DEBUG: Removed existing frontend extension dir")

            # Only copy frontend files (not backend files)
            import shutil
            frontend_extension_dir.mkdir(exist_ok=True)
            print(f"DEBUG: Created frontend extension dir")

            # Copy manifest.json
            manifest_path = extension_dir / "manifest.json"
            if manifest_path.exists():
                shutil.copy2(manifest_path, frontend_extension_dir)
                print(f"DEBUG: Copied manifest.json to frontend")

            # Extract frontend files directly to target directory
            frontend_files_copied = 0
            with zipfile.ZipFile(temp_path, 'r') as zip_ref:
                # First pass: collect all file paths to handle directory conflicts
                frontend_files = []
                locales_files = []
                installed_files = []

                for file_info in zip_ref.filelist:
                    if file_info.filename.startswith('frontend/') and not file_info.filename.startswith('frontend/src/extensions/'):
                        frontend_files.append(file_info)
                    elif file_info.filename.startswith('locales/') and hasattr(manifest, 'locales') and manifest.locales:
                        locales_files.append(file_info)
                    elif file_info.filename.startswith(f'frontend/src/extensions/{manifest.name}_{manifest.version}/'):
                        installed_files.append(file_info)

                # Process frontend files
                for file_info in frontend_files:
                    relative_path = file_info.filename[len('frontend/'):]
                    if relative_path and not relative_path.endswith('/'):  # Only process actual files
                        target_path = frontend_extension_dir / relative_path
                        # If target path exists as a file but we need it as a directory, remove the file
                        if target_path.exists() and target_path.is_file() and target_path.parent != target_path:
                            target_path.unlink()
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        with zip_ref.open(file_info) as src, open(target_path, 'wb') as dst:
                            dst.write(src.read())
                        frontend_files_copied += 1

                # Process locales files
                for file_info in locales_files:
                    relative_path = file_info.filename[len('locales/'):]
                    if relative_path and not relative_path.endswith('/'):
                        locales_target = frontend_extension_dir / 'locales'
                        locales_target.mkdir(parents=True, exist_ok=True)
                        target_path = locales_target / relative_path
                        if target_path.exists() and target_path.is_file() and target_path.parent != target_path:
                            target_path.unlink()
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        with zip_ref.open(file_info) as src, open(target_path, 'wb') as dst:
                            dst.write(src.read())
                        frontend_files_copied += 1

                # Process installed files
                for file_info in installed_files:
                    relative_path = file_info.filename[len(f'frontend/src/extensions/{manifest.name}_{manifest.version}/'):]
                    if relative_path and not relative_path.endswith('/'):
                        target_path = frontend_extension_dir / relative_path
                        if target_path.exists() and target_path.is_file() and target_path.parent != target_path:
                            target_path.unlink()
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        with zip_ref.open(file_info) as src, open(target_path, 'wb') as dst:
                            dst.write(src.read())
                        frontend_files_copied += 1

            print(f"DEBUG: Copied {frontend_files_copied} frontend files")

        # For extensions with backend entry, initialize the backend module
        if hasattr(manifest, 'backend_entry') and manifest.backend_entry:
            print(f"DEBUG: Initializing backend for extension {manifest.name}")
            try:
                # Create sandbox environment based on permissions
                permissions = manifest.permissions or []
                print(f"DEBUG: Creating sandbox environment with permissions: {permissions}")
                sandbox_env = extension_sandbox.create_environment(
                    extension_id=f"{manifest.name}_{manifest.version}",
                    permissions=permissions
                )
                print(f"DEBUG: Sandbox environment created")

                # Get database session for extension initialization
                print(f"DEBUG: Getting database session for initialization")
                db_session = next(get_db())
                from backend.main import app
                print(f"DEBUG: Calling extension_manager.initialize_extension")
                success = extension_manager.initialize_extension(
                    extension_id=f"{manifest.name}_{manifest.version}",
                    extension_path=extension_dir,
                    app=app,
                    db=db_session
                )
                if success:
                    print(f"Extension {manifest.name} backend initialized successfully")
                else:
                    print(f"Warning: Failed to initialize backend for extension {manifest.name}")
            except Exception as e:
                print(f"Error initializing backend for extension {manifest.name}: {e}")
                import traceback
                traceback.print_exc()
                # Continue with installation even if backend initialization fails

        # Perform security analysis (skip if dummy)
        print(f"DEBUG: Starting security analysis")
        if hasattr(security_manager, 'validate_extension_package'):
            print(f"DEBUG: About to validate extension package at {extension_dir}")
            try:
                security_report = security_manager.validate_extension_package(extension_dir)
                print(f"DEBUG: Security report: {security_report}")
            except Exception as sec_error:
                print(f"DEBUG: Security validation error: {sec_error}")
                security_report = {'critical': [str(sec_error)]}

            # Check for critical security issues
            if security_report and 'critical' in security_report and security_report['critical']:
                # Quarantine the extension
                print(f"DEBUG: Critical security issues found: {security_report['critical']}")
                security_manager.quarantine_extension(extension_dir, f"Security violations: {security_report['critical']}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Extension contains security violations: {', '.join(security_report['critical'])}"
                )

            # Check permissions
            print(f"DEBUG: Checking permissions")
            try:
                permission_issues = permission_manager.validate_manifest_permissions(manifest.dict())
                print(f"DEBUG: Permission issues: {permission_issues}, type: {type(permission_issues)}")
                if permission_issues and len(permission_issues) > 0:
                    print(f"DEBUG: Permission issues found: {permission_issues}")
                    security_manager.quarantine_extension(extension_dir, f"Permission issues: {permission_issues}")
                    raise HTTPException(
                        status_code=400,
                        detail=f"Extension requests dangerous permissions: {', '.join(permission_issues)}"
                    )
                else:
                    print("DEBUG: No permission issues found")
            except Exception as perm_error:
                print(f"DEBUG: Permission check error: {perm_error}")
                # Continue without permission check if it fails

            # Calculate integrity hash
            try:
                integrity_hash = security_manager.calculate_extension_hash(extension_dir)
                print(f"DEBUG: Integrity hash: {integrity_hash}")
            except Exception as hash_error:
                print(f"DEBUG: Hash calculation error: {hash_error}")
                integrity_hash = "error_hash"
        else:
            # Dummy security manager
            print(f"DEBUG: Using dummy security manager")
            security_report = {}
            integrity_hash = "dummy_hash"

        # Register extension for monitoring
        print(f"DEBUG: Registering extension for monitoring")
        try:
            performance_monitor.register_extension(f"{manifest.name}_{manifest.version}")
        except Exception as mon_error:
            print(f"DEBUG: Monitoring registration error: {mon_error}")

        # Register extension version
        print(f"DEBUG: Registering extension version")
        try:
            version_manager.register_extension(f"{manifest.name}_{manifest.version}", manifest.version)
        except Exception as ver_error:
            print(f"DEBUG: Version registration error: {ver_error}")

        # Save to database
        print(f"DEBUG: Creating extension record with security_status: {'safe' if not security_report.get('warnings', []) else 'warning'}")
        extension = Extension(
            user_id=user_id,
            name=manifest.name,
            type=manifest.type,
            version=manifest.version,
            description=manifest.description,
            author=manifest.author,
            manifest=manifest.dict(),
            file_path=str(extension_dir),
            integrity_hash=integrity_hash,
            security_status="safe" if not security_report.get('warnings', []) else "warning",
            status="inactive",
            is_enabled=False
        )
        print(f"DEBUG: Extension object created: {extension.name}")
        try:
            db.add(extension)
            print(f"DEBUG: Committing to database")
            db.commit()
            db.refresh(extension)
            print(f"DEBUG: Database commit successful")
        except Exception as db_error:
            print(f"DEBUG: Database error: {db_error}")
            db.rollback()
            raise

        print(f"DEBUG: Returning extension schema: {extension.id}")
        return ExtensionSchema.from_orm(extension)

    except Exception as e:
        print(f"DEBUG: Unexpected error in upload_extension: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    finally:
        # Clean up temp file
        temp_path.unlink(missing_ok=True)

@router.patch("/api/extensions/{extension_id}")
def update_extension(
    extension_id: int,
    payload: ExtensionUpdate,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    try:
        user_id = claims.get("sub") or claims.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        user_id = int(user_id)

        extension = db.query(Extension).filter(
            Extension.id == extension_id,
            Extension.user_id == user_id
        ).first()
        if not extension:
            raise HTTPException(status_code=404, detail="Extension not found")

        # Store original state for logging
        was_enabled = extension.is_enabled
        extension_full_id = f"{extension.name}_{extension.version}"

        if payload.is_enabled is not None:
            extension.is_enabled = payload.is_enabled
            extension.status = "active" if payload.is_enabled else "inactive"

            # Handle extension lifecycle
            if payload.is_enabled:
                # Enable extension - initialize backend if present
                try:
                    manifest_data = extension.manifest
                    if isinstance(manifest_data, dict) and manifest_data.get('backend_entry'):
                        from backend.main import app
                        success = extension_manager.initialize_extension(
                            extension_id=extension_full_id,
                            extension_path=Path(extension.file_path),
                            app=app,
                            db=db
                        )
                        if not success:
                            extension.status = "error"
                            extension.error_message = "Failed to initialize backend"
                        else:
                            print(f"Extension {extension_full_id} initialized successfully")
                
                except Exception as e:
                    print(f"Error initializing extension {extension_full_id}: {e}")
                    extension.status = "error"
                    extension.error_message = f"Initialization error: {str(e)}"
                
                # Special handling for language pack extensions
                try:
                    manifest_data = extension.manifest
                    if isinstance(manifest_data, dict) and manifest_data.get('type') == 'language':
                        from backend.db.language_pack import LanguagePack
                        
                        # Check if language pack already exists
                        existing_lang_pack = db.query(LanguagePack).filter(
                            LanguagePack.extension_id == extension.id
                        ).first()
                        
                        if not existing_lang_pack:
                            # Create new language pack
                            language_pack = LanguagePack.from_manifest(manifest_data, extension.id)
                            
                            # Load translations from backend and frontend directories
                            extension_path = Path(extension.file_path)
                            backend_dir = extension_path / "backend"
                            frontend_dir = extension_path / "frontend"
                            
                            # Load backend translations (language_routes.json, user.json, etc.)
                            if backend_dir.exists():
                                import json
                                backend_translations = {}
                                for json_file in backend_dir.glob("*.json"):
                                    try:
                                        with open(json_file, 'r', encoding='utf-8') as f:
                                            data = json.load(f)
                                            backend_translations[json_file.stem] = data
                                    except Exception as e:
                                        print(f"Error loading backend translation file {json_file}: {e}")
                                language_pack.backend_translations = backend_translations
                            
                            # Load frontend translations (Login.json, Register.json, etc.)
                            if frontend_dir.exists():
                                import json
                                frontend_translations = {}
                                for json_file in frontend_dir.glob("*.json"):
                                    try:
                                        with open(json_file, 'r', encoding='utf-8') as f:
                                            data = json.load(f)
                                            frontend_translations[json_file.stem] = data
                                    except Exception as e:
                                        print(f"Error loading frontend translation file {json_file}: {e}")
                                language_pack.frontend_translations = frontend_translations
                            
                            # Extract language info from manifest
                            lang_info = manifest_data.get("language", {})
                            language_pack.name = lang_info.get("name", extension.name)
                            language_pack.code = lang_info.get("code", "bg")
                            language_pack.native_name = lang_info.get("nativeName", lang_info.get("name", "Bulgarian"))
                            language_pack.locale = lang_info.get("locale", "bg-BG")
                            language_pack.direction = lang_info.get("direction", "ltr")
                            language_pack.currency = lang_info.get("currency", "BGN")
                            language_pack.date_format = lang_info.get("dateFormat")
                            language_pack.time_format = lang_info.get("timeFormat")
                            language_pack.number_format = lang_info.get("numberFormat")
                            
                            # Set coverage from manifest
                            coverage = manifest_data.get("coverage", {})
                            language_pack.frontend_coverage = coverage.get("frontend", 0)
                            language_pack.backend_coverage = coverage.get("backend", 0)
                            language_pack.extensions_coverage = coverage.get("extensions", 0)
                            
                            # Set as active and default
                            language_pack.is_active = True
                            language_pack.is_default = (language_pack.code == 'bg')  # Make Bulgarian default for now
                            
                            db.add(language_pack)
                            db.commit()
                            db.refresh(language_pack)
                            print(f"Language pack '{language_pack.name}' created successfully")
                        else:
                            # Update existing language pack to active
                            existing_lang_pack.is_active = True
                            db.commit()
                            print(f"Language pack '{existing_lang_pack.name}' activated")
                        
                except Exception as e:
                    print(f"Error creating language pack: {e}")
                    extension.status = "error"
                    extension.error_message = f"Failed to install language pack: {str(e)}"
            else:
                # Disable extension - cleanup backend
                try:
                    # Get manifest data for language pack check
                    manifest_data = extension.manifest
                    
                    extension_manager.cleanup_extension(extension_full_id)
                    print(f"Extension {extension_full_id} cleaned up successfully")
                except Exception as e:
                    print(f"Warning: Error cleaning up extension {extension_full_id}: {e}")
                    # Don't fail the entire operation for cleanup errors
                    extension.error_message = f"Extension cleanup warning: {str(e)}"
                
                # Special handling for language pack extensions
                try:
                    manifest_data = extension.manifest
                    if isinstance(manifest_data, dict) and manifest_data.get('type') == 'language':
                        from backend.db.language_pack import LanguagePack
                        
                        # Deactivate language pack
                        language_pack = db.query(LanguagePack).filter(
                            LanguagePack.extension_id == extension.id
                        ).first()
                        
                        if language_pack:
                            language_pack.is_active = False
                            db.commit()
                            print(f"Language pack '{language_pack.name}' deactivated")
                        
                except Exception as e:
                    print(f"Error deactivating language pack: {e}")
                    # Don't fail the entire operation for language pack errors
                    extension.error_message = f"Language pack deactivation error: {str(e)}"

        db.commit()
        db.refresh(extension)
        
        print(f"Extension {extension_full_id} {'enabled' if extension.is_enabled else 'disabled'} successfully")
        return ExtensionSchema.from_orm(extension)

    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        print(f"Unexpected error in update_extension for extension {extension_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.delete("/api/extensions/{extension_id}")
def delete_extension(
    extension_id: int,
    deleteData: bool = False,
    deleteFiles: bool = False,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)

    extension = db.query(Extension).filter(
        Extension.id == extension_id,
        Extension.user_id == user_id
    ).first()
    if not extension:
        raise HTTPException(status_code=404, detail="Extension not found")

    print(f"DEBUG: Starting deletion of extension {extension_id} ({extension.name}_{extension.version})")

    try:
        # Cleanup extension backend before deletion
        extension_full_id = f"{extension.name}_{extension.version}"
        print(f"DEBUG: Cleaning up extension backend for {extension_full_id}")
        cleanup_result = extension_manager.cleanup_extension(extension_full_id)
        print(f"DEBUG: Cleanup result: {cleanup_result}")

        # Check for widgets using this extension
        from backend.db.widget import Widget
        widgets_using_extension = db.query(Widget).filter(
            Widget.type.like(f"extension:{extension_id}")
        ).all()
        if widgets_using_extension:
            print(f"DEBUG: Found {len(widgets_using_extension)} widgets using this extension")

        # Drop database tables if requested and extension has tables
        if deleteData and extension.type == 'extension':
            try:
                print(f"DEBUG: Dropping database tables for extension {extension_full_id}")
                # Get all tables that start with the extension prefix
                from backend.db.base import Base
                from sqlalchemy import text

                # Query for tables with the extension prefix
                # Use lowercase extension name to match table creation pattern
                result = db.execute(text("""
                    SELECT tablename FROM pg_tables
                    WHERE schemaname = 'public'
                    AND tablename LIKE :prefix
                """), {"prefix": f"ext_{extension.name.lower()}%"})

                tables_to_drop = [row[0] for row in result.fetchall()]
                print(f"DEBUG: Found tables to drop: {tables_to_drop}")

                # Drop each table
                for table_name in tables_to_drop:
                    try:
                        db.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE'))
                        print(f"DEBUG: Dropped table {table_name}")
                    except Exception as e:
                        print(f"DEBUG: Error dropping table {table_name}: {e}")

                db.commit()
                print(f"DEBUG: Database tables dropped successfully")
            except Exception as e:
                print(f"DEBUG: Error dropping database tables: {e}")
                db.rollback()

        # Remove extension files from backend
        extension_path = Path(extension.file_path)
        print(f"DEBUG: Checking backend extension path: {extension_path}")
        if extension_path.exists():
            print(f"DEBUG: Removing backend extension files")
            shutil.rmtree(extension_path)
            print(f"DEBUG: Backend files removed")
        else:
            print(f"DEBUG: Backend extension path does not exist")

        # Remove extension files from frontend if it's a widget, extension, or language
        if extension.type in ['widget', 'extension', 'language']:
            frontend_extensions_dir = Path("frontend/src/extensions")
            frontend_extension_dir = frontend_extensions_dir / f"{extension.name}_{extension.version}"
            print(f"DEBUG: Checking frontend extension path: {frontend_extension_dir}")
            if frontend_extension_dir.exists():
                print(f"DEBUG: Removing frontend extension files")
                shutil.rmtree(frontend_extension_dir)
                print(f"DEBUG: Frontend files removed")
            else:
                print(f"DEBUG: Frontend extension path does not exist")

        # Remove uploaded files for extensions that upload files (like StoreExtension)
        if extension.type == 'extension' and deleteFiles:
            # Determine upload directory name - typically lowercase extension name without "Extension"
            upload_dir_name = extension.name.replace('Extension', '').lower()
            uploads_dir = Path("uploads") / upload_dir_name
            print(f"DEBUG: Checking uploads directory: {uploads_dir}")
            if uploads_dir.exists():
                print(f"DEBUG: Removing uploaded files for extension")
                shutil.rmtree(uploads_dir)
                print(f"DEBUG: Uploaded files removed")
            else:
                print(f"DEBUG: Uploads directory does not exist")

        # Remove language pack record if this is a language extension
        if extension.type == 'language':
            print(f"DEBUG: Extension type is 'language' ({extension.name}), checking for language pack record")
            try:
                from backend.db.language_pack import LanguagePack

                # First, try to find by extension_id
                language_pack = db.query(LanguagePack).filter(
                    LanguagePack.extension_id == extension.id
                ).first()

                if language_pack:
                    print(f"DEBUG: Found language pack '{language_pack.name}' (ID: {language_pack.id}) by extension_id, removing...")
                    db.delete(language_pack)
                    db.commit()  # Commit immediately to avoid rollback issues
                    print(f"DEBUG: Language pack removed from database")
                else:
                    print(f"DEBUG: No language pack found by extension_id {extension.id}, trying by name '{extension.name}'...")

                    # If not found by extension_id, try by name (for orphaned records)
                    # Try exact match first
                    language_pack = db.query(LanguagePack).filter(
                        LanguagePack.name == extension.name
                    ).first()

                    if language_pack:
                        print(f"DEBUG: Found language pack '{language_pack.name}' (ID: {language_pack.id}) by exact name match, removing...")
                        db.delete(language_pack)
                        db.commit()  # Commit immediately
                        print(f"DEBUG: Language pack removed from database")
                    else:
                        # Try case-insensitive match
                        language_pack = db.query(LanguagePack).filter(
                            LanguagePack.name.ilike(extension.name)
                        ).first()

                        if language_pack:
                            print(f"DEBUG: Found language pack '{language_pack.name}' (ID: {language_pack.id}) by case-insensitive name match, removing...")
                            db.delete(language_pack)
                            db.commit()  # Commit immediately
                            print(f"DEBUG: Language pack removed from database")
                        else:
                            print(f"DEBUG: No language pack found for extension {extension.name}")

                # Also check for orphaned language pack records (in case extension was partially deleted)
                orphaned_packs = db.query(LanguagePack).filter(
                    LanguagePack.extension_id.isnot(None),
                    ~LanguagePack.extension_id.in_(
                        db.query(Extension.id).subquery()
                    )
                ).all()

                if orphaned_packs:
                    print(f"DEBUG: Found {len(orphaned_packs)} orphaned language pack records, cleaning up...")
                    for pack in orphaned_packs:
                        print(f"DEBUG: Removing orphaned language pack '{pack.name}' (ID: {pack.id})")
                        db.delete(pack)
                    db.commit()  # Commit orphaned cleanup
                    print(f"DEBUG: Orphaned language packs cleaned up")

            except Exception as e:
                print(f"DEBUG: Error removing language pack: {e}")
                import traceback
                traceback.print_exc()
                db.rollback()  # Rollback on error

        # Remove from database
        print(f"DEBUG: Deleting extension record from database")
        db.delete(extension)
        print(f"DEBUG: Committing database changes")
        db.commit()
        print(f"DEBUG: Extension {extension_id} successfully deleted")
        return {"message": "Extension deleted"}

    except Exception as e:
        db.rollback()
        print(f"DEBUG: Error deleting extension {extension_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to delete extension: {str(e)}")

@router.get("/api/extensions/widgets")
def list_widget_extensions(
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Get all enabled widget extensions for the current user"""
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)

    extensions = db.query(Extension).filter(
        Extension.user_id == user_id,
        Extension.type == "widget",
        Extension.is_enabled == True
    ).all()

    widgets = []
    for ext in extensions:
        manifest_data = ext.manifest
        if isinstance(manifest_data, dict):
            widgets.append({
                "id": ext.id,
                "name": ext.name,
                "version": ext.version,
                "description": ext.description,
                "author": ext.author,
                "frontend_entry": manifest_data.get("frontend_entry"),
                "frontend_editor": manifest_data.get("frontend_editor"),
                "config_schema": manifest_data.get("config_schema", {}),
                "file_path": ext.file_path
            })

    return {"items": widgets}

@router.get("/api/extensions/files/{path:path}")
async def serve_extension_file(path: str):
    """Serve extension files statically"""
    # Security: Validate path to prevent directory traversal
    if '..' in path or path.startswith('/'):
        raise HTTPException(status_code=403, detail="Invalid path")

    # Construct full path - extensions are stored in frontend/src/extensions/
    # The path is relative to the frontend directory for frontend extensions
    full_path = Path(__file__).parent.parent.parent / "frontend" / "src" / "extensions" / path

    # Check if file exists
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # Security: Only allow access to .vue, .js, .ts, .json, .css files
    allowed_extensions = {'.vue', '.js', '.ts', '.json', '.css', '.scss'}
    if full_path.suffix.lower() not in allowed_extensions:
        raise HTTPException(status_code=403, detail="File type not allowed")

    # Return file content with proper MIME type for JavaScript modules
    from fastapi.responses import Response
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Serve as JavaScript module for dynamic imports
        return Response(content, media_type="application/javascript")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")


# Multilingual Content Endpoints

@router.get("/api/extensions/{extension_id}/content/{content_key}")
def get_multilingual_content(
    extension_id: int,
    content_key: str,
    language_code: str = None,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Get multilingual content for an extension"""
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)

    # Verify extension ownership
    extension = db.query(Extension).filter(
        Extension.id == extension_id,
        Extension.user_id == user_id
    ).first()
    if not extension:
        raise HTTPException(status_code=404, detail="Extension not found")

    # Get content for specific language or all languages
    query = db.query(ExtensionMultilingualContent).filter(
        ExtensionMultilingualContent.extension_id == extension_id,
        ExtensionMultilingualContent.content_key == content_key
    )

    if language_code:
        query = query.filter(ExtensionMultilingualContent.language_code == language_code)

    content_items = query.all()

    if language_code and not content_items:
        return {"content": {}, "language_code": language_code}

    result = {}
    for item in content_items:
        result[item.language_code] = item.content_data

    return {
        "extension_id": extension_id,
        "content_key": content_key,
        "content": result
    }


@router.post("/api/extensions/{extension_id}/content/{content_key}")
def save_multilingual_content(
    extension_id: int,
    content_key: str,
    content_data: Dict[str, Any],
    language_code: str,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Save multilingual content for an extension"""
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)

    # Verify extension ownership
    extension = db.query(Extension).filter(
        Extension.id == extension_id,
        Extension.user_id == user_id
    ).first()
    if not extension:
        raise HTTPException(status_code=404, detail="Extension not found")

    # Check if extension supports multilingual content
    manifest = extension.manifest
    if not (isinstance(manifest, dict) and manifest.get('multilingual')):
        raise HTTPException(status_code=400, detail="Extension does not support multilingual content")

    # Upsert content
    existing = db.query(ExtensionMultilingualContent).filter(
        ExtensionMultilingualContent.extension_id == extension_id,
        ExtensionMultilingualContent.content_key == content_key,
        ExtensionMultilingualContent.language_code == language_code
    ).first()

    if existing:
        existing.content_data = content_data
        existing.updated_at = datetime.utcnow()
    else:
        new_content = ExtensionMultilingualContent(
            extension_id=extension_id,
            content_key=content_key,
            language_code=language_code,
            content_data=content_data
        )
        db.add(new_content)

    db.commit()

    return {
        "message": "Content saved successfully",
        "extension_id": extension_id,
        "content_key": content_key,
        "language_code": language_code
    }


@router.delete("/api/extensions/{extension_id}/content/{content_key}")
def delete_multilingual_content(
    extension_id: int,
    content_key: str,
    language_code: str = None,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Delete multilingual content for an extension"""
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)

    # Verify extension ownership
    extension = db.query(Extension).filter(
        Extension.id == extension_id,
        Extension.user_id == user_id
    ).first()
    if not extension:
        raise HTTPException(status_code=404, detail="Extension not found")

    # Delete content
    query = db.query(ExtensionMultilingualContent).filter(
        ExtensionMultilingualContent.extension_id == extension_id,
        ExtensionMultilingualContent.content_key == content_key
    )

    if language_code:
        query = query.filter(ExtensionMultilingualContent.language_code == language_code)

    deleted_count = query.delete()
    db.commit()

    return {
        "message": f"Deleted {deleted_count} content item(s)",
        "extension_id": extension_id,
        "content_key": content_key
    }