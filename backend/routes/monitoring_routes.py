"""
Extension Performance Monitoring API Routes
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import time

from backend.database import get_db
from backend.utils.auth_dep import require_user
from backend.utils.extension_monitoring import performance_monitor, health_checker

router = APIRouter()

@router.get("/api/extensions/monitoring/metrics/{extension_id}")
async def get_extension_metrics(
    extension_id: str,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Get current performance metrics for an extension"""
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    metrics = performance_monitor.get_metrics(extension_id)
    if not metrics:
        raise HTTPException(status_code=404, detail="Extension metrics not found")

    return {
        "extension_id": extension_id,
        "metrics": {
            "cpu_usage": metrics.cpu_usage,
            "memory_usage": metrics.memory_usage,
            "response_time": metrics.response_time,
            "request_count": metrics.request_count,
            "error_count": metrics.error_count,
            "uptime": metrics.uptime,
            "database_queries": metrics.database_queries,
            "database_query_time": metrics.database_query_time,
            "last_activity": metrics.last_activity.isoformat() if metrics.last_activity else None
        }
    }

@router.get("/api/extensions/monitoring/stats/{extension_id}")
async def get_extension_stats(
    extension_id: str,
    hours: int = Query(24, le=168),
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Get statistical data for an extension"""
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    stats = performance_monitor.get_stats(extension_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Extension stats not found")

    # Filter stats by time range
    from datetime import datetime, timedelta
    cutoff_time = datetime.utcnow() - timedelta(hours=hours)

    filtered_hourly = [
        stat for stat in stats.hourly_stats
        if stat['timestamp'] > cutoff_time
    ]

    return {
        "extension_id": extension_id,
        "time_range_hours": hours,
        "hourly_stats": filtered_hourly,
        "alerts_count": len(stats.alerts_triggered)
    }

@router.get("/api/extensions/monitoring/alerts/{extension_id}")
async def get_extension_alerts(
    extension_id: str,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Get alerts for an extension"""
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    alerts = performance_monitor.get_alerts(extension_id, limit)
    return {
        "extension_id": extension_id,
        "alerts": alerts,
        "count": len(alerts)
    }

@router.get("/api/extensions/monitoring/health/{extension_id}")
async def get_extension_health(
    extension_id: str,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Get health status for an extension"""
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    health_status = health_checker.get_health_status(extension_id)
    if not health_status:
        return {
            "extension_id": extension_id,
            "status": "unknown",
            "message": "No health check registered for this extension"
        }

    return {
        "extension_id": extension_id,
        "health_status": health_status
    }

@router.get("/api/extensions/monitoring/overview")
async def get_monitoring_overview(
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Get monitoring overview for all extensions"""
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    all_metrics = performance_monitor.get_all_metrics()

    overview = []
    for extension_id, metrics in all_metrics.items():
        alerts = performance_monitor.get_alerts(extension_id, limit=10)
        recent_alerts = len([a for a in alerts if time.time() - time.mktime(a['timestamp'].timetuple()) < 3600])  # Last hour

        overview.append({
            "extension_id": extension_id,
            "cpu_usage": metrics.cpu_usage,
            "memory_usage": metrics.memory_usage,
            "request_count": metrics.request_count,
            "error_count": metrics.error_count,
            "uptime": metrics.uptime,
            "recent_alerts": recent_alerts,
            "last_activity": metrics.last_activity.isoformat() if metrics.last_activity else None
        })

    return {
        "extensions": overview,
        "total_extensions": len(overview),
        "timestamp": time.time()
    }

@router.post("/api/extensions/monitoring/health-check/{extension_id}")
async def register_health_check(
    extension_id: str,
    check_config: dict,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Register a health check for an extension (admin only)"""
    user_role = claims.get("role", "user")
    if user_role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    # This would typically be called by extensions themselves
    # For now, it's an admin endpoint for manual registration
    def dummy_health_check(ext_id):
        metrics = performance_monitor.get_metrics(ext_id)
        return metrics and metrics.request_count >= 0  # Basic liveness check

    interval = check_config.get('interval', 300)
    health_checker.register_health_check(extension_id, dummy_health_check, interval)

    return {
        "message": f"Health check registered for {extension_id}",
        "interval": interval
    }

@router.patch("/api/extensions/monitoring/thresholds")
async def update_alert_thresholds(
    thresholds: dict,
    db: Session = Depends(get_db),
    claims: dict = Depends(require_user)
):
    """Update alert thresholds (admin only)"""
    user_role = claims.get("role", "user")
    if user_role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    updated = []
    for metric, threshold in thresholds.items():
        if hasattr(performance_monitor, 'set_alert_threshold'):
            performance_monitor.set_alert_threshold(metric, threshold)
            updated.append(metric)

    return {
        "message": f"Updated thresholds for: {', '.join(updated)}",
        "updated_metrics": updated
    }