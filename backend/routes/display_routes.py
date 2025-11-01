from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import Optional
from backend.database import get_db
from backend.utils.jwt_utils import decode_token
from backend.utils.auth_dep import require_user, try_get_claims
from backend.db.user import User
from backend.db.display import Display
from backend.db.widget import Widget
from backend.schemas.display import (
    DisplayCreate, DisplayUpdate,
    WidgetCreate, WidgetUpdate,
    BulkLayoutUpdate
)
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class DisplaySchema(BaseModel):
    id: int
    user_id: int
    name: Optional[str] = None
    title: Optional[str] = None
    slug: str
    is_public: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

router = APIRouter()


def ensure_access(db: Session, user_id: int, display_id: int, require_owner: bool = False) -> Display:
    """Check if user has access to display (owner or has permissions)"""
    display = db.query(Display).filter(Display.id == display_id).first()
    if not display:
        raise HTTPException(status_code=404, detail="Display not found")
    
    # Check if user is owner
    if display.user_id == user_id:
        return display
    
    # If ownership is required (for delete/update operations), deny access
    if require_owner:
        raise HTTPException(status_code=403, detail="Only the owner can perform this action")
    
    # Check if user has permissions
    from backend.db.permission import Permission
    permission = db.query(Permission).filter(
        Permission.user_id == user_id,
        Permission.entity_type == "dashboard",
        Permission.entity_id == display_id
    ).first()
    
    if permission:
        return display
    
    # Check if display is public
    if display.is_public:
        return display
    
    raise HTTPException(status_code=403, detail="Access denied")

def ensure_owner(db: Session, user_id: int, display_id: int) -> Display:
    """Legacy function - ensures user is owner"""
    return ensure_access(db, user_id, display_id, require_owner=True)


@router.get("/display/read")
def read_displays(
    db: Session = Depends(get_db),
    claims: Optional[dict] = Depends(try_get_claims),
    limit: int = 100,
    offset: int = 0
):
    """Get all displays/dashboards - respects permissions"""
    if claims is None:
        # Anonymous: only public displays
        displays = db.query(Display).filter(Display.is_public == True).offset(offset).limit(limit).all()
    else:
        # Authenticated: get user info
        user_id = claims.get("sub") or claims.get("user_id")
        user_role = claims.get("role", "")
        
        if user_role == "admin":
            # Admin sees all displays
            displays = db.query(Display).offset(offset).limit(limit).all()
        else:
            # Regular user: public displays + their own + displays they have permissions for
            from sqlalchemy import or_
            from backend.db.permission import Permission
            
            # Get displays user has permissions for
            permitted_display_ids = db.query(Permission.entity_id).filter(
                Permission.user_id == user_id,
                Permission.entity_type == "dashboard"
            ).subquery()
            
            displays = db.query(Display).filter(
                or_(
                    Display.is_public == True,
                    Display.user_id == user_id,
                    Display.id.in_(permitted_display_ids)
                )
            ).offset(offset).limit(limit).all()
    
    items = []
    for d in displays:
        # Get owner username
        owner = db.query(User).filter(User.id == d.user_id).first()
        owner_username = owner.username if owner else "unknown"
        
        items.append({
            "id": d.id,
            "user_id": d.user_id,
            "owner_username": owner_username,  # Add owner username
            "name": d.title,  # Use title as name for compatibility
            "title": d.title,
            "slug": d.slug,
            "is_public": d.is_public,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None
        })
    return {
        "items": items,
        "total": len(items)  # Return actual count of filtered items
    }

@router.get("/api/displays/my")
def list_my_displays(claims: dict = Depends(require_user), db: Session = Depends(get_db)):
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)
    displays = db.query(Display).filter(Display.user_id == user_id).order_by(Display.created_at.desc()).all()
    return {"items": [{"id": d.id, "title": d.title, "slug": d.slug, "is_public": d.is_public} for d in displays]}


@router.post("/api/displays")
def create_display(payload: DisplayCreate, claims: dict = Depends(require_user), db: Session = Depends(get_db)):
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)
    # Enforce unique (user_id, slug)
    exists = db.query(Display).filter(Display.user_id == user_id, Display.slug == payload.slug).first()
    if exists:
        raise HTTPException(status_code=400, detail="Slug already exists for this user")
    d = Display(user_id=user_id, title=payload.title, slug=payload.slug, is_public=payload.is_public)
    db.add(d)
    db.commit()
    db.refresh(d)
    return {"id": d.id, "title": d.title, "slug": d.slug, "is_public": d.is_public}


@router.get("/api/displays/{display_id}")
def get_display(display_id: int, claims: dict = Depends(require_user), db: Session = Depends(get_db)):
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)
    # Allow access if user has permissions (not just owner)
    d = ensure_access(db, user_id, display_id, require_owner=False)
    
    # Get owner username
    owner = db.query(User).filter(User.id == d.user_id).first()
    owner_username = owner.username if owner else "unknown"
    
    return {
        "id": d.id,
        "title": d.title,
        "slug": d.slug,
        "is_public": d.is_public,
        "owner_username": owner_username
    }


@router.patch("/api/displays/{display_id}")
def update_display(display_id: int, payload: DisplayUpdate, claims: dict = Depends(require_user), db: Session = Depends(get_db)):
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)
    d = ensure_owner(db, user_id, display_id)
    if payload.title is not None:
        d.title = payload.title
    if payload.is_public is not None:
        d.is_public = payload.is_public
    db.commit()
    db.refresh(d)
    return {"id": d.id, "title": d.title, "slug": d.slug, "is_public": d.is_public}


@router.delete("/api/displays/{display_id}")
def delete_display(display_id: int, claims: dict = Depends(require_user), db: Session = Depends(get_db)):
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)
    d = ensure_owner(db, user_id, display_id)
    db.delete(d)
    db.commit()
    return {"message": "Display deleted"}


@router.get("/api/displays/{display_id}/widgets")
def list_widgets(display_id: int, claims: dict = Depends(require_user), db: Session = Depends(get_db)):
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)
    # Allow access if user has permissions (not just owner)
    ensure_access(db, user_id, display_id, require_owner=False)
    widgets = db.query(Widget).filter(Widget.display_id == display_id).order_by(Widget.z_index.asc()).all()
    return {"items": [serialize_widget(w) for w in widgets]}


@router.post("/api/displays/{display_id}/widgets")
def create_widget(display_id: int, payload: WidgetCreate, claims: dict = Depends(require_user), db: Session = Depends(get_db)):
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)
    
    # Check if user has edit permission (not just owner)
    d = db.query(Display).filter(Display.id == display_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Display not found")
    
    # Check if user is owner
    if d.user_id != user_id:
        # Not owner, check if user has edit permission
        from backend.db.permission import Permission, PermissionLevel
        permission = db.query(Permission).filter(
            Permission.user_id == user_id,
            Permission.entity_type == "dashboard",
            Permission.entity_id == display_id
        ).first()
        
        if not permission:
            raise HTTPException(status_code=403, detail="No permission to edit this dashboard")
        
        # Check permission level (need at least EDIT)
        level_hierarchy = {
            PermissionLevel.NONE: 0,
            PermissionLevel.VIEW: 1,
            PermissionLevel.EDIT: 2,
            PermissionLevel.DELETE: 3,
            PermissionLevel.ADMIN: 4
        }
        
        if level_hierarchy.get(permission.permission_level, 0) < level_hierarchy.get(PermissionLevel.EDIT, 2):
            raise HTTPException(status_code=403, detail="Insufficient permission level (need edit or higher)")
    
    if payload.type not in {"CLOCK", "TEXT", "RSS"}:
        raise HTTPException(status_code=422, detail="Invalid widget type")
    
    w = Widget(
        display_id=display_id,
        type=payload.type,
        config=payload.config or {},
        x=payload.x, y=payload.y, width=payload.width, height=payload.height, z_index=payload.z_index
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return serialize_widget(w)


@router.patch("/api/widgets/{widget_id}")
def update_widget(widget_id: int, payload: WidgetUpdate, claims: dict = Depends(require_user), db: Session = Depends(get_db)):
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)
    
    w = db.query(Widget).filter(Widget.id == widget_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Widget not found")
    
    # Check if user has edit permission for the display (owner or has edit/admin permission)
    d = db.query(Display).filter(Display.id == w.display_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Display not found")
    
    # Check if user is owner
    if d.user_id != user_id:
        # Not owner, check if user has edit permission
        from backend.db.permission import Permission, PermissionLevel
        permission = db.query(Permission).filter(
            Permission.user_id == user_id,
            Permission.entity_type == "dashboard",
            Permission.entity_id == d.id
        ).first()
        
        if not permission:
            raise HTTPException(status_code=403, detail="No permission to edit this dashboard")
        
        # Check permission level (need at least EDIT)
        level_hierarchy = {
            PermissionLevel.NONE: 0,
            PermissionLevel.VIEW: 1,
            PermissionLevel.EDIT: 2,
            PermissionLevel.DELETE: 3,
            PermissionLevel.ADMIN: 4
        }
        
        if level_hierarchy.get(permission.permission_level, 0) < level_hierarchy.get(PermissionLevel.EDIT, 2):
            raise HTTPException(status_code=403, detail="Insufficient permission level (need edit or higher)")
    
    # User has permission, update the widget
    if payload.config is not None:
        w.config = payload.config
    if payload.x is not None: w.x = payload.x
    if payload.y is not None: w.y = payload.y
    if payload.width is not None: w.width = payload.width
    if payload.height is not None: w.height = payload.height
    if payload.z_index is not None: w.z_index = payload.z_index
    db.commit()
    db.refresh(w)
    return serialize_widget(w)


@router.delete("/api/widgets/{widget_id}")
def delete_widget(widget_id: int, claims: dict = Depends(require_user), db: Session = Depends(get_db)):
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)
    
    w = db.query(Widget).filter(Widget.id == widget_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Widget not found")
    
    d = db.query(Display).filter(Display.id == w.display_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Display not found")
    
    # Check if user is owner
    if d.user_id != user_id:
        # Not owner, check if user has delete permission
        from backend.db.permission import Permission, PermissionLevel
        permission = db.query(Permission).filter(
            Permission.user_id == user_id,
            Permission.entity_type == "dashboard",
            Permission.entity_id == d.id
        ).first()
        
        if not permission:
            raise HTTPException(status_code=403, detail="No permission to delete from this dashboard")
        
        # Check permission level (need at least DELETE)
        level_hierarchy = {
            PermissionLevel.NONE: 0,
            PermissionLevel.VIEW: 1,
            PermissionLevel.EDIT: 2,
            PermissionLevel.DELETE: 3,
            PermissionLevel.ADMIN: 4
        }
        
        if level_hierarchy.get(permission.permission_level, 0) < level_hierarchy.get(PermissionLevel.DELETE, 3):
            raise HTTPException(status_code=403, detail="Insufficient permission level (need delete or higher)")
    
    db.delete(w)
    db.commit()
    return {"message": "Widget deleted"}


@router.post("/api/widgets/bulk-layout")
def bulk_layout(payload: BulkLayoutUpdate, claims: dict = Depends(require_user), db: Session = Depends(get_db)):
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user_id = int(user_id)
    # Fetch all widgets by IDs and check ownership via their displays
    ids = [item.id for item in payload.widgets]
    if not ids:
        return {"updated": 0}
    widgets = db.query(Widget).filter(Widget.id.in_(ids)).all()
    if not widgets:
        return {"updated": 0}
    display_ids = {w.display_id for w in widgets}
    displays = db.query(Display).filter(Display.id.in_(display_ids)).all()
    owner_ok = all(d.user_id == user_id for d in displays)
    if not owner_ok:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Update positions
    index_by_id = {item.id: item for item in payload.widgets}
    for w in widgets:
        item = index_by_id.get(w.id)
        if item:
            w.x, w.y, w.width, w.height, w.z_index = item.x, item.y, item.width, item.height, item.z_index
    db.commit()

    return {"updated": len(widgets)}


def serialize_widget(w: Widget):
    return {
        "id": w.id,
        "display_id": w.display_id,
        "type": w.type,
        "config": w.config or {},
        "x": w.x, "y": w.y, "width": w.width, "height": w.height, "z_index": w.z_index,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "updated_at": w.updated_at.isoformat() if w.updated_at else None,
    }


@router.get("/api/public/@{username}/{slug}")
def public_display(username: str, slug: str, db: Session = Depends(get_db)):
    # Resolve user by username
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Resolve display by slug
    d = db.query(Display).filter(Display.user_id == user.id, Display.slug == slug, Display.is_public == True).first()
    if not d:
        raise HTTPException(status_code=404, detail="Display not found or not public")
    widgets = db.query(Widget).filter(Widget.display_id == d.id).order_by(Widget.z_index.asc()).all()
    return {
        "display": {"id": d.id, "title": d.title, "slug": d.slug, "is_public": d.is_public},
        "widgets": [serialize_widget(w) for w in widgets]
    }
