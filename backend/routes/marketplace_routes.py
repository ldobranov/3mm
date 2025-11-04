"""
Extension Marketplace API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import requests
from datetime import datetime

from backend.database import get_db
from backend.utils.auth_dep import require_user
from backend.utils.extension_dependencies import extension_repository
from backend.utils.extension_updates import update_manager
from backend.db.extension import Extension

router = APIRouter()

MARKETPLACE_URL = "https://extensions.megamonitor.dev/api"

@router.get("/api/marketplace/search")
async def search_marketplace(
    query: str = Query(..., min_length=1),
    category: Optional[str] = None,
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Search for extensions in the marketplace"""
    try:
        # This would make a real API call to the marketplace
        # For now, return mock data
        mock_results = [
            {
                "id": "system-monitor",
                "name": "System Monitor",
                "version": "1.0.0",
                "description": "Real-time system monitoring widget",
                "author": "Mega Monitor Team",
                "category": "monitoring",
                "downloads": 1250,
                "rating": 4.5,
                "tags": ["system", "monitoring", "metrics"],
                "updated_at": "2024-01-15T00:00:00Z"
            },
            {
                "id": "weather-widget",
                "name": "Weather Widget",
                "version": "2.1.0",
                "description": "Weather forecasts and current conditions",
                "author": "Weather Corp",
                "category": "information",
                "downloads": 3200,
                "rating": 4.2,
                "tags": ["weather", "forecast", "api"],
                "updated_at": "2024-01-10T00:00:00Z"
            }
        ]

        # Filter by query
        results = [
            ext for ext in mock_results
            if query.lower() in ext["name"].lower() or
               query.lower() in ext["description"].lower() or
               any(query.lower() in tag for tag in ext.get("tags", []))
        ]

        # Filter by category
        if category:
            results = [ext for ext in results if ext.get("category") == category]

        return {
            "query": query,
            "category": category,
            "total": len(results),
            "results": results[:limit]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Marketplace search failed: {str(e)}")

@router.get("/api/marketplace/extension/{extension_id}")
async def get_marketplace_extension(
    extension_id: str,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Get detailed information about a marketplace extension"""
    try:
        # Mock data - would be real API call
        mock_extensions = {
            "system-monitor": {
                "id": "system-monitor",
                "name": "System Monitor",
                "version": "1.0.0",
                "description": "Real-time system monitoring widget with CPU, memory, disk, and network metrics",
                "author": "Mega Monitor Team",
                "author_email": "team@megamonitor.dev",
                "homepage": "https://megamonitor.dev/extensions/system-monitor",
                "repository": "https://github.com/megamonitor/system-monitor",
                "license": "MIT",
                "category": "monitoring",
                "tags": ["system", "monitoring", "metrics", "dashboard"],
                "downloads": 1250,
                "rating": 4.5,
                "reviews_count": 23,
                "screenshots": [
                    "https://example.com/screenshot1.png",
                    "https://example.com/screenshot2.png"
                ],
                "changelog": "Initial release with basic system monitoring features",
                "dependencies": {
                    "psutil": ">=5.9.0"
                },
                "permissions": ["system_read"],
                "config_schema": {
                    "type": "object",
                    "properties": {
                        "refreshInterval": {
                            "type": "number",
                            "title": "Refresh Interval",
                            "default": 30
                        }
                    }
                },
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-15T00:00:00Z",
                "file_size": 245760
            }
        }

        if extension_id not in mock_extensions:
            raise HTTPException(status_code=404, detail="Extension not found in marketplace")

        return mock_extensions[extension_id]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get extension info: {str(e)}")

@router.post("/api/marketplace/install/{extension_id}")
async def install_from_marketplace(
    extension_id: str,
    version: Optional[str] = None,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Install an extension from the marketplace"""
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)

    try:
        # Check if extension is already installed
        existing = db.query(Extension).filter(
            Extension.user_id == user_id,
            Extension.name == extension_id
        ).first()

        if existing:
            raise HTTPException(status_code=400, detail="Extension already installed")

        # Download extension from marketplace
        extension_data = await get_marketplace_extension(extension_id, db, claims)
        version_to_install = version or extension_data["version"]

        # This would download the actual ZIP file
        # For now, we'll simulate by creating a reference
        print(f"Installing {extension_id} version {version_to_install} for user {user_id}")

        # The actual installation would go through the existing upload endpoint
        # Here we would download the ZIP and then call the upload endpoint

        return {
            "message": f"Extension {extension_id} installation initiated",
            "extension_id": extension_id,
            "version": version_to_install
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Installation failed: {str(e)}")

@router.get("/api/marketplace/categories")
async def get_marketplace_categories(
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Get available extension categories"""
    return {
        "categories": [
            {"id": "monitoring", "name": "Monitoring", "description": "System and service monitoring"},
            {"id": "information", "name": "Information", "description": "Data display and information widgets"},
            {"id": "productivity", "name": "Productivity", "description": "Task management and productivity tools"},
            {"id": "communication", "name": "Communication", "description": "Messaging and collaboration"},
            {"id": "utilities", "name": "Utilities", "description": "Helper tools and utilities"},
            {"id": "themes", "name": "Themes", "description": "Visual themes and styling"}
        ]
    }

@router.get("/api/marketplace/popular")
async def get_popular_extensions(
    limit: int = Query(10, le=50),
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Get popular extensions from the marketplace"""
    try:
        # Mock popular extensions
        popular = [
            {
                "id": "system-monitor",
                "name": "System Monitor",
                "downloads": 1250,
                "rating": 4.5
            },
            {
                "id": "weather-widget",
                "name": "Weather Widget",
                "downloads": 3200,
                "rating": 4.2
            },
            {
                "id": "rss-reader",
                "name": "RSS Reader",
                "downloads": 890,
                "rating": 4.1
            }
        ]

        return {
            "popular": popular[:limit]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get popular extensions: {str(e)}")

@router.get("/api/marketplace/updates")
async def check_extension_updates(
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Check for available updates for installed extensions"""
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)

    try:
        # Get user's installed extensions
        extensions = db.query(Extension).filter(Extension.user_id == user_id).all()

        updates_available = []
        for ext in extensions:
            # Check marketplace for updates
            try:
                marketplace_info = await get_marketplace_extension(ext.name, db, claims)
                if marketplace_info["version"] != ext.version:
                    updates_available.append({
                        "extension_id": ext.id,
                        "name": ext.name,
                        "current_version": ext.version,
                        "available_version": marketplace_info["version"],
                        "changelog": marketplace_info.get("changelog", "")
                    })
            except:
                # Extension not found in marketplace or other error
                continue

        return {
            "updates_available": updates_available,
            "count": len(updates_available)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check updates: {str(e)}")

@router.post("/api/marketplace/update/{extension_id}")
async def update_extension_from_marketplace(
    extension_id: int,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Update an extension from the marketplace"""
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)

    try:
        # Get extension info
        extension = db.query(Extension).filter(
            Extension.id == extension_id,
            Extension.user_id == user_id
        ).first()

        if not extension:
            raise HTTPException(status_code=404, detail="Extension not found")

        # Get latest version from marketplace
        marketplace_info = await get_marketplace_extension(extension.name, db, claims)

        if marketplace_info["version"] == extension.version:
            return {"message": "Extension is already up to date"}

        # Schedule update using the update manager
        result = await update_manager.schedule_update(
            extension_id=extension_id,
            new_version=marketplace_info["version"],
            user_id=user_id
        )

        return {
            "message": f"Extension {extension.name} update scheduled",
            "from_version": extension.version,
            "to_version": marketplace_info["version"],
            "update_id": result.get("extension_id")
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update scheduling failed: {str(e)}")

@router.get("/api/marketplace/updates/status/{extension_id}")
async def get_update_status(
    extension_id: str,
    claims: dict = Depends(require_user)
):
    """Get the status of an extension update"""
    status = update_manager.get_update_status(extension_id)
    if status:
        return status
    else:
        return {"status": "no_update", "extension_id": extension_id}