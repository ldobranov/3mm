from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session as DBSession
from typing import List, Optional
from datetime import datetime
from backend.db.role import Role, RoleSchema, RoleCreateSchema, RoleUpdateSchema
from backend.db.user import User
from backend.db.audit_log import AuditLog
from backend.db.association_tables import user_roles
from backend.utils.db_utils import get_db
from backend.utils.auth_dep import require_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/roles", response_model=List[RoleSchema])
def get_roles(
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    user_agent: Optional[str] = Header(None)
):
    """Get all roles (admin only)"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    roles = db.query(Role).all()
    
    # Create audit log
    audit_log = AuditLog(
        user_id=user_id,
        action="VIEW_ROLES",
        entity_type="role",
        entity_id=0,
        entity_name="all",
        changes={"count": len(roles)},
        ip_address=request.client.host if request.client else None,
        user_agent=user_agent
    )
    db.add(audit_log)
    db.commit()
    
    return roles

@router.get("/roles/{role_id}", response_model=RoleSchema)
def get_role(
    role_id: int,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    user_agent: Optional[str] = Header(None)
):
    """Get a specific role by ID (admin only)"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    return role

@router.post("/roles", response_model=RoleSchema)
def create_role(
    role_data: RoleCreateSchema,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    user_agent: Optional[str] = Header(None)
):
    """Create a new role (admin only)"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Check if role name already exists
    existing_role = db.query(Role).filter(Role.name == role_data.name).first()
    if existing_role:
        raise HTTPException(status_code=400, detail="Role name already exists")
    
    role = Role(
        name=role_data.name,
        description=role_data.description,
        is_system_role=0  # Custom role
    )
    
    db.add(role)
    db.commit()
    db.refresh(role)
    
    # Create audit log
    audit_log = AuditLog(
        user_id=user_id,
        action="CREATE_ROLE",
        entity_type="role",
        entity_id=role.id,
        entity_name=role.name,
        changes=role_data.model_dump(),
        ip_address=request.client.host if request.client else None,
        user_agent=user_agent
    )
    db.add(audit_log)
    db.commit()
    
    logger.info(f"Role created successfully: {role.id}")
    
    return role

@router.put("/roles/{role_id}", response_model=RoleSchema)
def update_role(
    role_id: int,
    role_data: RoleUpdateSchema,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    user_agent: Optional[str] = Header(None)
):
    """Update a role (admin only)"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Don't allow editing system roles
    if role.is_system_role:
        raise HTTPException(status_code=403, detail="Cannot modify system roles")
    
    # Check if name already exists (if name is being changed)
    if role_data.name and role_data.name != role.name:
        existing_role = db.query(Role).filter(Role.name == role_data.name).first()
        if existing_role:
            raise HTTPException(status_code=400, detail="Role name already exists")
    
    # Update fields
    if role_data.name:
        role.name = role_data.name
    if role_data.description is not None:
        role.description = role_data.description
    
    role.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(role)
    
    # Create audit log
    audit_log = AuditLog(
        user_id=user_id,
        action="UPDATE_ROLE",
        entity_type="role",
        entity_id=role.id,
        entity_name=role.name,
        changes=role_data.model_dump(exclude_unset=True),
        ip_address=request.client.host if request.client else None,
        user_agent=user_agent
    )
    db.add(audit_log)
    db.commit()
    
    logger.info(f"Role updated successfully: {role.id}")
    
    return role

@router.delete("/roles/{role_id}")
def delete_role(
    role_id: int,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    user_agent: Optional[str] = Header(None)
):
    """Delete a role (admin only)"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Don't allow deleting system roles
    if role.is_system_role:
        raise HTTPException(status_code=403, detail="Cannot delete system roles")
    
    role_name = role.name
    
    # Check if role is assigned to any users
    from sqlalchemy import select
    from backend.db.association_tables import user_roles
    stmt = select(user_roles).where(user_roles.c.role_id == role_id)
    result = db.execute(stmt).fetchall()
    if len(result) > 0:
        raise HTTPException(status_code=400, detail="Cannot delete role that is assigned to users")
    
    # Create audit log before deletion
    audit_log = AuditLog(
        user_id=user_id,
        action="DELETE_ROLE",
        entity_type="role",
        entity_id=role.id,
        entity_name=role_name,
        changes={"deleted": True},
        ip_address=request.client.host if request.client else None,
        user_agent=user_agent
    )
    db.add(audit_log)
    
    # Delete role
    db.delete(role)
    db.commit()
    
    logger.info(f"Role deleted successfully: {role_id}")
    
    return {"message": "Role deleted successfully"}

@router.post("/roles/{role_id}/assign/{user_id}")
def assign_role_to_user(
    role_id: int,
    user_id: int,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    user_agent: Optional[str] = Header(None)
):
    """Assign a role to a user (admin only)"""
    
    admin_id = claims.get("sub") or claims.get("user_id")
    admin_user = db.query(User).filter(User.id == admin_id).first()
    
    if not admin_user or admin_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if user already has this role
    from sqlalchemy import select
    stmt = select(user_roles).where(
        user_roles.c.user_id == user_id,
        user_roles.c.role_id == role_id
    )
    result = db.execute(stmt).fetchall()
    if len(result) > 0:
        raise HTTPException(status_code=400, detail="User already has this role")
    
    # Assign role to user
    from sqlalchemy import insert
    db.execute(insert(user_roles).values(user_id=user_id, role_id=role_id))
    
    # Create audit log
    audit_log = AuditLog(
        user_id=admin_id,
        action="ASSIGN_ROLE",
        entity_type="role",
        entity_id=role.id,
        entity_name=role.name,
        changes={
            "user_id": user_id,
            "username": user.username,
            "role_id": role_id,
            "role_name": role.name
        },
        ip_address=request.client.host if request.client else None,
        user_agent=user_agent
    )
    db.add(audit_log)
    db.commit()
    
    logger.info(f"Role {role_id} assigned to user {user_id}")
    
    return {"message": "Role assigned successfully"}

@router.delete("/roles/{role_id}/unassign/{user_id}")
def unassign_role_from_user(
    role_id: int,
    user_id: int,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    user_agent: Optional[str] = Header(None)
):
    """Remove a role from a user (admin only)"""
    
    admin_id = claims.get("sub") or claims.get("user_id")
    admin_user = db.query(User).filter(User.id == admin_id).first()
    
    if not admin_user or admin_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if user has this role
    from sqlalchemy import select
    from backend.db.association_tables import user_roles
    stmt = select(user_roles).where(
        user_roles.c.user_id == user_id,
        user_roles.c.role_id == role_id
    )
    result = db.execute(stmt).fetchall()
    if len(result) == 0:
        raise HTTPException(status_code=400, detail="User does not have this role")
    
    # Remove role from user
    from sqlalchemy import delete
    db.execute(delete(user_roles).where(
        user_roles.c.user_id == user_id,
        user_roles.c.role_id == role_id
    ))
    
    # Create audit log
    audit_log = AuditLog(
        user_id=admin_id,
        action="UNASSIGN_ROLE",
        entity_type="role",
        entity_id=role.id,
        entity_name=role.name,
        changes={
            "user_id": user_id,
            "username": user.username,
            "role_id": role_id,
            "role_name": role.name
        },
        ip_address=request.client.host if request.client else None,
        user_agent=user_agent
    )
    db.add(audit_log)
    db.commit()
    
    logger.info(f"Role {role_id} removed from user {user_id}")
    
    return {"message": "Role unassigned successfully"}

@router.get("/roles/{role_id}/users")
def get_role_users(
    role_id: int,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db)
):
    """Get all users with a specific role (admin only)"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Get all users with this role using simple raw SQL approach
    from sqlalchemy import text
    
    # Use raw SQL to avoid relationship issues
    query = text("""
        SELECT u.id, u.username, u.email, u.role, u.created_at
        FROM users u
        JOIN user_roles ur ON u.id = ur.user_id
        WHERE ur.role_id = :role_id
    """)
    
    result = db.execute(query, {"role_id": role_id}).fetchall()
    
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

@router.get("/roles/{role_id}/count")
def get_role_user_count(
    role_id: int,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db)
):
    """Get user count for a specific role (admin only)"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    
    # Get count of users with this role using raw SQL
    from sqlalchemy import text
    
    query = text("SELECT COUNT(*) FROM user_roles WHERE role_id = :role_id")
    count = db.execute(query, {"role_id": role_id}).scalar()
    
    return {"role_id": role_id, "user_count": count}