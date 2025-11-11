from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session as DBSession
from typing import List, Optional
from datetime import datetime
from backend.db.role import Group, GroupSchema, GroupCreateSchema, GroupUpdateSchema
from backend.db.user import User
from backend.db.audit_log import AuditLog
from backend.db.association_tables import user_groups
from backend.utils.db_utils import get_db
from backend.utils.auth_dep import require_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/groups", response_model=List[GroupSchema])
def get_groups(
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    user_agent: Optional[str] = Header(None)
):
    """Get all groups (admin only)"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    groups = db.query(Group).all()
    
    # Create audit log
    audit_log = AuditLog(
        user_id=user_id,
        action="VIEW_GROUPS",
        entity_type="group",
        entity_id=0,
        entity_name="all",
        changes={"count": len(groups)},
        ip_address=request.client.host if request.client else None,
        user_agent=user_agent
    )
    db.add(audit_log)
    db.commit()
    
    return groups

@router.get("/groups/{group_id}", response_model=GroupSchema)
def get_group(
    group_id: int,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    user_agent: Optional[str] = Header(None)
):
    """Get a specific group by ID (admin only)"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    return group

@router.post("/groups", response_model=GroupSchema)
def create_group(
    group_data: GroupCreateSchema,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    user_agent: Optional[str] = Header(None)
):
    """Create a new group (admin only)"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Check if group name already exists
    existing_group = db.query(Group).filter(Group.name == group_data.name).first()
    if existing_group:
        raise HTTPException(status_code=400, detail="Group name already exists")
    
    group = Group(
        name=group_data.name,
        description=group_data.description
    )
    
    db.add(group)
    db.commit()
    db.refresh(group)
    
    # Create audit log
    audit_log = AuditLog(
        user_id=user_id,
        action="CREATE_GROUP",
        entity_type="group",
        entity_id=group.id,
        entity_name=group.name,
        changes=group_data.model_dump(),
        ip_address=request.client.host if request.client else None,
        user_agent=user_agent
    )
    db.add(audit_log)
    db.commit()
    
    logger.info(f"Group created successfully: {group.id}")
    
    return group

@router.put("/groups/{group_id}", response_model=GroupSchema)
def update_group(
    group_id: int,
    group_data: GroupUpdateSchema,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    user_agent: Optional[str] = Header(None)
):
    """Update a group (admin only)"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Check if name already exists (if name is being changed)
    if group_data.name and group_data.name != group.name:
        existing_group = db.query(Group).filter(Group.name == group_data.name).first()
        if existing_group:
            raise HTTPException(status_code=400, detail="Group name already exists")
    
    # Update fields
    if group_data.name:
        group.name = group_data.name
    if group_data.description is not None:
        group.description = group_data.description
    
    group.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(group)
    
    # Create audit log
    audit_log = AuditLog(
        user_id=user_id,
        action="UPDATE_GROUP",
        entity_type="group",
        entity_id=group.id,
        entity_name=group.name,
        changes=group_data.model_dump(exclude_unset=True),
        ip_address=request.client.host if request.client else None,
        user_agent=user_agent
    )
    db.add(audit_log)
    db.commit()
    
    logger.info(f"Group updated successfully: {group.id}")
    
    return group

@router.delete("/groups/{group_id}")
def delete_group(
    group_id: int,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    user_agent: Optional[str] = Header(None)
):
    """Delete a group (admin only)"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    group_name = group.name
    
    # Check if group has any users
    from sqlalchemy import select
    from backend.db.association_tables import user_groups
    stmt = select(user_groups).where(user_groups.c.group_id == group_id)
    result = db.execute(stmt).fetchall()
    if len(result) > 0:
        raise HTTPException(status_code=400, detail="Cannot delete group that has members")
    
    # Create audit log before deletion
    audit_log = AuditLog(
        user_id=user_id,
        action="DELETE_GROUP",
        entity_type="group",
        entity_id=group.id,
        entity_name=group_name,
        changes={"deleted": True},
        ip_address=request.client.host if request.client else None,
        user_agent=user_agent
    )
    db.add(audit_log)
    
    # Delete group
    db.delete(group)
    db.commit()
    
    logger.info(f"Group deleted successfully: {group_id}")
    
    return {"message": "Group deleted successfully"}

@router.post("/groups/{group_id}/add/{user_id}")
def add_user_to_group(
    group_id: int,
    user_id: int,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    user_agent: Optional[str] = Header(None)
):
    """Add a user to a group (admin only)"""
    
    admin_id = claims.get("sub") or claims.get("user_id")
    admin_user = db.query(User).filter(User.id == admin_id).first()
    
    if not admin_user or admin_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if user is already in this group
    from sqlalchemy import select
    stmt = select(user_groups).where(
        user_groups.c.user_id == user_id,
        user_groups.c.group_id == group_id
    )
    result = db.execute(stmt).fetchall()
    if len(result) > 0:
        raise HTTPException(status_code=400, detail="User is already in this group")
    
    # Add user to group
    from sqlalchemy import insert
    db.execute(insert(user_groups).values(user_id=user_id, group_id=group_id))
    
    # Create audit log
    audit_log = AuditLog(
        user_id=admin_id,
        action="ADD_TO_GROUP",
        entity_type="group",
        entity_id=group.id,
        entity_name=group.name,
        changes={
            "user_id": user_id,
            "username": user.username,
            "group_id": group_id,
            "group_name": group.name
        },
        ip_address=request.client.host if request.client else None,
        user_agent=user_agent
    )
    db.add(audit_log)
    db.commit()
    
    logger.info(f"User {user_id} added to group {group_id}")
    
    return {"message": "User added to group successfully"}

@router.delete("/groups/{group_id}/remove/{user_id}")
def remove_user_from_group(
    group_id: int,
    user_id: int,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    user_agent: Optional[str] = Header(None)
):
    """Remove a user from a group (admin only)"""
    
    admin_id = claims.get("sub") or claims.get("user_id")
    admin_user = db.query(User).filter(User.id == admin_id).first()
    
    if not admin_user or admin_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if user is in this group
    from sqlalchemy import select
    from backend.db.association_tables import user_groups
    stmt = select(user_groups).where(
        user_groups.c.user_id == user_id,
        user_groups.c.group_id == group_id
    )
    result = db.execute(stmt).fetchall()
    if len(result) == 0:
        raise HTTPException(status_code=400, detail="User is not in this group")
    
    # Remove user from group
    from sqlalchemy import delete
    db.execute(delete(user_groups).where(
        user_groups.c.user_id == user_id,
        user_groups.c.group_id == group_id
    ))
    
    # Create audit log
    audit_log = AuditLog(
        user_id=admin_id,
        action="REMOVE_FROM_GROUP",
        entity_type="group",
        entity_id=group.id,
        entity_name=group.name,
        changes={
            "user_id": user_id,
            "username": user.username,
            "group_id": group_id,
            "group_name": group.name
        },
        ip_address=request.client.host if request.client else None,
        user_agent=user_agent
    )
    db.add(audit_log)
    db.commit()
    
    logger.info(f"User {user_id} removed from group {group_id}")
    
    return {"message": "User removed from group successfully"}

@router.get("/groups/{group_id}/users")
def get_group_users(
    group_id: int,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db)
):
    """Get all users in a specific group (admin only)"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Get all users in this group using simple raw SQL approach
    from sqlalchemy import text
    
    # Use raw SQL to avoid relationship issues
    query = text("""
        SELECT u.id, u.username, u.email, u.role, u.created_at
        FROM users u
        JOIN user_groups ug ON u.id = ug.user_id
        WHERE ug.group_id = :group_id
    """)
    
    result = db.execute(query, {"group_id": group_id}).fetchall()
    
    users_list = []
    for row in result:
        users_list.append({
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "role": row[3],
            "created_at": row[4]
        })
    
    return users_list

@router.get("/groups/{group_id}/count")
def get_group_user_count(
    group_id: int,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db)
):
    """Get user count for a specific group (admin only)"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    # Get count of users in this group using raw SQL
    from sqlalchemy import text
    
    query = text("SELECT COUNT(*) FROM user_groups WHERE group_id = :group_id")
    count = db.execute(query, {"group_id": group_id}).scalar()
    
    return {"group_id": group_id, "user_count": count}

@router.get("/users/{user_id}/groups")
def get_user_groups(
    user_id: int,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db)
):
    """Get all groups for a specific user (admin only)"""
    
    admin_id = claims.get("sub") or claims.get("user_id")
    admin_user = db.query(User).filter(User.id == admin_id).first()
    
    if not admin_user or admin_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get all groups for this user
    groups = user.groups.all()
    
    result = []
    for group in groups:
        result.append({
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "created_at": group.created_at,
            "updated_at": group.updated_at
        })
    
    return result