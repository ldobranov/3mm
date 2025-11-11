from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List
import os
import json
import zipfile
import tempfile
import shutil
from pathlib import Path

from backend.database import get_db
from backend.utils.auth_dep import require_user
from backend.db.extension import Extension
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

    security_manager = DummySecurityManager()
    permission_manager = DummyPermissionManager()

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
        if manifest.type not in ['widget', 'theme', 'backend-api', 'extension']:
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
            # Check if frontend_entry exists (could be in frontend/ directory or flattened)
            frontend_entry_found = (
                manifest.frontend_entry in zip_ref.namelist() or
                f"frontend/{manifest.frontend_entry}" in zip_ref.namelist()
            )
            if not frontend_entry_found:
                raise HTTPException(status_code=400, detail=f"Widget entry file {manifest.frontend_entry} not found in extension")
            # Check for optional editor file
            if manifest.frontend_editor:
                frontend_editor_found = (
                    manifest.frontend_editor in zip_ref.namelist() or
                    f"frontend/{manifest.frontend_editor}" in zip_ref.namelist()
                )
                if not frontend_editor_found:
                    raise HTTPException(status_code=400, detail=f"Widget editor file {manifest.frontend_editor} not found in extension")

        # Check for backend entry file if specified
        if hasattr(manifest, 'backend_entry') and manifest.backend_entry:
            # Check if backend_entry exists (could be in backend/ directory or flattened)
            backend_entry_found = (
                manifest.backend_entry in zip_ref.namelist() or
                f"backend/{manifest.backend_entry}" in zip_ref.namelist()
            )
            if not backend_entry_found:
                raise HTTPException(status_code=400, detail=f"Backend entry file {manifest.backend_entry} not found in extension")

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

@router.post("/api/extensions/upload")
async def upload_extension(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)

    # Validate file type
    if not file.filename or not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Extension must be a ZIP file")

    # Check file size (limit to 10MB)
    file_size = 0
    content = await file.read()
    file_size = len(content)
    if file_size > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=400, detail="Extension file too large (max 10MB)")

    # Save uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_file:
        temp_file.write(content)
        temp_path = Path(temp_file.name)

    try:
        # Validate extension
        manifest = validate_extension_file(temp_path)

        # Check if extension with same name/version already exists for user
        existing = db.query(Extension).filter(
            Extension.user_id == user_id,
            Extension.name == manifest.name,
            Extension.version == manifest.version
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Extension with this name and version already exists")

        # Create extension directory
        extension_dir = EXTENSIONS_DIR / f"{manifest.name}_{manifest.version}"
        extension_dir.mkdir(parents=True, exist_ok=True)

        # Extract extension files, keeping only backend-relevant files
        with zipfile.ZipFile(temp_path, 'r') as zip_ref:
            # Security: Check for dangerous files
            for file_info in zip_ref.filelist:
                if '..' in file_info.filename or file_info.filename.startswith('/'):
                    raise HTTPException(status_code=400, detail="Extension contains invalid file paths")

            # Extract only non-frontend files, and flatten backend directory
            for file_info in zip_ref.filelist:
                # Skip frontend directory and its contents
                if file_info.filename.startswith('frontend/'):
                    continue

                # Flatten backend directory structure
                if file_info.filename.startswith('backend/'):
                    # Remove 'backend/' prefix to flatten the structure
                    flattened_path = file_info.filename[len('backend/'):]
                    if flattened_path:  # Skip the directory itself
                        extract_path = extension_dir / flattened_path
                        extract_path.parent.mkdir(parents=True, exist_ok=True)
                        with zip_ref.open(file_info) as src, open(extract_path, 'wb') as dst:
                            dst.write(src.read())
                else:
                    # Extract other files normally (like manifest.json)
                    zip_ref.extract(file_info, extension_dir)

        # For widget and extension type, also copy to frontend extensions directory
        if manifest.type in ['widget', 'extension']:
            frontend_extensions_dir = Path("frontend/src/extensions")
            frontend_extensions_dir.mkdir(exist_ok=True)

            # Copy the extension files to frontend
            frontend_extension_dir = frontend_extensions_dir / f"{manifest.name}_{manifest.version}"
            if frontend_extension_dir.exists():
                import shutil
                shutil.rmtree(frontend_extension_dir)

            # Only copy frontend files (not backend files)
            import shutil
            frontend_extension_dir.mkdir(exist_ok=True)

            # Copy manifest.json
            manifest_path = extension_dir / "manifest.json"
            if manifest_path.exists():
                shutil.copy2(manifest_path, frontend_extension_dir)

            # Copy frontend files from the ZIP directly to avoid issues
            with zipfile.ZipFile(temp_path, 'r') as zip_ref:
                for file_info in zip_ref.filelist:
                    if file_info.filename.startswith('frontend/'):
                        # Extract frontend files to the frontend extension directory (flatten structure)
                        relative_path = file_info.filename[len('frontend/'):]
                        if relative_path:  # Skip the directory itself
                            extract_path = frontend_extension_dir / relative_path
                            extract_path.parent.mkdir(parents=True, exist_ok=True)
                            with zip_ref.open(file_info) as src, open(extract_path, 'wb') as dst:
                                dst.write(src.read())

        # For extensions with backend entry, initialize the backend module
        if hasattr(manifest, 'backend_entry') and manifest.backend_entry:
            try:
                # Create sandbox environment based on permissions
                permissions = manifest.permissions or []
                sandbox_env = extension_sandbox.create_environment(
                    extension_id=f"{manifest.name}_{manifest.version}",
                    permissions=permissions
                )

                # Get database session for extension initialization
                db_session = next(get_db())
                from backend.main import app
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
                # Continue with installation even if backend initialization fails

        # Perform security analysis (skip if dummy)
        if hasattr(security_manager, 'validate_extension_package'):
            print(f"DEBUG: About to validate extension package at {extension_dir}")
            security_report = security_manager.validate_extension_package(extension_dir)
            print(f"DEBUG: Security report: {security_report}")

            # Check for critical security issues
            if security_report and 'critical' in security_report and security_report['critical']:
                # Quarantine the extension
                security_manager.quarantine_extension(extension_dir, f"Security violations: {security_report['critical']}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Extension contains security violations: {', '.join(security_report['critical'])}"
                )

            # Check permissions
            try:
                permission_issues = permission_manager.validate_manifest_permissions(manifest.dict())
                print(f"DEBUG: Permission issues: {permission_issues}, type: {type(permission_issues)}")
                if permission_issues and len(permission_issues) > 0:
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
            integrity_hash = security_manager.calculate_extension_hash(extension_dir)
            print(f"DEBUG: Integrity hash: {integrity_hash}")
        else:
            # Dummy security manager
            security_report = {}
            integrity_hash = "dummy_hash"

        # Register extension for monitoring
        performance_monitor.register_extension(f"{manifest.name}_{manifest.version}")

        # Register extension version
        version_manager.register_extension(f"{manifest.name}_{manifest.version}", manifest.version)

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
        db.add(extension)
        db.commit()
        db.refresh(extension)

        print(f"DEBUG: Returning extension schema: {extension.id}")
        return ExtensionSchema.from_orm(extension)

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

    if payload.is_enabled is not None:
        extension.is_enabled = payload.is_enabled
        extension.status = "active" if payload.is_enabled else "inactive"

        # Handle extension lifecycle
        extension_full_id = f"{extension.name}_{extension.version}"
        if payload.is_enabled:
            # Enable extension - initialize backend if present
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
            # Disable extension - cleanup backend
            extension_manager.cleanup_extension(extension_full_id)

    db.commit()
    db.refresh(extension)
    return ExtensionSchema.from_orm(extension)

@router.delete("/api/extensions/{extension_id}")
def delete_extension(
    extension_id: int,
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

    # Cleanup extension backend before deletion
    extension_full_id = f"{extension.name}_{extension.version}"
    extension_manager.cleanup_extension(extension_full_id)

    # Remove extension files from backend
    extension_path = Path(extension.file_path)
    if extension_path.exists():
        shutil.rmtree(extension_path)

    # Remove extension files from frontend if it's a widget or extension
    if extension.type in ['widget', 'extension']:
        frontend_extensions_dir = Path("frontend/src/extensions")
        frontend_extension_dir = frontend_extensions_dir / f"{extension.name}_{extension.version}"
        if frontend_extension_dir.exists():
            shutil.rmtree(frontend_extension_dir)

    # Remove from database
    db.delete(extension)
    db.commit()
    return {"message": "Extension deleted"}

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