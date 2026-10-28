from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session as DBSession
from typing import List, Optional
from datetime import datetime
from backend.db.permission import Permission, PermissionSchema, PermissionCreateSchema, PermissionLevel
from backend.db.user import User
from backend.db.audit_log import AuditLog
from backend.utils.db_utils import get_db
from backend.utils.auth_dep import require_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

def check_permission(
    db: DBSession,
    user_id: int,
    entity_type: str,
    entity_id: int,
    required_level: PermissionLevel
) -> bool:
    """Check if user has required permission level for an entity"""
    
    # Check if user is admin
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.role == "admin":
        return True
    
    # Check specific permission
    permission = db.query(Permission).filter(
        Permission.user_id == user_id,
        Permission.entity_type == entity_type,
        Permission.entity_id == entity_id
    ).first()
    
    if not permission:
        return False
    
    # Check if permission has expired
    if permission.expires_at and permission.expires_at < datetime.utcnow():
        return False
    
    # Check permission level hierarchy
    level_hierarchy = {
        PermissionLevel.NONE: 0,
        PermissionLevel.VIEW: 1,
        PermissionLevel.EDIT: 2,
        PermissionLevel.DELETE: 3,
        PermissionLevel.ADMIN: 4
    }
    
    return level_hierarchy.get(permission.permission_level, 0) >= level_hierarchy.get(required_level, 0)

def check_extension_permission(
    db: DBSession,
    user_id: int,
    extension_name: str,
    required_level: PermissionLevel
) -> bool:
    """Check if user has required permission level for an extension"""
    
    # Get extension by name
    from backend.db.extension import Extension
    extension = db.query(Extension).filter(Extension.name == extension_name).first()
    if not extension:
        return False
    
    # Check if extension is enabled
    if not extension.is_enabled:
        return False
    
    return check_permission(db, user_id, "extension", extension.id, required_level)

def get_user_extension_permissions(
    db: DBSession,
    user_id: int
) -> List[dict]:
    """Get all extension permissions for a user"""
    
    from backend.db.extension import Extension
    
    # Get all extension permissions for the user
    extension_perms = db.query(Permission).filter(
        Permission.user_id == user_id,
        Permission.entity_type == "extension"
    ).all()
    
    result = []
    for perm in extension_perms:
        extension = db.query(Extension).filter(Extension.id == perm.entity_id).first()
        if extension:
            result.append({
                "permission_id": perm.id,
                "extension_id": extension.id,
                "extension_name": extension.name,
                "extension_version": extension.version,
                "extension_type": extension.type,
                "permission_level": perm.permission_level.value if hasattr(perm.permission_level, 'value') else str(perm.permission_level),
                "granted_at": perm.granted_at,
                "expires_at": perm.expires_at
            })
    
    return result

@router.post("/permissions")
def grant_permission(
    permission_data: PermissionCreateSchema,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    user_agent: Optional[str] = Header(None)
):
    """Grant permission to a user for an entity"""
    
    try:
        granter_id = claims.get("sub") or claims.get("user_id")
        logger.info(f"Granting permission: {permission_data.model_dump()} by user {granter_id}")
        
        # Check if user is admin (admins can grant any permission)
        granter_user = db.query(User).filter(User.id == granter_id).first()
        if not granter_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # If not admin, check if they have admin permission for this entity
        if granter_user.role != "admin":
            if not check_permission(db, granter_id, permission_data.entity_type, 
                                  permission_data.entity_id, PermissionLevel.ADMIN):
                raise HTTPException(status_code=403, detail="You don't have permission to grant access")
        
        # Check if permission already exists
        existing = db.query(Permission).filter(
            Permission.user_id == permission_data.user_id,
            Permission.entity_type == permission_data.entity_type,
            Permission.entity_id == permission_data.entity_id
        ).first()
        
        if existing:
            # Update existing permission
            try:
                existing.permission_level = PermissionLevel[permission_data.permission_level.upper()]
            except KeyError:
                # If enum fails, try direct assignment
                existing.permission_level = permission_data.permission_level
            existing.granted_by = granter_id
            existing.granted_at = datetime.utcnow()
            existing.expires_at = permission_data.expires_at
            db.commit()
            db.refresh(existing)
            permission = existing
        else:
            # Create new permission
            try:
                perm_level = PermissionLevel[permission_data.permission_level.upper()]
            except KeyError:
                # If enum fails, try direct assignment
                perm_level = permission_data.permission_level
                
            permission = Permission(
                user_id=permission_data.user_id,
                entity_type=permission_data.entity_type,
                entity_id=permission_data.entity_id,
                permission_level=perm_level,
                granted_by=granter_id,
                expires_at=permission_data.expires_at
            )
            db.add(permission)
            db.commit()
            db.refresh(permission)
        
        # Create audit log
        target_user = db.query(User).filter(User.id == permission_data.user_id).first()
        audit_log = AuditLog(
            user_id=granter_id,
            action="GRANT_PERMISSION",
            entity_type="permission",
            entity_id=permission.id,
            entity_name=f"{permission_data.entity_type}:{permission_data.entity_id}",
            changes={
                "user": target_user.username if target_user else permission_data.user_id,
                "level": permission_data.permission_level
            },
            ip_address=request.client.host if request.client else None,
            user_agent=user_agent
        )
        db.add(audit_log)
        db.commit()
        
        logger.info(f"Permission granted successfully: {permission.id}")
        
        # Return a dictionary instead of the ORM object to avoid serialization issues
        return {
            "id": permission.id,
            "user_id": permission.user_id,
            "entity_type": permission.entity_type,
            "entity_id": permission.entity_id,
            "permission_level": permission.permission_level.value if hasattr(permission.permission_level, 'value') else str(permission.permission_level),
            "granted_by": permission.granted_by,
            "granted_at": permission.granted_at,
            "expires_at": permission.expires_at
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error granting permission: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error granting permission: {str(e)}")

@router.delete("/permissions/{permission_id}")
def revoke_permission(
    permission_id: int,
    request: Request,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    user_agent: Optional[str] = Header(None)
):
    """Revoke a permission"""
    
    revoker_id = claims.get("sub") or claims.get("user_id")
    
    # Get the permission
    permission = db.query(Permission).filter(Permission.id == permission_id).first()
    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")
    
    # Check if revoker has admin permission for this entity
    if not check_permission(db, revoker_id, permission.entity_type, 
                          permission.entity_id, PermissionLevel.ADMIN):
        raise HTTPException(status_code=403, detail="You don't have permission to revoke access")
    
    # Create audit log before deletion
    target_user = db.query(User).filter(User.id == permission.user_id).first()
    audit_log = AuditLog(
        user_id=revoker_id,
        action="REVOKE_PERMISSION",
        entity_type="permission",
        entity_id=permission_id,
        entity_name=f"{permission.entity_type}:{permission.entity_id}",
        changes={
            "user": target_user.username if target_user else permission.user_id,
            "level": permission.permission_level.value
        },
        ip_address=request.client.host,
        user_agent=user_agent
    )
    db.add(audit_log)
    
    # Delete permission
    db.delete(permission)
    db.commit()
    
    return {"message": "Permission revoked successfully"}

@router.get("/permissions/entity/{entity_type}/{entity_id}")
def get_entity_permissions(
    entity_type: str,
    entity_id: int,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db)
):
    """Get all permissions for an entity"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    
    # Check if user has admin permission for this entity
    if not check_permission(db, user_id, entity_type, entity_id, PermissionLevel.ADMIN):
        raise HTTPException(status_code=403, detail="You don't have permission to view access list")
    
    permissions = db.query(Permission).filter(
        Permission.entity_type == entity_type,
        Permission.entity_id == entity_id
    ).all()
    
    # Include user information
    result = []
    for perm in permissions:
        user = db.query(User).filter(User.id == perm.user_id).first()
        result.append({
            "id": perm.id,
            "user_id": perm.user_id,
            "username": user.username if user else None,
            "email": user.email if user else None,
            "permission_level": perm.permission_level.value,
            "granted_at": perm.granted_at,
            "expires_at": perm.expires_at
        })
    
    return result

@router.get("/permissions/my")
def get_my_permissions(
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    entity_type: Optional[str] = None
):
    """Get all permissions for the current user"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    
    query = db.query(Permission).filter(Permission.user_id == user_id)
    
    if entity_type:
        query = query.filter(Permission.entity_type == entity_type)
    
    permissions = query.all()
    
    return permissions

@router.get("/permissions/all")
def get_all_permissions(
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db),
    entity_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    """Get all permissions (admin only) with entity names"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    query = db.query(Permission)
    
    if entity_type:
        query = query.filter(Permission.entity_type == entity_type)
    
    permissions = query.offset(offset).limit(limit).all()
    
    # Enrich with entity names and user info
    result = []
    for perm in permissions:
        perm_data = {
            "id": perm.id,
            "user_id": perm.user_id,
            "entity_type": perm.entity_type,
            "entity_id": perm.entity_id,
            "permission_level": perm.permission_level.value if hasattr(perm.permission_level, 'value') else perm.permission_level,
            "granted_at": perm.granted_at,
            "expires_at": perm.expires_at
        }
        
        # Get user info
        target_user = db.query(User).filter(User.id == perm.user_id).first()
        if target_user:
            perm_data["username"] = target_user.username
            perm_data["user_email"] = target_user.email
        
        # Get entity name based on type
        if perm.entity_type == "page":
            from backend.db.page import Page
            page = db.query(Page).filter(Page.id == perm.entity_id).first()
            if page:
                perm_data["entity_name"] = page.title
                perm_data["entity_slug"] = page.slug
        elif perm.entity_type == "dashboard":
            from backend.db.display import Display
            dashboard = db.query(Display).filter(Display.id == perm.entity_id).first()
            if dashboard:
                perm_data["entity_name"] = dashboard.title  # Use title instead of name
                perm_data["entity_slug"] = dashboard.slug
        elif perm.entity_type == "extension":
            from backend.db.extension import Extension
            extension = db.query(Extension).filter(Extension.id == perm.entity_id).first()
            if extension:
                perm_data["entity_name"] = f"{extension.name} v{extension.version}"
                perm_data["entity_slug"] = extension.name
                perm_data["extension_type"] = extension.type
                perm_data["description"] = extension.description
        
        result.append(perm_data)
    
    return result

@router.get("/permissions/entities")
def get_available_entities(
    entity_type: str,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db)
):
    """Get available entities for permission assignment (admin only)"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    entities = []
    
    if entity_type == "page":
        from backend.db.page import Page
        pages = db.query(Page).all()
        for page in pages:
            entities.append({
                "id": page.id,
                "name": page.title,
                "slug": page.slug,
                "description": page.description
            })
    elif entity_type == "dashboard":
        from backend.db.display import Display
        dashboards = db.query(Display).all()
        for dashboard in dashboards:
            entities.append({
                "id": dashboard.id,
                "name": dashboard.title,
                "slug": dashboard.slug,
                "description": dashboard.description
            })
    elif entity_type == "extension":
        from backend.db.extension import Extension
        extensions = db.query(Extension).all()
        for ext in extensions:
            entities.append({
                "id": ext.id,
                "name": f"{ext.name} v{ext.version}",
                "slug": ext.name,
                "description": ext.description,
                "type": ext.type,
                "status": ext.status,
                "is_enabled": ext.is_enabled
            })
    
    return entities

@router.get("/permissions/extension-types")
def get_extension_types(
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db)
):
    """Get all available extension types (admin only)"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    from backend.db.extension import Extension
    
    # Get distinct extension types
    extension_types = db.query(Extension.type).distinct().all()
    types = [ext_type[0] for ext_type in extension_types if ext_type[0]]
    
    return {"types": types}

@router.get("/permissions/my/extensions")
def get_my_extension_permissions(
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db)
):
    """Get all extension permissions for the current user"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    
    return get_user_extension_permissions(db, user_id)

@router.get("/permissions/check")
def check_user_permission(
    entity_type: str,
    entity_id: int,
    required_level: str,
    claims: dict = Depends(require_user),
    db: DBSession = Depends(get_db)
):
    """Check if current user has required permission level"""
    
    user_id = claims.get("sub") or claims.get("user_id")
    
    has_permission = check_permission(
        db, user_id, entity_type, entity_id, 
        PermissionLevel[required_level.upper()]
    )
    
    return {"has_permission": has_permission}