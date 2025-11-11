"""
Pages Extension Backend Module
Provides full pages management functionality with database models and API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List
from backend.database import get_db
from backend.utils.jwt_utils import decode_token
from backend.utils.auth_dep import try_get_claims, require_user
import json

# Database models will be created dynamically by the extension
# We'll use the existing Page model from the main application

def initialize_extension(context):
    """Initialize the Pages extension"""
    try:
        # Create database tables for pages (if not already exist)
        context.execute_query("""
            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT,
                slug TEXT UNIQUE NOT NULL DEFAULT '',
                is_public BOOLEAN NOT NULL DEFAULT 1,
                allowed_roles TEXT NOT NULL DEFAULT '[]',
                owner_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id)
            )
        """)

        # Create indexes for better performance
        context.execute_query("""
            CREATE INDEX IF NOT EXISTS idx_pages_slug ON pages(slug)
        """)
        context.execute_query("""
            CREATE INDEX IF NOT EXISTS idx_pages_owner ON pages(owner_id)
        """)
        context.execute_query("""
            CREATE INDEX IF NOT EXISTS idx_pages_public ON pages(is_public)
        """)

        # Register API routes
        router = APIRouter(prefix="/api/pages")

        @router.get("/read")
        def get_pages_list(
            authorization: Optional[str] = Header(None),
            claims: Optional[dict] = Depends(try_get_claims)
        ):
            """
            Get list of pages. Returns only public pages for anonymous users,
            public + owned/permitted pages for authenticated users.
            """
            try:
                if claims is None:
                    # Anonymous: only public pages
                    pages = context.execute_query("""
                        SELECT id, title, slug, is_public, owner_id
                        FROM pages
                        WHERE is_public = 1
                        ORDER BY title
                    """)
                else:
                    # Authenticated: get user info
                    user_id = claims.get("sub") or claims.get("user_id")
                    user_role = claims.get("role", "")

                    if user_role == "admin":
                        # Admin sees all pages
                        pages = context.execute_query("""
                            SELECT id, title, slug, is_public, owner_id
                            FROM pages
                            ORDER BY title
                        """)
                    else:
                        # Regular user: public pages + their own private pages
                        pages = context.execute_query("""
                            SELECT id, title, slug, is_public, owner_id
                            FROM pages
                            WHERE is_public = 1 OR owner_id = :user_id
                            ORDER BY title
                        """, {"user_id": user_id})

                return {
                    "items": [
                        {
                            "id": p["id"],
                            "title": p["title"],
                            "slug": p["slug"],
                            "is_public": bool(p["is_public"]),
                            "owner_id": p["owner_id"]
                        }
                        for p in (pages or [])
                    ]
                }
            except Exception as e:
                print(f"Error in get_pages_list: {e}")
                import traceback
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=f"Failed to fetch pages: {str(e)}")

        @router.post("/create")
        def create_page(
            page_data: dict,
            claims: dict = Depends(require_user)
        ):
            """Create a new page. Requires authentication."""
            user_id = claims.get("sub") or claims.get("user_id")
            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid token payload")

            # Generate slug if not provided
            slug = page_data.get("slug", "")
            if not slug:
                title = page_data.get("title", "")
                slug = title.lower().replace(" ", "-").replace("/", "-")

            # Insert page
            try:
                result = context.execute_query("""
                    INSERT INTO pages (title, content, slug, is_public, allowed_roles, owner_id)
                    VALUES (:title, :content, :slug, :is_public, :allowed_roles, :owner_id)
                """, {
                    "title": page_data.get("title"),
                    "content": page_data.get("content", ""),
                    "slug": slug,
                    "is_public": page_data.get("is_public", True),
                    "allowed_roles": json.dumps(page_data.get("allowed_roles", [])),
                    "owner_id": user_id
                })
                return {
                    "id": result[0]["last_insert_rowid()"] if result else None,
                    "title": page_data.get("title"),
                    "slug": slug,
                    "is_public": page_data.get("is_public", True)
                }
            except Exception as e:
                print(f"Error in create_page: {e}")
                raise

        @router.put("/{page_id}")
        def update_page(
            page_id: int,
            page_data: dict,
            claims: dict = Depends(require_user)
        ):
            """Update a page. Requires authentication and ownership/admin permission."""
            user_id = claims.get("sub") or claims.get("user_id")
            user_role = claims.get("role", "")

            # Check if page exists and get owner
            page = context.execute_query("""
                SELECT owner_id FROM pages WHERE id = :page_id
            """, {"page_id": page_id})

            if not page:
                raise HTTPException(status_code=404, detail="Page not found")

            # Check permission: owner or admin
            if str(page[0]["owner_id"]) != str(user_id) and user_role != "admin":
                raise HTTPException(status_code=403, detail="No permission to edit this page")

            # Generate slug if not provided
            slug = page_data.get("slug", "")
            if not slug and "title" in page_data:
                slug = page_data["title"].lower().replace(" ", "-").replace("/", "-")

            # Update page
            update_fields = []
            update_values = {}

            if "title" in page_data:
                update_fields.append("title = :title")
                update_values["title"] = page_data["title"]
            if "content" in page_data:
                update_fields.append("content = :content")
                update_values["content"] = page_data["content"]
            if "slug" in page_data or slug:
                update_fields.append("slug = :slug")
                update_values["slug"] = slug or page_data["slug"]
            if "is_public" in page_data:
                update_fields.append("is_public = :is_public")
                update_values["is_public"] = page_data["is_public"]
            if "allowed_roles" in page_data:
                update_fields.append("allowed_roles = :allowed_roles")
                update_values["allowed_roles"] = json.dumps(page_data["allowed_roles"])

            if update_fields:
                update_values["page_id"] = page_id
                context.execute_query(f"""
                    UPDATE pages
                    SET {', '.join(update_fields)}
                    WHERE id = :page_id
                """, update_values)

            return {"message": "Page updated successfully"}

        @router.delete("/{page_id}")
        def delete_page(
            page_id: int,
            claims: dict = Depends(require_user)
        ):
            """Delete a page. Requires authentication and ownership/admin permission."""
            user_id = claims.get("sub") or claims.get("user_id")
            user_role = claims.get("role", "")

            # Check if page exists and get owner
            page = context.execute_query("""
                SELECT owner_id FROM pages WHERE id = :page_id
            """, {"page_id": page_id})

            if not page:
                raise HTTPException(status_code=404, detail="Page not found")

            # Check permission: owner or admin
            if str(page[0]["owner_id"]) != str(user_id) and user_role != "admin":
                raise HTTPException(status_code=403, detail="No permission to delete this page")

            # Delete page
            context.execute_query("DELETE FROM pages WHERE id = :page_id", {"page_id": page_id})

            return {"message": "Page deleted successfully"}

        @router.get("/{slug}")
        def get_page_by_slug(slug: str, authorization: Optional[str] = Header(default=None)):
            try:
                # Find page by slug using named parameters
                page = context.execute_query("""
                    SELECT id, title, content, is_public, allowed_roles, owner_id
                    FROM pages
                    WHERE slug = :slug
                """, {"slug": slug})
                
                if not page:
                    raise HTTPException(status_code=404, detail="Page not found")

                page_data = page[0]
                title, content, is_public, allowed_roles, owner_id = page_data["title"], page_data["content"], page_data["is_public"], page_data["allowed_roles"], page_data["owner_id"]

                # Public page: allow anyone
                if is_public:
                    return {"title": title, "content": content}

                # Private page: require valid token
                if not authorization or not authorization.lower().startswith("bearer "):
                    raise HTTPException(status_code=401, detail="Authorization header missing or invalid format")

                token = authorization.split(" ", 1)[1].strip()
                claims = decode_token(token)

                user_id = claims.get("sub") or claims.get("user_id")
                if not user_id:
                    raise HTTPException(status_code=401, detail="Invalid token payload")

                # Check if user has access (owner or in allowed roles)
                if str(owner_id) == str(user_id):
                    return {"title": title, "content": content}

                # Check role-based access
                if allowed_roles:
                    try:
                        allowed = json.loads(allowed_roles)
                        if isinstance(allowed, list) and allowed:
                            user_role = claims.get("role")
                            if user_role and user_role in allowed:
                                return {"title": title, "content": content}
                    except Exception as e:
                        pass

                raise HTTPException(status_code=403, detail="Access denied")
            except Exception as e:
                print(f"Error in get_page_by_slug: {e}")
                import traceback
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        context.register_router(router)

        return {
            "routes_registered": 5,
            "tables_created": 1,
            "indexes_created": 3,
            "status": "initialized"
        }

    except Exception as e:
        print(f"Pages extension initialization error: {e}")
        return {"status": "error", "error": str(e)}

def cleanup_extension(context):
    """Cleanup when extension is disabled"""
    try:
        # Note: We don't drop tables as they might contain user data
        # The extension can be safely disabled while preserving data
        return {"status": "cleaned_up"}
    except Exception as e:
        print(f"Pages extension cleanup error: {e}")
        return {"status": "cleanup_error", "error": str(e)}