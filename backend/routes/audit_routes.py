from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import desc, and_
from typing import List, Optional
from datetime import datetime, timedelta
from backend.db.audit_log import AuditLog, AuditLogSchema
from backend.db.user import User
from backend.services import audit_retention
from backend.utils.db_utils import get_db
from backend.utils.auth_dep import require_admin, require_user

router = APIRouter()


class AuditRetentionApplyRequest(BaseModel):
    retention_days: int
    confirmation: str = ""
    max_batch: int = 1000

    model_config = ConfigDict(extra="forbid")


@router.get("/audit-logs", response_model=List[AuditLogSchema])
def get_audit_logs(
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0)
):
    """Get audit logs with filtering options"""
    
    # Check if user is admin or getting their own logs
    current_user_id = claims.get("sub") or claims.get("user_id")
    current_user = db.query(User).filter(User.id == current_user_id).first()
    
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Build query
    query = db.query(AuditLog)
    
    # Non-admins can only see their own logs
    if current_user.role != "admin":
        query = query.filter(AuditLog.user_id == current_user_id)
    elif user_id:
        query = query.filter(AuditLog.user_id == user_id)
    
    # Apply filters
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if start_date:
        query = query.filter(AuditLog.timestamp >= start_date)
    if end_date:
        query = query.filter(AuditLog.timestamp <= end_date)
    
    # Order by timestamp descending and apply pagination
    logs = query.order_by(desc(AuditLog.timestamp)).offset(offset).limit(limit).all()
    
    return logs

@router.get("/audit-logs/stats")
def get_audit_stats(
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    days: int = Query(7, le=90)
):
    """Get audit log statistics"""
    
    current_user_id = claims.get("sub") or claims.get("user_id")
    current_user = db.query(User).filter(User.id == current_user_id).first()
    
    if not current_user or current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Get statistics
    query = db.query(AuditLog).filter(
        AuditLog.timestamp >= start_date,
        AuditLog.timestamp <= end_date
    )
    
    total_actions = query.count()
    
    # Count by action type
    action_counts = {}
    for action in ["CREATE", "UPDATE", "DELETE", "LOGIN", "LOGOUT"]:
        count = query.filter(AuditLog.action == action).count()
        action_counts[action.lower()] = count
    
    # Count by entity type
    from sqlalchemy import func
    entity_counts = dict(query.filter(AuditLog.entity_type.is_not(None)).with_entities(AuditLog.entity_type, func.count(AuditLog.id))
        .group_by(AuditLog.entity_type).order_by(AuditLog.entity_type).limit(128).all())
    
    # Most active users
    from sqlalchemy import func
    active_users = db.query(
        User.username,
        func.count(AuditLog.id).label("action_count")
    ).join(
        AuditLog, User.id == AuditLog.user_id
    ).filter(
        AuditLog.timestamp >= start_date,
        AuditLog.timestamp <= end_date
    ).group_by(User.username).order_by(
        desc("action_count")
    ).limit(5).all()
    
    return {
        "period_days": days,
        "total_actions": total_actions,
        "actions_by_type": action_counts,
        "actions_by_entity": entity_counts,
        "most_active_users": [
            {"username": user[0], "actions": user[1]} 
            for user in active_users
        ]
    }

@router.get("/audit-logs/entity/{entity_type}/{entity_id}")
def get_entity_history(
    entity_type: str,
    entity_id: int,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    limit: int = Query(50, le=200)
):
    """Get audit history for a specific entity"""
    
    logs = db.query(AuditLog).filter(
        AuditLog.entity_type == entity_type,
        AuditLog.entity_id == entity_id
    ).order_by(desc(AuditLog.timestamp)).limit(limit).all()
    
    return logs


@router.get("/audit-logs/retention-plan")
def get_audit_retention_plan(
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
    retention_days: int = Query(
        audit_retention.DEFAULT_RETENTION_DAYS,
        ge=audit_retention.MIN_RETENTION_DAYS,
        le=audit_retention.MAX_RETENTION_DAYS,
    ),
):
    """Admin-only dry run: what an age-based purge would remove, without doing it."""
    try:
        plan = audit_retention.plan_audit_retention(
            db,
            now=datetime.utcnow(),
            retention_days=retention_days,
        )
    except audit_retention.AuditRetentionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "retention_days": retention_days,
        "cutoff": plan.cutoff.isoformat() + "Z",
        "candidate_total": plan.candidate_total,
        "protected_evidential": plan.protected_evidential,
        "confirm_to_apply": "AUDIT RETENTION",
    }


@router.post("/audit-logs/retention")
def apply_audit_retention(
    payload: AuditRetentionApplyRequest,
    admin: User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    """Admin-only bounded purge of old, non-evidential audit records."""
    if payload.confirmation != "AUDIT RETENTION":
        raise HTTPException(status_code=409, detail="Confirmation does not match")
    try:
        deleted = audit_retention.apply_audit_retention(
            db,
            now=datetime.utcnow(),
            retention_days=payload.retention_days,
            max_batch=payload.max_batch,
        )
    except audit_retention.AuditRetentionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.add(
        AuditLog(
            user_id=admin.id,
            action="AUDIT_RETENTION_APPLIED",
            entity_type="audit_log",
            changes={
                "retention_days": payload.retention_days,
                "deleted": deleted,
            },
        )
    )
    db.commit()
    return {"deleted": deleted}
