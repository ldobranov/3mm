from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import Optional, List
from backend.db.page import Page
from backend.db.user import User
from backend.database import get_db
from backend.utils.jwt_utils import decode_token
from backend.utils.auth_dep import try_get_claims, require_user
import json

router = APIRouter()

@router.get("/read")
def get_pages_list(
    claims: Optional[dict] = Depends(try_get_claims),
    db: Session = Depends(get_db)
):
    """
    Get list of pages. Returns only public pages for anonymous users,
    public + owned/permitted pages for authenticated users.
    """
    # Debug logging
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Pages /read - Claims: {claims}")
    
    if claims is None:
        # Anonymous: only public pages
        logger.info("No claims - returning public pages only")
        pages = db.query(Page).filter(Page.is_public == True).all()
    else:
        # Authenticated: get user info
        user_id = claims.get("sub") or claims.get("user_id")
        user_role = claims.get("role", "")
        
        if user_role == "admin":
            # Admin sees all pages
            pages = db.query(Page).all()
        else:
            # Regular user: public pages + their own private pages + pages they have permissions for
            from sqlalchemy import or_
            from backend.db.permission import Permission, PermissionLevel
            
            # Get pages user has permissions for
            permitted_page_ids = db.query(Permission.entity_id).filter(
                Permission.user_id == user_id,
                Permission.entity_type == "page"
            ).subquery()
            
            pages = db.query(Page).filter(
                or_(
                    Page.is_public == True,
                    Page.owner_id == user_id,
                    Page.id.in_(permitted_page_ids)
                )
            ).all()
    
    return {
        "items": [
            {
                "id": p.id,
                "title": p.title,
                "slug": p.slug,
                "is_public": p.is_public,
                "owner_id": p.owner_id
            }
            for p in pages
        ]
    }

@router.post("/create")
def create_page(
    page_data: dict,
    claims: dict = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Create a new page. Requires authentication."""
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    
    # Create page with owner
    new_page = Page(
        title=page_data.get("title"),
        slug=page_data.get("slug"),
        content=page_data.get("content", ""),
        is_public=page_data.get("is_public", False),
        allowed_roles=page_data.get("allowed_roles"),
        owner_id=user_id
    )
    db.add(new_page)
    db.commit()
    db.refresh(new_page)
    
    return {
        "id": new_page.id,
        "title": new_page.title,
        "slug": new_page.slug,
        "is_public": new_page.is_public
    }

@router.put("/{page_id}")
def update_page(
    page_id: int,
    page_data: dict,
    claims: dict = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Update a page. Requires authentication and ownership/admin/edit permission."""
    user_id = claims.get("sub") or claims.get("user_id")
    user_role = claims.get("role", "")
    
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    # Check permission: owner, admin, or has edit permission
    if str(page.owner_id) != str(user_id) and user_role != "admin":
        # Not owner or admin, check if user has edit permission
        from backend.db.permission import Permission, PermissionLevel
        permission = db.query(Permission).filter(
            Permission.user_id == user_id,
            Permission.entity_type == "page",
            Permission.entity_id == page_id
        ).first()
        
        if not permission:
            raise HTTPException(status_code=403, detail="No permission to edit this page")
        
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
    
    # Update fields
    if "title" in page_data:
        page.title = page_data["title"]
    if "slug" in page_data:
        page.slug = page_data["slug"]
    if "content" in page_data:
        page.content = page_data["content"]
    if "is_public" in page_data:
        page.is_public = page_data["is_public"]
    if "allowed_roles" in page_data:
        page.allowed_roles = page_data["allowed_roles"]
    
    db.commit()
    db.refresh(page)
    
    return {
        "id": page.id,
        "title": page.title,
        "slug": page.slug,
        "is_public": page.is_public
    }

@router.delete("/{page_id}")
def delete_page(
    page_id: int,
    claims: dict = Depends(require_user),
    db: Session = Depends(get_db)
):
    """Delete a page. Requires authentication and ownership/admin/delete permission."""
    user_id = claims.get("sub") or claims.get("user_id")
    user_role = claims.get("role", "")
    
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    # Check permission: owner, admin, or has delete permission
    if str(page.owner_id) != str(user_id) and user_role != "admin":
        # Not owner or admin, check if user has delete permission
        from backend.db.permission import Permission, PermissionLevel
        permission = db.query(Permission).filter(
            Permission.user_id == user_id,
            Permission.entity_type == "page",
            Permission.entity_id == page_id
        ).first()
        
        if not permission:
            raise HTTPException(status_code=403, detail="No permission to delete this page")
        
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
    
    db.delete(page)
    db.commit()
    
    return {"message": "Page deleted successfully"}

@router.get("/{slug}")
def get_page_by_slug(slug: str, authorization: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    page = Page.get_by_slug(db, slug)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    # Public page: allow anyone
    if page.is_public:
        return {"title": page.title, "content": page.content}

    # Private page: require valid token
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authorization header missing or invalid format")

    token = authorization.split(" ", 1)[1].strip()
    claims = decode_token(token)  # raises HTTPException with 401 on failure

    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Role-based restrictions if present
    allowed = getattr(page, "allowed_roles", None)
    if allowed:
        if isinstance(allowed, str):
            try:
                allowed = json.loads(allowed)
            except Exception:
                allowed = [x.strip() for x in allowed.split(",") if x.strip()]
        if isinstance(allowed, list) and allowed:
            if not user.role or user.role not in allowed:
                raise HTTPException(status_code=403, detail="Forbidden: insufficient role")

# Optional: owner-only guard if you have an ownership rule
# if getattr(page, "owner_id", None) and str(page.owner_id) != str(user_id):
#     raise HTTPException(status_code=403, detail="Forbidden: not owner")

    return {"title": page.title, "content": page.content}
