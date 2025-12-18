"""
Pages Extension Backend Module
Provides full pages management functionality with database models and API endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Request, Form
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional, List, Dict, Any
from backend.database import get_db
from backend.utils.jwt_utils import decode_token
from backend.utils.auth_dep import try_get_claims, require_user
from backend.utils.extension_relationships import declare_extension_capabilities, call_api_endpoint
import json
import os

def execute_main_db_query(query: str, params: dict = None):
    """Execute query using main database session"""
    db = next(get_db())
    try:
        result = db.execute(text(query), params or {})
        rows = []
        if result.returns_rows:
            for row in result.fetchall():
                if hasattr(row, '_mapping'):
                    rows.append(dict(row._mapping))
                else:
                    rows.append(dict(row))
        db.commit()
        return rows
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

# Dynamic Extension Discovery System (similar to frontend extension-relationships.ts)
class BackendExtensionDiscovery:
    """Backend extension discovery system that dynamically finds extensions and loads their schemas"""

    def __init__(self):
        self.extensions_dir = os.path.join(os.path.dirname(__file__), '..')
        self.extension_schemas = {}
        self.form_handlers = {}

    def discover_extensions(self) -> List[str]:
        """Discover available extensions by scanning the extensions directory"""
        try:
            if not os.path.exists(self.extensions_dir):
                print(f"Extensions directory not found: {self.extensions_dir}")
                return []

            # List all directories in extensions folder
            all_items = os.listdir(self.extensions_dir)
            extensions = []

            for item in all_items:
                item_path = os.path.join(self.extensions_dir, item)
                if os.path.isdir(item_path):
                    # Check if it looks like an extension (has manifest.json)
                    manifest_path = os.path.join(item_path, 'manifest.json')
                    if os.path.exists(manifest_path):
                        # Extract extension name (remove version suffix)
                        extension_name = item.rsplit('_', 1)[0] if '_' in item else item
                        extensions.append(extension_name)

            print(f"Discovered {len(extensions)} extensions:", extensions)
            return extensions
        except Exception as e:
            print(f"Error discovering extensions: {e}")
            return []

    def load_extension_schema(self, extension_name: str) -> Dict[str, Dict[str, Any]]:
        """Load database schema for an extension from its database_schema.json"""
        if extension_name in self.extension_schemas:
            return self.extension_schemas[extension_name]

        try:
            # Find the extension directory (with version)
            extension_dirs = [d for d in os.listdir(self.extensions_dir)
                            if os.path.isdir(os.path.join(self.extensions_dir, d)) and
                            d.startswith(f"{extension_name}_")]

            if not extension_dirs:
                print(f"No extension directory found for {extension_name}")
                return {}

            extension_dir = extension_dirs[0]  # Take the first one
            schema_path = os.path.join(self.extensions_dir, extension_dir, 'database_schema.json')

            if os.path.exists(schema_path):
                with open(schema_path, 'r') as f:
                    schema = json.load(f)
                    self.extension_schemas[extension_name] = schema
                    print(f"Loaded schema for {extension_name}: {schema}")
                    return schema
            else:
                print(f"No database_schema.json found for {extension_name}")
                return {}
        except Exception as e:
            print(f"Error loading schema for {extension_name}: {e}")
            return {}

    def get_form_handler(self, extension_name: str, table_name: str = None) -> 'DynamicFormHandler':
        """Get or create a form handler for an extension table"""
        handler_key = f"{extension_name}.{table_name}" if table_name else extension_name

        if handler_key in self.form_handlers:
            return self.form_handlers[handler_key]

        # Load schema for this extension
        schema = self.load_extension_schema(extension_name)
        if not schema:
            # Fallback to empty schema
            schema = {}

        # Create form handler
        handler = DynamicFormHandler(schema)
        self.form_handlers[handler_key] = handler
        return handler

# Dynamic Form Parameter Handler (similar to frontend extension-relationships.ts)
class DynamicFormHandler:
    """Dynamic form parameter handler that extracts form data based on schema"""

    def __init__(self, schema: Dict[str, Dict[str, Any]]):
        self.schema = schema
        self.updatable_fields = [
            field_name for field_name, field_config in schema.items()
            if not field_config.get("primary_key", False) and
               field_name not in ["created_at", "updated_at", "owner_id"]
        ]

    async def extract_form_data(self, request: Request) -> Dict[str, Any]:
        """Extract form data dynamically based on schema"""
        form_data = {}

        # Parse the multipart form data
        form = await request.form()
        print(f"DEBUG: Raw form data received: {list(form.keys())}")

        for field_name in self.updatable_fields:
            field_config = self.schema[field_name]
            field_type = field_config.get("type", "text")

            # Get value from form
            value = form.get(field_name)
            print(f"DEBUG: Processing field {field_name} (type: {field_type}), value: {value}, value type: {type(value)}")

            if value is not None:
                # Convert based on field type
                if field_type == "boolean":
                    # Handle boolean conversion
                    if isinstance(value, str):
                        form_data[field_name] = value.lower() in ("true", "1", "yes", "on")
                    else:
                        form_data[field_name] = bool(value)
                elif field_type == "integer":
                    try:
                        form_data[field_name] = int(value)
                    except (ValueError, TypeError):
                        form_data[field_name] = value
                elif field_type == "decimal":
                    try:
                        form_data[field_name] = float(value)
                    except (ValueError, TypeError):
                        form_data[field_name] = value
                else:
                    # Text and other types
                    form_data[field_name] = value

                # Special handling for JSON fields
                if field_name == "allowed_roles" and isinstance(form_data[field_name], str):
                    try:
                        form_data[field_name] = json.loads(form_data[field_name])
                    except (json.JSONDecodeError, TypeError):
                        # If it's not valid JSON, treat as plain string
                        pass

        print(f"DEBUG: Final extracted form_data: {form_data}")
        return form_data

# Global extension discovery instance (similar to frontend extensionRelationships)
extension_discovery = BackendExtensionDiscovery()

# Initialize extension discovery on module load
available_extensions = extension_discovery.discover_extensions()

# Get form handler for PagesExtension (dynamically loaded)
page_form_handler = extension_discovery.get_form_handler("PagesExtension")

# Database models will be created dynamically by the extension
# We'll use the existing Page model from the main application

def initialize_extension(context):
    """Initialize the Pages extension"""
    try:
        # Get the table name (extension database uses prefixed tables)
        table_name = "ext_pagesextension"

        # Note: Table creation is handled by the extension database system
        # using database_schema.json and ExtensionTableCreator

        # Ensure the table exists with proper schema
        try:
            # Check if table exists
            result = context.execute_query(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = '{table_name}'
                )
            """)
            table_exists = result[0]['exists'] if result and len(result) > 0 else False

            if not table_exists:
                # Create the table with proper schema
                context.execute_query(f"""
                    CREATE TABLE "{table_name}" (
                        id SERIAL PRIMARY KEY,
                        title TEXT NOT NULL,
                        content TEXT,
                        slug TEXT NOT NULL,
                        is_public BOOLEAN NOT NULL,
                        allowed_roles TEXT NOT NULL,
                        owner_id INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Create indexes
                context.execute_query(f'CREATE INDEX IF NOT EXISTS idx_{table_name.replace(".", "_")}_slug ON "{table_name}" (slug)')
                context.execute_query(f'CREATE INDEX IF NOT EXISTS idx_{table_name.replace(".", "_")}_owner ON "{table_name}" (owner_id)')
                context.execute_query(f'CREATE INDEX IF NOT EXISTS idx_{table_name.replace(".", "_")}_public ON "{table_name}" (is_public)')
        except Exception as e:
            # Try to create anyway
            try:
                execute_main_db_query(f"""
                    CREATE TABLE IF NOT EXISTS "{table_name}" (
                        id SERIAL PRIMARY KEY,
                        title TEXT NOT NULL,
                        content TEXT,
                        slug TEXT NOT NULL,
                        is_public BOOLEAN NOT NULL,
                        allowed_roles TEXT NOT NULL,
                        owner_id INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            except Exception as e2:
                pass

        # Create translations table for multilingual support
        translations_table = f"{table_name}_translations"
        try:
            result = execute_main_db_query(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = '{translations_table}'
                )
            """)
            table_exists = result[0]['exists'] if result and len(result) > 0 else False

            if not table_exists:
                context.execute_query(f"""
                    CREATE TABLE "{translations_table}" (
                        id SERIAL PRIMARY KEY,
                        record_id INTEGER NOT NULL,
                        language_code TEXT NOT NULL,
                        translation_data JSONB NOT NULL,
                        translation_coverage DECIMAL(5,2) DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(record_id, language_code)
                    )
                """)
        except Exception as e:
            pass

        # Register tables with the extension registry for proper uninstall support
        try:
            # Get the extension database ID from name/version
            extension_name, extension_version = context.extension_id.rsplit('_', 1)
            extension_result = execute_main_db_query("""
                SELECT id FROM extensions
                WHERE name = :name AND version = :version
            """, {"name": extension_name, "version": extension_version})

            if extension_result:
                extension_db_id = extension_result[0]["id"]

                # Define table schemas for registration
                table_schemas = {
                    table_name: {
                        "id": {"type": "integer", "primary_key": True},
                        "title": {"type": "text", "multilingual": True},
                        "content": {"type": "text", "multilingual": True},
                        "slug": {"type": "text"},
                        "is_public": {"type": "boolean"},
                        "allowed_roles": {"type": "text"},
                        "owner_id": {"type": "integer"},
                        "created_at": {"type": "timestamp"},
                        "updated_at": {"type": "timestamp"}
                    },
                    translations_table: {
                        "id": {"type": "integer", "primary_key": True},
                        "record_id": {"type": "integer"},
                        "language_code": {"type": "text"},
                        "translation_data": {"type": "jsonb"},
                        "translation_coverage": {"type": "decimal"},
                        "created_at": {"type": "timestamp"},
                        "updated_at": {"type": "timestamp"}
                    }
                }

                # Register each table synchronously using direct SQL
                for tbl_name, schema in table_schemas.items():
                    translatable_fields = [field for field, config in schema.items() if config.get("multilingual", False)]

                    execute_main_db_query("""
                        INSERT INTO extension_tables
                        (extension_id, table_name, table_schema, translatable_fields, primary_key_field, is_multilingual)
                        VALUES (:extension_id, :table_name, :table_schema, :translatable_fields, :primary_key, :is_multilingual)
                        ON CONFLICT (extension_id, table_name) DO UPDATE SET
                            table_schema = EXCLUDED.table_schema,
                            translatable_fields = EXCLUDED.translatable_fields,
                            primary_key_field = EXCLUDED.primary_key_field,
                            is_multilingual = EXCLUDED.is_multilingual
                    """, {
                        "extension_id": extension_db_id,
                        "table_name": tbl_name,
                        "table_schema": json.dumps(schema),
                        "translatable_fields": json.dumps(translatable_fields),
                        "primary_key": "id",
                        "is_multilingual": len(translatable_fields) > 0
                    })

                    # Register fields
                    for field_name, field_config in schema.items():
                        try:
                            execute_main_db_query("""
                                INSERT INTO extension_fields
                                (extension_id, table_name, field_name, field_type, is_translatable, validation_rules, field_order)
                                VALUES (:extension_id, :table_name, :field_name, :field_type, :is_translatable, :validation_rules, :field_order)
                                ON CONFLICT (extension_id, table_name, field_name) DO UPDATE SET
                                    field_type = EXCLUDED.field_type,
                                    is_translatable = EXCLUDED.is_translatable,
                                    validation_rules = EXCLUDED.validation_rules,
                                    field_order = EXCLUDED.field_order
                            """, {
                                "extension_id": extension_db_id,
                                "table_name": tbl_name,
                                "field_name": field_name,
                                "field_type": field_config.get("type", "text"),
                                "is_translatable": field_config.get("multilingual", False),
                                "validation_rules": json.dumps(field_config.get("validation", {})),
                                "field_order": field_config.get("order", 0)
                            })
                        except Exception as field_error:
                            if "ON CONFLICT" in str(field_error):
                                # Try INSERT without ON CONFLICT first
                                execute_main_db_query("""
                                    INSERT INTO extension_fields
                                    (extension_id, table_name, field_name, field_type, is_translatable, validation_rules, field_order)
                                    VALUES (:extension_id, :table_name, :field_name, :field_type, :is_translatable, :validation_rules, :field_order)
                                """, {
                                    "extension_id": extension_db_id,
                                    "table_name": tbl_name,
                                    "field_name": field_name,
                                    "field_type": field_config.get("type", "text"),
                                    "is_translatable": field_config.get("multilingual", False),
                                    "validation_rules": json.dumps(field_config.get("validation", {})),
                                    "field_order": field_config.get("order", 0)
                                })
                            else:
                                raise field_error

                    pass
            else:
                print("Warning: Could not find extension record for table registration")

        except Exception as e:
            print(f"Warning: Failed to register table with extension registry: {e}")
            # Don't fail initialization for registration issues

        # Declare extension capabilities for dynamic inter-extension relationships
        declare_extension_capabilities("PagesExtension", {
            "provides": {
                "components": {
                    # PagesExtension doesn't provide components in this example
                },
                "apis": {
                    # PagesExtension APIs are for internal use
                }
            },
            "consumes": {
                "StoreExtension": {
                    "components": ["product_selector"],
                    "apis": ["get_products", "get_product", "get_categories", "get_cart", "add_to_cart"]
                }
            }
        })

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
                    pages = context.execute_query(f"""
                        SELECT id, title, slug, is_public, owner_id
                        FROM "{table_name}"
                        WHERE is_public = true
                        ORDER BY title
                    """)
                else:
                    # Authenticated: get user info
                    user_id = claims.get("sub") or claims.get("user_id")
                    user_role = claims.get("role", "")

                    if user_role == "admin":
                        # Admin sees all pages
                        pages = context.execute_query(f"""
                            SELECT id, title, slug, is_public, owner_id
                            FROM "{table_name}"
                            ORDER BY title
                        """)
                    else:
                        # Regular user: public pages + their own private pages
                        pages = context.execute_query(f"""
                            SELECT id, title, slug, is_public, owner_id
                            FROM "{table_name}"
                            WHERE is_public = true OR owner_id = :user_id
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
        async def create_page(
            request: Request,
            claims: dict = Depends(require_user)
        ):
            """Create a new page. Requires authentication."""
            user_id = claims.get("sub") or claims.get("user_id")
            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid token payload")

            # Dynamically extract form data based on schema (similar to frontend extension-relationships.ts)
            page_data = await page_form_handler.extract_form_data(request)

            # Generate slug if not provided
            slug = page_data.get("slug", "")
            if not slug:
                title = page_data.get("title", "")
                slug = title.lower().replace(" ", "-").replace("/", "-")

            # Insert page
            try:
                result = execute_main_db_query(f"""
                    INSERT INTO "{table_name}" (title, content, slug, is_public, allowed_roles, owner_id)
                    VALUES (:title, :content, :slug, :is_public, :allowed_roles, :owner_id)
                    RETURNING id
                """, {
                    "title": page_data.get("title"),
                    "content": page_data.get("content", ""),
                    "slug": slug,
                    "is_public": page_data.get("is_public", True),
                    "allowed_roles": json.dumps(page_data.get("allowed_roles", [])),
                    "owner_id": user_id
                })
                return {
                    "id": result[0]["id"] if result else None,
                    "title": page_data.get("title"),
                    "slug": slug,
                    "is_public": page_data.get("is_public", True)
                }
            except Exception as e:
                print(f"Error in create_page: {e}")
                raise

        @router.put("/{page_id}")
        async def update_page(
            page_id: int,
            request: Request,
            claims: dict = Depends(require_user)
        ):
            """Update a page dynamically based on schema. Requires authentication and ownership/admin permission."""
            user_id = claims.get("sub") or claims.get("user_id")
            user_role = claims.get("role", "")

            # Check if page exists and get owner
            page = context.execute_query(f"""
                SELECT owner_id FROM "{table_name}" WHERE id = :page_id
            """, {"page_id": page_id})

            if not page:
                raise HTTPException(status_code=404, detail="Page not found")

            # Check permission: owner or admin
            if str(page[0]["owner_id"]) != str(user_id) and user_role != "admin":
                raise HTTPException(status_code=403, detail="No permission to edit this page")

            # Dynamically extract form data based on schema (similar to frontend extension-relationships.ts)
            page_data = await page_form_handler.extract_form_data(request)
            print(f"DEBUG: Extracted page_data: {page_data}")

            # Generate slug if not provided but title is
            if "slug" not in page_data and "title" in page_data and page_data["title"]:
                page_data["slug"] = page_data["title"].lower().replace(" ", "-").replace("/", "-")

            # Update page dynamically
            update_fields = []
            update_values = {}

            for field_name, value in page_data.items():
                if field_name in page_form_handler.updatable_fields:
                    update_fields.append(f"{field_name} = :{field_name}")
                    # Handle special cases for JSON serialization
                    if field_name == "allowed_roles" and isinstance(value, (list, dict)):
                        update_values[field_name] = json.dumps(value)
                    else:
                        update_values[field_name] = value

            print(f"DEBUG: Update fields: {update_fields}")
            print(f"DEBUG: Update values: {update_values}")

            if update_fields:
                update_values["page_id"] = page_id
                result = execute_main_db_query(f"""
                    UPDATE "{table_name}"
                    SET {', '.join(update_fields)}
                    WHERE id = :page_id
                """, update_values)
                print(f"DEBUG: Update query executed, result: {result}")

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
            page = context.execute_query(f"""
                SELECT owner_id FROM "{table_name}" WHERE id = :page_id
            """, {"page_id": page_id})

            if not page:
                raise HTTPException(status_code=404, detail="Page not found")

            # Check permission: owner or admin
            if str(page[0]["owner_id"]) != str(user_id) and user_role != "admin":
                raise HTTPException(status_code=403, detail="No permission to delete this page")

            # Delete page
            execute_main_db_query(f'DELETE FROM "{table_name}" WHERE id = :page_id', {"page_id": page_id})

            return {"message": "Page deleted successfully"}

        @router.get("/{page_id}")
        def get_page(page_id: int, claims: dict = Depends(require_user)):
            """Get a single page by ID (for editing)"""
            user_id = claims.get("sub") or claims.get("user_id")
            user_role = claims.get("role", "")

            # Get page
            page = context.execute_query(f"""
                SELECT id, title, content, slug, is_public, allowed_roles, owner_id
                FROM "{table_name}"
                WHERE id = :page_id
            """, {"page_id": page_id})

            if not page:
                raise HTTPException(status_code=404, detail="Page not found")

            page_data = page[0]

            # Check permission: owner or admin
            if str(page_data["owner_id"]) != str(user_id) and user_role != "admin":
                raise HTTPException(status_code=403, detail="No permission to view this page")

            return {
                "id": page_data["id"],
                "title": page_data["title"],
                "content": page_data["content"],
                "slug": page_data["slug"],
                "is_public": bool(page_data["is_public"]),
                "allowed_roles": json.loads(page_data["allowed_roles"]) if page_data["allowed_roles"] else []
            }

        @router.get("/{slug}")
        def get_page_by_slug(slug: str, authorization: Optional[str] = Header(default=None)):
            try:
                # Find page by slug using named parameters
                page = context.execute_query(f"""
                    SELECT id, title, content, is_public, allowed_roles, owner_id
                    FROM "{table_name}"
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

        # Translation Management for Pages
        @router.post("/{page_id}/translations")
        async def add_page_translation(
            page_id: int,
            request: Request,
            claims: dict = Depends(require_user)
        ):
            """Add translations for a page"""
            try:
                # Parse form data
                form = await request.form()
                language_code = form.get("language_code")
                translations_raw = form.get("translations")

                # Parse translations JSON
                if translations_raw:
                    translations = json.loads(translations_raw)
                else:
                    translations = {}

                if not language_code:
                    raise HTTPException(status_code=400, detail="language_code is required")

                if not translations or not isinstance(translations, dict):
                    raise HTTPException(status_code=400, detail="translations must be a non-empty object")

                # Check if page exists and get owner
                page = context.execute_query(f"""
                    SELECT owner_id FROM "{table_name}" WHERE id = :page_id
                """, {"page_id": page_id})

                if not page:
                    raise HTTPException(status_code=404, detail="Page not found")

                # Check permission: owner or admin
                user_id = claims.get("sub") or claims.get("user_id")
                user_role = claims.get("role", "")
                if str(page[0]["owner_id"]) != str(user_id) and user_role != "admin":
                    raise HTTPException(status_code=403, detail="No permission to translate this page")

                # Insert or update translation
                translation_data = json.dumps(translations)

                # Try to access translations table, but handle if it doesn't exist yet
                try:
                    # Check if translation already exists
                    existing = context.execute_query(f"""
                        SELECT id FROM "{table_name}_translations"
                        WHERE record_id = :record_id
                        AND language_code = :language_code
                    """, {
                        "record_id": page_id,
                        "language_code": language_code
                    })

                    if existing:
                        # Update existing translation
                        context.execute_query(f"""
                            UPDATE "{table_name}_translations"
                            SET translation_data = :translation_data,
                                translation_coverage = :coverage,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE record_id = :record_id
                            AND language_code = :language_code
                        """, {
                            "translation_data": translation_data,
                            "coverage": len(translations) / 2 * 100,  # 2 translatable fields: title, content
                            "record_id": page_id,
                            "language_code": language_code
                        })
                    else:
                        # Insert new translation
                        context.execute_query(f"""
                            INSERT INTO "{table_name}_translations"
                            (record_id, language_code, translation_data, translation_coverage)
                            VALUES (:record_id, :language_code, :translation_data, :coverage)
                        """, {
                            "record_id": page_id,
                            "language_code": language_code,
                            "translation_data": translation_data,
                            "coverage": len(translations) / 2 * 100
                        })
                except Exception as table_error:
                    print(f"Translations table not accessible (this is normal if extension was just updated): {table_error}")
                    raise HTTPException(status_code=500, detail="Translations feature not available yet. Please restart the backend server.")

                return {"message": f"Translations added for {language_code}"}
            except Exception as e:
                print(f"Error adding page translations: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to add translations: {str(e)}")

        @router.get("/{page_id}/translations")
        def get_page_translations(page_id: int, claims: dict = Depends(require_user)):
            """Get all translations for a page"""
            try:
                # Check if page exists and get owner
                page = context.execute_query(f"""
                    SELECT owner_id FROM "{table_name}" WHERE id = :page_id
                """, {"page_id": page_id})

                if not page:
                    raise HTTPException(status_code=404, detail="Page not found")

                # Check permission: owner or admin
                user_id = claims.get("sub") or claims.get("user_id")
                user_role = claims.get("role", "")
                if str(page[0]["owner_id"]) != str(user_id) and user_role != "admin":
                    raise HTTPException(status_code=403, detail="No permission to view translations")

                # Try to get translations, but don't fail if table doesn't exist
                try:
                    translations = context.execute_query(f"""
                        SELECT language_code, translation_data, translation_coverage
                        FROM "{table_name}_translations"
                        WHERE record_id = :record_id
                    """, {
                        "record_id": page_id
                    })
                except Exception as table_error:
                    print(f"Translations table not accessible (this is normal if extension was just updated): {table_error}")
                    translations = []

                return {
                    "page_id": page_id,
                    "translations": [{
                        "language_code": row["language_code"],
                        "data": json.loads(row["translation_data"]) if isinstance(row["translation_data"], str) else row["translation_data"],
                        "coverage": float(row["translation_coverage"]) if row["translation_coverage"] else 0
                    } for row in translations or []]
                }
            except HTTPException:
                raise
            except Exception as e:
                print(f"Error getting page translations: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get translations: {str(e)}")

        @router.delete("/{page_id}/translations/{language_code}")
        def delete_page_translation(
            page_id: int,
            language_code: str,
            claims: dict = Depends(require_user)
        ):
            """Delete translations for a specific language"""
            try:
                # Check if page exists and get owner
                page = context.execute_query(f"""
                    SELECT owner_id FROM "{table_name}" WHERE id = :page_id
                """, {"page_id": page_id})

                if not page:
                    raise HTTPException(status_code=404, detail="Page not found")

                # Check permission: owner or admin
                user_id = claims.get("sub") or claims.get("user_id")
                user_role = claims.get("role", "")
                if str(page[0]["owner_id"]) != str(user_id) and user_role != "admin":
                    raise HTTPException(status_code=403, detail="No permission to delete translations")

                execute_main_db_query(f"""
                    DELETE FROM "{table_name}_translations"
                    WHERE record_id = :record_id
                    AND language_code = :language_code
                """, {
                    "record_id": page_id,
                    "language_code": language_code
                })

                return {"message": f"Translations deleted for {language_code}"}
            except Exception as e:
                print(f"Error deleting page translations: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to delete translations: {str(e)}")

        # Enhanced page retrieval with translations
        @router.get("/by-slug/{slug}")
        def get_page_by_slug_with_translations(
            slug: str,
            language: Optional[str] = None,
            authorization: Optional[str] = Header(default=None)
        ):
            """Get page by slug with automatic translation merging"""
            try:
                current_language = language or "en"

                # Find page by slug
                page = context.execute_query(f"""
                    SELECT id, title, content, is_public, allowed_roles, owner_id
                    FROM "{table_name}"
                    WHERE slug = :slug
                """, {"slug": slug})

                if not page:
                    raise HTTPException(status_code=404, detail="Page not found")

                page_data = page[0]
                title, content, is_public, allowed_roles, owner_id = page_data["title"], page_data["content"], page_data["is_public"], page_data["allowed_roles"], page_data["owner_id"]

                # Public page: allow anyone
                if is_public:
                    # Apply translations if needed
                    if current_language != "en":
                        try:
                            translation = execute_main_db_query(f"""
                                SELECT translation_data FROM "{table_name}_translations"
                                WHERE record_id = :record_id
                                AND language_code = :language_code
                            """, {
                                "record_id": page_data["id"],
                                "language_code": current_language
                            })

                            if translation and translation[0]["translation_data"]:
                                translation_raw = translation[0]["translation_data"]
                                # SQLAlchemy may have already parsed JSONB as dict
                                if isinstance(translation_raw, dict):
                                    translation_data = translation_raw
                                else:
                                    translation_data = json.loads(translation_raw)
                                # Merge translation with base content
                                title = translation_data.get("title", title)
                                content = translation_data.get("content", content)
                        except Exception as translation_error:
                            print(f"Translations not available for page {page_data['id']} in {current_language}: {translation_error}")
                            # Continue without translations

                    return {"title": title, "content": content, "language": current_language}

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
                    # Apply translations if needed
                    if current_language != "en":
                        try:
                            translation = execute_main_db_query(f"""
                                SELECT translation_data FROM "{table_name}_translations"
                                WHERE record_id = :record_id
                                AND language_code = :language_code
                            """, {
                                "record_id": page_data["id"],
                                "language_code": current_language
                            })

                            if translation and translation[0]["translation_data"]:
                                translation_raw = translation[0]["translation_data"]
                                # SQLAlchemy may have already parsed JSONB as dict
                                if isinstance(translation_raw, dict):
                                    translation_data = translation_raw
                                else:
                                    translation_data = json.loads(translation_raw)
                                # Merge translation with base content
                                title = translation_data.get("title", title)
                                content = translation_data.get("content", content)
                        except Exception as translation_error:
                            print(f"Translations not available for page {page_data['id']} in {current_language}: {translation_error}")
                            # Continue without translations

                    return {"title": title, "content": content, "language": current_language}

                # Check role-based access
                if allowed_roles:
                    try:
                        allowed = json.loads(allowed_roles)
                        if isinstance(allowed, list) and allowed:
                            user_role = claims.get("role")
                            if user_role and user_role in allowed:
                                # Apply translations if needed
                                if current_language != "en":
                                    try:
                                        translation = execute_main_db_query(f"""
                                            SELECT translation_data FROM "{table_name}_translations"
                                            WHERE record_id = :record_id
                                            AND language_code = :language_code
                                        """, {
                                            "record_id": page_data["id"],
                                            "language_code": current_language
                                        })

                                        if translation and translation[0]["translation_data"]:
                                            translation_raw = translation[0]["translation_data"]
                                            # SQLAlchemy may have already parsed JSONB as dict
                                            if isinstance(translation_raw, dict):
                                                translation_data = translation_raw
                                            else:
                                                translation_data = json.loads(translation_raw)
                                            # Merge translation with base content
                                            title = translation_data.get("title", title)
                                            content = translation_data.get("content", content)
                                    except Exception as translation_error:
                                        print(f"Translations not available for page {page_data['id']} in {current_language}: {translation_error}")
                                        # Continue without translations

                                return {"title": title, "content": content, "language": current_language}
                    except Exception as e:
                        pass

                raise HTTPException(status_code=403, detail="Access denied")
            except Exception as e:
                print(f"Error in get_page_by_slug_with_translations: {e}")
                import traceback
                traceback.print_exc()
                raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

        # Image Upload Endpoint
        @router.post("/upload-image")
        def upload_page_image(
            file: UploadFile = File(...),
            directory: str = "pages",
            replace_filename: str = None,
            claims: dict = Depends(require_user)
        ):
            """Upload page image"""
            try:
                # Validate file type
                allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
                if file.content_type not in allowed_types:
                    raise HTTPException(status_code=400, detail="Invalid file type. Only JPEG, PNG, GIF, and WebP are allowed.")

                # Validate file size (max 5MB)
                file.file.seek(0, 2)
                file_size = file.file.tell()
                file.file.seek(0)
                if file_size > 5 * 1024 * 1024:
                    raise HTTPException(status_code=400, detail="File too large. Maximum size is 5MB.")

                # Generate filename
                import uuid
                import os
                from datetime import datetime

                if replace_filename:
                    # Use the existing filename when replacing
                    filename = replace_filename
                else:
                    # Generate unique filename for new uploads
                    file_extension = os.path.splitext(file.filename)[1]
                    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex}{file_extension}"

                # Create uploads directory if it doesn't exist
                uploads_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'uploads', directory)
                os.makedirs(uploads_dir, exist_ok=True)

                # Save the file
                file_path = os.path.join(uploads_dir, filename)
                with open(file_path, "wb") as buffer:
                    buffer.write(file.file.read())

                return {
                    "filename": filename,
                    "url": f"/uploads/{directory}/{filename}",
                    "message": "Image uploaded successfully"
                }

            except Exception as e:
                print(f"Error uploading image: {e}")
                raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

        # Images List Endpoint
        @router.get("/images/list")
        def list_page_images(directory: str = "pages", search: Optional[str] = None, limit: int = 100, offset: int = 0):
            """List images in the pages uploads directory"""
            try:
                import os
                from datetime import datetime

                # Base uploads directory
                base_uploads_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'uploads')

                # Target directory (default to 'pages')
                target_dir = os.path.join(base_uploads_dir, directory)

                # Ensure directory exists
                if not os.path.exists(target_dir):
                    os.makedirs(target_dir, exist_ok=True)

                # Get all items (files and directories)
                image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.svg'}
                all_items = []

                try:
                    items = os.listdir(target_dir)
                except PermissionError:
                    return {"images": [], "folders": [], "total": 0, "directory": directory}

                for item_name in items:
                    item_path = os.path.join(target_dir, item_name)

                    try:
                        # Check if it's a directory
                        if os.path.isdir(item_path):
                            # Get directory stats
                            stat = os.stat(item_path)
                            modified_time = datetime.fromtimestamp(stat.st_mtime)

                            # Count images in this folder
                            image_count = 0
                            try:
                                for sub_item in os.listdir(item_path):
                                    sub_path = os.path.join(item_path, sub_item)
                                    if os.path.isfile(sub_path):
                                        _, ext = os.path.splitext(sub_item.lower())
                                        if ext in image_extensions:
                                            image_count += 1
                            except PermissionError:
                                image_count = 0

                            folder_obj = {
                                "name": item_name,
                                "path": f"{directory}/{item_name}".lstrip("/"),
                                "type": "folder",
                                "image_count": image_count,
                                "modified": modified_time.isoformat(),
                                "directory": directory
                            }
                            all_items.append(folder_obj)

                        # Check if it's an image file
                        elif os.path.isfile(item_path):
                            _, ext = os.path.splitext(item_name.lower())
                            if ext in image_extensions:
                                # Get file stats
                                stat = os.stat(item_path)
                                file_size = stat.st_size
                                modified_time = datetime.fromtimestamp(stat.st_mtime)

                                # Create image object
                                image_obj = {
                                    "url": f"/uploads/{directory}/{item_name}",
                                    "name": item_name,
                                    "size": file_size,
                                    "type": "image",
                                    "modified": modified_time.isoformat(),
                                    "directory": directory
                                }
                                all_items.append(image_obj)

                    except Exception as e:
                        print(f"Error processing item {item_name}: {e}")
                        continue

                # Separate folders and images
                folders = [item for item in all_items if item["type"] == "folder"]
                images = [item for item in all_items if item["type"] == "image"]

                # Sort folders alphabetically
                folders.sort(key=lambda x: x["name"].lower())

                # Sort images by modification time (newest first)
                images.sort(key=lambda x: x["modified"], reverse=True)

                # Apply search filter if provided
                if search:
                    search_lower = search.lower()
                    filtered_folders = [
                        folder for folder in folders
                        if search_lower in folder["name"].lower()
                    ]
                    filtered_images = [
                        img for img in images
                        if search_lower in img["name"].lower() or search_lower in img["url"].lower()
                    ]
                else:
                    filtered_folders = folders
                    filtered_images = images

                # Apply pagination to images only (folders are always shown)
                total_images = len(filtered_images)
                paginated_images = filtered_images[offset:offset + limit]

                # Build breadcrumb path
                path_parts = directory.split("/") if directory != "pages" else []
                breadcrumb = []
                current_path = "pages"
                breadcrumb.append({"name": "Pages", "path": "pages"})

                for part in path_parts:
                    if part and part != "pages":
                        current_path = f"{current_path}/{part}"
                        breadcrumb.append({"name": part, "path": current_path})

                return {
                    "folders": filtered_folders,
                    "images": paginated_images,
                    "total": total_images,
                    "limit": limit,
                    "offset": offset,
                    "directory": directory,
                    "breadcrumb": breadcrumb,
                    "can_create_folder": True
                }

            except Exception as e:
                print(f"Error listing page images: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to list images: {str(e)}")

        # Create Folder Endpoint
        @router.post("/images/folder")
        def create_page_image_folder(data: dict, claims: dict = Depends(require_user)):
            """Create a new folder in the pages uploads directory"""
            try:
                import os

                folder_name = data.get("folder_name")
                directory = data.get("directory", "pages")

                # Validate folder name
                if not folder_name or not folder_name.strip():
                    raise HTTPException(status_code=400, detail="Folder name is required")

                # Sanitize folder name
                safe_name = "".join(c for c in folder_name.strip() if c.isalnum() or c in (' ', '-', '_')).rstrip()
                if not safe_name:
                    raise HTTPException(status_code=400, detail="Invalid folder name")

                # Base uploads directory
                base_uploads_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'uploads')

                # Target directory
                target_dir = os.path.join(base_uploads_dir, directory)

                # Create the new folder
                new_folder_path = os.path.join(target_dir, safe_name)

                # Check if folder already exists
                if os.path.exists(new_folder_path):
                    raise HTTPException(status_code=400, detail="Folder already exists")

                os.makedirs(new_folder_path, exist_ok=True)

                return {
                    "message": "Folder created successfully",
                    "folder": {
                        "name": safe_name,
                        "path": f"{directory}/{safe_name}".lstrip("/"),
                        "type": "folder",
                        "image_count": 0,
                        "directory": directory
                    }
                }

            except HTTPException:
                raise
            except Exception as e:
                print(f"Error creating folder: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to create folder: {str(e)}")

        # Dynamic Extension Integration Endpoint
        @router.post("/extension-integration/{target_extension}/{api_name}")
        def call_extension_api_via_pages(
            target_extension: str,
            api_name: str,
            request_data: dict = None,
            claims: dict = Depends(require_user)
        ):
            """Dynamically call any extension API via PagesExtension (demonstrates inter-extension communication)"""
            try:
                # Validate that the target extension is available and provides the requested API
                from backend.utils.extension_relationships import extension_capabilities

                if target_extension not in extension_capabilities:
                    raise HTTPException(status_code=404, detail=f"Extension '{target_extension}' not found")

                capabilities = extension_capabilities[target_extension]
                if 'provides' not in capabilities or 'apis' not in capabilities['provides']:
                    raise HTTPException(status_code=400, detail=f"Extension '{target_extension}' does not provide APIs")

                if api_name not in capabilities['provides']['apis']:
                    raise HTTPException(status_code=400, detail=f"Extension '{target_extension}' does not provide API '{api_name}'")

                # Extract parameters from request_data
                kwargs = request_data or {}

                # Call the extension API dynamically
                result = call_api_endpoint(target_extension, api_name, **kwargs)

                # Add integration metadata
                result["integration_info"] = {
                    "source": "PagesExtension",
                    "target": target_extension,
                    "api_called": api_name,
                    "timestamp": "2025-12-10",
                    "user_id": claims.get("user_id")
                }

                return result

            except HTTPException:
                raise
            except Exception as e:
                print(f"Error calling {target_extension}.{api_name} API: {e}")
                raise HTTPException(status_code=500, detail=f"Extension integration failed: {str(e)}")

        # Get Available Extension Capabilities
        @router.get("/extension-capabilities")
        def get_extension_capabilities():
            """Get capabilities of all available extensions (for dynamic integration)"""
            try:
                from backend.utils.extension_relationships import extension_capabilities

                # Return capabilities without sensitive information
                public_capabilities = {}
                for ext_name, capabilities in extension_capabilities.items():
                    public_capabilities[ext_name] = {
                        "provides": capabilities.get("provides", {}),
                        # Don't expose "consumes" as it might contain sensitive dependency info
                    }

                return {
                    "extensions": public_capabilities,
                    "integration_info": {
                        "source": "PagesExtension",
                        "endpoint": "/api/pages/extension-capabilities",
                        "description": "Dynamic extension integration capabilities"
                    }
                }

            except Exception as e:
                print(f"Error getting extension capabilities: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get capabilities: {str(e)}")

        context.register_router(router)

        return {
            "routes_registered": 15,  # Original 5 + 4 translation routes + 1 get page route + 3 image routes + 2 dynamic integration routes
            "tables_created": 2,  # Main table + translations table
            "indexes_created": 3,  # Indexes created by manual code
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