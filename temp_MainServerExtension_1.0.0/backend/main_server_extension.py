"""
Main Server Extension - Backend Implementation
Manages and distributes updates to Raspberry Pi devices
"""

from fastapi import APIRouter, Depends, HTTPException
from backend.utils.auth_dep import require_user
from backend.utils.extension_manager import extension_manager
from backend.utils.extension_updates import update_manager
from backend.db.extension import Extension
from sqlalchemy.orm import Session
from backend.database import get_db
from typing import List, Dict, Any
import json
import os
from pathlib import Path

def initialize_extension(context):
    """Initialize the Main Server Extension"""
    router = APIRouter(prefix="/api/main-server")
    
    @router.get("/health")
    def health():
        return {"ok": True, "message": "Main Server Extension is running"}
    
    @router.get("/updates")
    def get_available_updates(claims: dict = Depends(require_user)):
        """Get available updates for all devices"""
        user_id = claims.get("sub") or claims.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        user_id = int(user_id)
        
        # Get database session
        db = next(get_db())
        
        try:
            # Check for available updates
            updates = update_manager.check_for_updates(user_id, db)
            return {"updates": updates}
        finally:
            db.close()
    
    @router.post("/schedule-update")
    def schedule_update(
        extension_id: int,
        new_version: str,
        claims: dict = Depends(require_user)
    ):
        """Schedule an update for a specific extension"""
        user_id = claims.get("sub") or claims.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        user_id = int(user_id)
        
        # Schedule the update
        result = update_manager.schedule_update(extension_id, new_version, user_id)
        return result
    
    @router.get("/update-status/{extension_id}")
    def get_update_status(extension_id: str):
        """Get the status of an ongoing update"""
        status = update_manager.get_update_status(extension_id)
        if status:
            return status
        else:
            return {"status": "not_updating", "extension_id": extension_id}
    
    @router.get("/devices")
    def get_connected_devices(claims: dict = Depends(require_user)):
        """Get list of connected Raspberry Pi devices"""
        user_id = claims.get("sub") or claims.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        user_id = int(user_id)
        
        # In a real implementation, this would query a device registry
        # For now, return a mock list
        devices = [
            {"id": "raspi-001", "name": "Living Room Display", "ip": "192.168.1.100", "status": "online"},
            {"id": "raspi-002", "name": "Kitchen Display", "ip": "192.168.1.101", "status": "online"},
            {"id": "raspi-003", "name": "Bedroom Display", "ip": "192.168.1.102", "status": "offline"}
        ]
        
        return {"devices": devices}
    
    @router.post("/deploy-update")
    async def deploy_update_to_device(
        device_id: str,
        extension_id: int,
        version: str,
        claims: dict = Depends(require_user)
    ):
        """Deploy an update to a specific device"""
        user_id = claims.get("sub") or claims.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        user_id = int(user_id)
        
        # Use the update manager to deploy the update
        result = await update_manager.deploy_update_to_device(device_id, extension_id, version)
        
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        
        return result
    
    @router.get("/settings")
    def get_update_settings(claims: dict = Depends(require_user)):
        """Get update settings for the main server"""
        user_id = claims.get("sub") or claims.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        user_id = int(user_id)
        
        # Return default settings
        settings = {
            "auto_update": False,
            "update_interval": "daily",
            "notify_devices": True,
            "backup_before_update": True
        }
        
        return {"settings": settings}
    
    @router.post("/settings")
    def update_settings(
        settings: Dict[str, Any],
        claims: dict = Depends(require_user)
    ):
        """Update settings for the main server"""
        user_id = claims.get("sub") or claims.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        user_id = int(user_id)
        
        # In a real implementation, this would save settings to the database
        # For now, just return the updated settings
        return {
            "message": "Settings updated successfully",
            "settings": settings
        }
    
    context.register_router(router)
    return {"routes_registered": 7, "status": "initialized"}

def cleanup_extension(context):
    """Cleanup when extension is disabled"""
    return {"status": "cleaned_up"}