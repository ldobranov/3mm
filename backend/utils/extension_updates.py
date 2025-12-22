"""
Extension Update Management System
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import zipfile
import tempfile
import shutil
import json

from backend.database import get_db
from backend.db.extension import Extension
from backend.utils.extension_dependencies import version_manager
from backend.utils.extension_manager import extension_manager

class ExtensionUpdateManager:
    """Manages extension updates and migrations"""

    def __init__(self):
        self.update_queue: asyncio.Queue = asyncio.Queue()
        self.updating: Dict[str, bool] = {}

    async def start_update_worker(self):
        """Start the background update worker"""
        asyncio.create_task(self._process_updates())

    async def _process_updates(self):
        """Process extension updates from the queue"""
        while True:
            try:
                update_request = await self.update_queue.get()
                await self._perform_update(update_request)
                self.update_queue.task_done()
            except Exception as e:
                print(f"Error processing update: {e}")

    async def _perform_update(self, update_request: Dict[str, Any]):
        """Perform an extension update"""
        extension_id = update_request["extension_id"]
        new_version = update_request["new_version"]
        user_id = update_request["user_id"]

        if extension_id in self.updating:
            return  # Already updating

        self.updating[extension_id] = True

        try:
            # Get extension from database
            db = next(get_db())
            extension = db.query(Extension).filter(
                Extension.id == extension_id,
                Extension.user_id == user_id
            ).first()

            if not extension:
                print(f"Extension {extension_id} not found for update")
                return

            # Check if update is compatible
            if not version_manager.is_compatible_update(extension.version, new_version):
                print(f"Update from {extension.version} to {new_version} may not be compatible")
                # Still proceed but log warning

            # Download new version (would integrate with marketplace)
            new_package_path = await self._download_extension_package(extension.name, new_version)

            if not new_package_path:
                print(f"Failed to download update for {extension.name}")
                return

            # Backup current extension
            backup_path = await self._create_backup(extension)

            try:
                # Disable current extension
                extension_manager.cleanup_extension(f"{extension.name}_{extension.version}")

                # Extract new version
                new_extension_dir = Path(extension.file_path).parent / f"{extension.name}_{new_version}"
                new_extension_dir.mkdir(parents=True, exist_ok=True)

                with zipfile.ZipFile(new_package_path, 'r') as zip_ref:
                    zip_ref.extractall(new_extension_dir)

                # Update database record
                old_file_path = extension.file_path
                extension.version = new_version
                extension.file_path = str(new_extension_dir)
                extension.updated_at = datetime.utcnow()

                # Run migration if needed
                await self._run_migration(extension, new_extension_dir, db)

                # Enable new version
                success = extension_manager.initialize_extension(
                    extension_id=f"{extension.name}_{new_version}",
                    extension_path=new_extension_dir,
                    app=None,  # Would need to pass app instance
                    db=db
                )

                if success:
                    # Clean up old version
                    old_path = Path(old_file_path)
                    if old_path.exists():
                        shutil.rmtree(old_path)

                    # Clean up backup after successful update
                    if backup_path and backup_path.exists():
                        shutil.rmtree(backup_path)

                    db.commit()
                    print(f"Successfully updated {extension.name} to {new_version}")
                else:
                    # Rollback on failure
                    await self._rollback_update(extension, backup_path, db)
                    print(f"Failed to initialize updated {extension.name}")

            except Exception as e:
                # Rollback on error
                await self._rollback_update(extension, backup_path, db)
                print(f"Error during update of {extension.name}: {e}")

        finally:
            if extension_id in self.updating:
                del self.updating[extension_id]

    async def _download_extension_package(self, extension_name: str, version: str) -> Optional[Path]:
        """Download extension package from marketplace"""
        # This would integrate with the marketplace API
        # For now, return None (would need actual implementation)
        return None

    async def _package_update_for_device(self, extension_id: int, version: str, device_id: str) -> Optional[Path]:
        """Package an update for a specific device"""
        try:
            # Get extension from database
            db = next(get_db())
            extension = db.query(Extension).filter(Extension.id == extension_id).first()
            
            if not extension:
                return None
            
            # Create a temporary directory for the package
            temp_dir = Path(f"/tmp/update_{device_id}_{extension.name}_{version}")
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy extension files to temp directory
            extension_path = Path(extension.file_path)
            if extension_path.exists():
                # Copy the entire extension directory
                import shutil
                shutil.copytree(extension_path, temp_dir / f"{extension.name}_{version}")
                
                # Create a manifest for the device
                device_manifest = {
                    "device_id": device_id,
                    "extension_id": extension_id,
                    "extension_name": extension.name,
                    "version": version,
                    "timestamp": datetime.utcnow().isoformat(),
                    "instructions": "Extract to extensions directory and restart service"
                }
                
                with open(temp_dir / "device_update.json", "w") as f:
                    json.dump(device_manifest, f, indent=2)
                
                # Create a zip file
                zip_path = Path(f"/tmp/{device_id}_update_{extension.name}_{version}.zip")
                with zipfile.ZipFile(zip_path, 'w') as zipf:
                    for file in temp_dir.rglob('*'):
                        if file.is_file():
                            zipf.write(file, file.relative_to(temp_dir))
                
                # Clean up temp directory
                shutil.rmtree(temp_dir)
                
                return zip_path
            
        except Exception as e:
            print(f"Error packaging update for device {device_id}: {e}")
            return None
        
        return None

    async def _create_backup(self, extension: Extension) -> Optional[Path]:
        """Create a backup of the current extension"""
        try:
            extension_path = Path(extension.file_path)
            if extension_path.exists():
                backup_path = extension_path.parent / f"{extension.name}_{extension.version}_backup"
                shutil.copytree(extension_path, backup_path)
                return backup_path
        except Exception as e:
            print(f"Failed to create backup for {extension.name}: {e}")
        return None

    async def _rollback_update(self, extension: Extension, backup_path: Optional[Path], db):
        """Rollback a failed update"""
        try:
            if backup_path and backup_path.exists():
                # Restore from backup
                extension_path = Path(extension.file_path)
                if extension_path.exists():
                    shutil.rmtree(extension_path)
                shutil.move(str(backup_path), extension.file_path)

                # Re-enable old version
                extension_manager.initialize_extension(
                    extension_id=f"{extension.name}_{extension.version}",
                    extension_path=Path(extension.file_path),
                    app=None,
                    db=db
                )

                print(f"Rolled back update for {extension.name}")
        except Exception as e:
            print(f"Failed to rollback update for {extension.name}: {e}")

    async def _run_migration(self, extension: Extension, new_path: Path, db):
        """Run migration scripts for extension update"""
        try:
            # Look for migration scripts in extension
            migration_dir = new_path / "migrations"
            if migration_dir.exists():
                # Run migration scripts (would need proper migration framework)
                print(f"Running migrations for {extension.name}")
                # Implementation would depend on migration framework used
        except Exception as e:
            print(f"Migration failed for {extension.name}: {e}")
            raise

    async def schedule_update(self, extension_id: int, new_version: str, user_id: int):
        """Schedule an extension update"""
        update_request = {
            "extension_id": extension_id,
            "new_version": new_version,
            "user_id": user_id,
            "scheduled_at": datetime.utcnow()
        }
        
        await self.update_queue.put(update_request)
        return {"message": "Update scheduled", "extension_id": extension_id}

    async def deploy_update_to_device(self, device_id: str, extension_id: int, version: str):
        """Deploy an update to a specific device"""
        try:
            # Package the update for the device
            update_package = await self._package_update_for_device(extension_id, version, device_id)
            
            if not update_package:
                return {"status": "error", "message": "Failed to package update"}
            
            # In a real implementation, this would:
            # 1. Transfer the package to the device via SSH/SCP
            # 2. Trigger the update process on the device
            # 3. Monitor the update status
            
            # For now, return a mock response
            return {
                "status": "queued",
                "message": f"Update deployment queued for device {device_id}",
                "device_id": device_id,
                "extension_id": extension_id,
                "version": version,
                "package_path": str(update_package)
            }
            
        except Exception as e:
            print(f"Error deploying update to device {device_id}: {e}")
            return {"status": "error", "message": str(e)}

    def get_update_status(self, extension_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of an ongoing update"""
        if extension_id in self.updating:
            return {"status": "updating", "extension_id": extension_id}
        return None

    async def check_for_updates(self, user_id: int, db) -> List[Dict[str, Any]]:
        """Check for available updates for user's extensions"""
        extensions = db.query(Extension).filter(Extension.user_id == user_id).all()
        updates_available = []

        for ext in extensions:
            # Check marketplace for updates (would integrate with marketplace API)
            latest_version = version_manager.check_for_updates(
                f"{ext.name}_{ext.version}",
                ext.version
            )

            if latest_version and latest_version != ext.version:
                updates_available.append({
                    "extension_id": ext.id,
                    "name": ext.name,
                    "current_version": ext.version,
                    "available_version": latest_version,
                    "is_compatible": version_manager.is_compatible_update(ext.version, latest_version)
                })

        return updates_available

class ExtensionMigrationManager:
    """Manages database migrations for extensions"""

    def __init__(self):
        self.migrations: Dict[str, List[Dict[str, Any]]] = {}

    def register_migration(self, extension_id: str, from_version: str, to_version: str,
                          migration_func: callable, description: str = ""):
        """Register a migration function"""
        if extension_id not in self.migrations:
            self.migrations[extension_id] = []

        self.migrations[extension_id].append({
            "from_version": from_version,
            "to_version": to_version,
            "function": migration_func,
            "description": description
        })

    async def run_migrations(self, extension_id: str, from_version: str, to_version: str, context: Any):
        """Run applicable migrations for an extension update"""
        if extension_id not in self.migrations:
            return

        applicable_migrations = [
            m for m in self.migrations[extension_id]
            if m["from_version"] == from_version and m["to_version"] == to_version
        ]

        for migration in applicable_migrations:
            try:
                print(f"Running migration: {migration['description']}")
                await migration["function"](context)
            except Exception as e:
                print(f"Migration failed: {e}")
                raise

# Global instances
update_manager = ExtensionUpdateManager()
migration_manager = ExtensionMigrationManager()

# Helper functions
async def schedule_extension_update(extension_id: int, new_version: str, user_id: int):
    """Helper function to schedule an extension update"""
    return await update_manager.schedule_update(extension_id, new_version, user_id)

def get_update_status(extension_id: str):
    """Helper function to get update status"""
    return update_manager.get_update_status(extension_id)