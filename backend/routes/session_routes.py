from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session as DBSession
from typing import List, Optional
from datetime import datetime, timedelta
from backend.db.session import Session, SessionSchema, SessionCreateSchema
from backend.db.audit_log import AuditLog, AuditLogCreateSchema
from backend.db.user import User
from backend.utils.db_utils import get_db
from backend.utils.auth_dep import require_user
import user_agents
import hashlib

router = APIRouter()

def get_device_info(user_agent_string: str) -> dict:
    """Parse user agent string to get device information"""
    user_agent = user_agents.parse(user_agent_string)
    
    browser = user_agent.browser.family
    browser_version = user_agent.browser.version_string
    os = user_agent.os.family
    os_version = user_agent.os.version_string
    
    if user_agent.is_mobile:
        device = "Mobile"
    elif user_agent.is_tablet:
        device = "Tablet"
    else:
        device = "Desktop"
    
    device_name = f"{browser} on {os}"
    if os_version:
        device_name += f" {os_version}"
    
    return {
        "device_name": device_name,
        "device_type": device,
        "browser": browser,
        "os": os
    }

def create_audit_log(
    db: DBSession,
    user_id: int,
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    entity_name: Optional[str] = None,
    changes: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    session_id: Optional[int] = None
):
    """Helper function to create audit log entries"""
    audit_log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        changes=changes,
        ip_address=ip_address,
        user_agent=user_agent,
        session_id=session_id
    )
    db.add(audit_log)
    db.commit()

@router.get("/sessions/my", response_model=List[SessionSchema])
def get_my_sessions(
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db)
):
    """Get all sessions for the current user"""
    user_id = claims.get("sub") or claims.get("user_id")
    
    sessions = db.query(Session).filter(
        Session.user_id == user_id,
        Session.is_active == True
    ).order_by(Session.last_activity.desc()).all()
    
    # Mark current session
    current_token = request.headers.get("authorization", "").replace("Bearer ", "")
    for session in sessions:
        if session.token == current_token:
            session.is_current = True
    
    return sessions

@router.post("/sessions/logout-all")
def logout_all_sessions(
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    user_agent: Optional[str] = Header(None)
):
    """Logout from all sessions except current"""
    user_id = claims.get("sub") or claims.get("user_id")
    current_token = request.headers.get("authorization", "").replace("Bearer ", "")
    
    # Deactivate all sessions except current
    sessions = db.query(Session).filter(
        Session.user_id == user_id,
        Session.is_active == True,
        Session.token != current_token
    ).all()
    
    for session in sessions:
        session.is_active = False
    
    db.commit()
    
    # Create audit log
    create_audit_log(
        db=db,
        user_id=user_id,
        action="LOGOUT_ALL",
        entity_type="session",
        ip_address=request.client.host,
        user_agent=user_agent
    )
    
    return {"message": f"Logged out from {len(sessions)} other sessions"}

@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: int,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    user_agent: Optional[str] = Header(None)
):
    """Revoke a specific session"""
    user_id = claims.get("sub") or claims.get("user_id")
    
    session = db.query(Session).filter(
        Session.id == session_id,
        Session.user_id == user_id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session.is_active = False
    db.commit()
    
    # Create audit log
    create_audit_log(
        db=db,
        user_id=user_id,
        action="LOGOUT_SESSION",
        entity_type="session",
        entity_id=session_id,
        entity_name=session.device_name,
        ip_address=request.client.host,
        user_agent=user_agent
    )
    
    return {"message": "Session revoked successfully"}

@router.post("/sessions/track-activity")
def track_activity(
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    authorization: str = Header(None)
):
    """Update last activity time for current session"""
    if not authorization:
        return {"message": "No session to track"}
    
    token = authorization.replace("Bearer ", "")
    session = db.query(Session).filter(
        Session.token == token,
        Session.is_active == True
    ).first()
    
    if session:
        session.last_activity = datetime.utcnow()
        db.commit()
    
    return {"message": "Activity tracked"}