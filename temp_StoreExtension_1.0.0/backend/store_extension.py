"""
Store Extension Backend Module
Provides full e-commerce functionality with products, orders, cart, and payments.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form
from backend.utils.auth_dep import require_user
from backend.database import get_db
from backend.utils.universal_translation_engine import UniversalTranslationEngine
from backend.utils.extension_dependencies import get_extension_dependency_manager
from backend.utils.extension_relationships import declare_extension_capabilities, register_extension_resources
from sqlalchemy import text
from typing import List, Optional, Dict, Any
import json
from datetime import datetime

def execute_main_db_query(query: str, params: dict = None):
    """Execute query using main database session with proper commits"""
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

def initialize_extension(context):
    """Initialize the store extension"""
    try:
        # Get the extension database ID from name/version
        extension_name, extension_version = context.extension_id.rsplit('_', 1)
        extension_result = execute_main_db_query("""
            SELECT id FROM extensions
            WHERE name = :name AND version = :version
        """, {"name": extension_name, "version": extension_version})

        if not extension_result:
            return {"status": "error", "error": "Extension not found in database"}

        extension_db_id = extension_result[0]["id"]

        # Table names (lowercase to match PostgreSQL folding)
        products_table = "ext_storeextension_products"
        categories_table = "ext_storeextension_categories"
        orders_table = "ext_storeextension_orders"
        order_items_table = "ext_storeextension_order_items"
        customers_table = "ext_storeextension_customers"
        cart_table = "ext_storeextension_cart"
        reviews_table = "ext_storeextension_reviews"
        translations_table = "ext_storeextension_translations"
        settings_table = "ext_storeextension_settings"

        # Ensure tables exist with proper schema
        try:
            # Check and create products table
            result = execute_main_db_query(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = '{products_table}'
                )
            """)
            if not result or not result[0]['exists']:
                execute_main_db_query(f"""
                    CREATE TABLE "{products_table}" (
                        id SERIAL PRIMARY KEY,
                        sku TEXT,
                        name TEXT NOT NULL,
                        description TEXT,
                        short_description TEXT,
                        price TEXT NOT NULL,
                        sale_price TEXT,
                        stock_quantity INTEGER DEFAULT 0,
                        images TEXT DEFAULT '[]',
                        categories TEXT DEFAULT '[]',
                        is_active BOOLEAN DEFAULT true,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            # Check and create categories table
            result = execute_main_db_query(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = '{categories_table}'
                )
            """)
            if not result or not result[0]['exists']:
                execute_main_db_query(f"""
                    CREATE TABLE "{categories_table}" (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        slug TEXT UNIQUE,
                        description TEXT,
                        sort_order INTEGER DEFAULT 0,
                        is_active BOOLEAN DEFAULT true
                    )
                """)
            # Check and create cart table
            result = execute_main_db_query(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = '{cart_table}'
                )
            """)
            if not result or not result[0]['exists']:
                execute_main_db_query(f"""
                    CREATE TABLE "{cart_table}" (
                        id SERIAL PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        items TEXT DEFAULT '[]',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            # Check and create orders table
            result = execute_main_db_query(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = '{orders_table}'
                )
            """)
            if not result or not result[0]['exists']:
                execute_main_db_query(f"""
                    CREATE TABLE "{orders_table}" (
                        id SERIAL PRIMARY KEY,
                        order_number TEXT NOT NULL UNIQUE,
                        customer_id INTEGER,
                        status TEXT DEFAULT 'pending',
                        subtotal TEXT NOT NULL,
                        tax_amount TEXT DEFAULT '0',
                        shipping_amount TEXT DEFAULT '0',
                        total_amount TEXT NOT NULL,
                        billing_address TEXT,
                        shipping_address TEXT,
                        payment_method TEXT,
                        shipping_method TEXT DEFAULT 'standard',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            # Check and create order_items table
            result = execute_main_db_query(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = '{order_items_table}'
                )
            """)
            if not result or not result[0]['exists']:
                execute_main_db_query(f"""
                    CREATE TABLE "{order_items_table}" (
                        id SERIAL PRIMARY KEY,
                        order_id INTEGER NOT NULL,
                        product_id INTEGER NOT NULL,
                        product_name TEXT NOT NULL,
                        product_sku TEXT,
                        quantity INTEGER NOT NULL,
                        unit_price TEXT NOT NULL,
                        total_price TEXT NOT NULL,
                        variant_data TEXT DEFAULT '{{}}'
                    )
                """)
            # Check and create customers table
            result = execute_main_db_query(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = '{customers_table}'
                )
            """)
            if not result or not result[0]['exists']:
                execute_main_db_query(f"""
                    CREATE TABLE "{customers_table}" (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER,
                        email TEXT NOT NULL,
                        first_name TEXT,
                        last_name TEXT,
                        phone TEXT,
                        billing_address TEXT,
                        shipping_address TEXT,
                        is_active BOOLEAN DEFAULT true,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            # Check and create reviews table
            result = execute_main_db_query(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = '{reviews_table}'
                )
            """)
            if not result or not result[0]['exists']:
                execute_main_db_query(f"""
                    CREATE TABLE "{reviews_table}" (
                        id SERIAL PRIMARY KEY,
                        product_id INTEGER NOT NULL,
                        customer_name TEXT NOT NULL,
                        customer_email TEXT,
                        rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                        title TEXT,
                        comment TEXT,
                        is_approved BOOLEAN DEFAULT false,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

            # Check and create translations table
            result = execute_main_db_query(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = '{translations_table}'
                )
            """)
            if not result or not result[0]['exists']:
                execute_main_db_query(f"""
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

            # Check and create ext_storeextension_settings table (extension-specific settings table)
            result = execute_main_db_query(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = '{settings_table}'
                )
            """)

            if not result or not result[0]['exists']:
                execute_main_db_query(f"""
                    CREATE TABLE "{settings_table}" (
                        id SERIAL PRIMARY KEY,
                        extension_id INTEGER NOT NULL UNIQUE,
                        settings_data JSONB NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Migrate existing settings from global table if they exist
                try:
                    existing_settings = execute_main_db_query("""
                        SELECT settings_data FROM extension_settings
                        WHERE extension_id = :extension_id
                    """, {"extension_id": extension_db_id})

                    if existing_settings:
                        execute_main_db_query(f"""
                            INSERT INTO "{settings_table}" (extension_id, settings_data)
                            VALUES (:extension_id, :settings_data)
                        """, {
                            "extension_id": extension_db_id,
                            "settings_data": existing_settings[0]["settings_data"]
                        })
                except Exception as e:
                    print(f"Warning: Could not migrate existing settings: {e}")

        except Exception as e:
            print(f"Error creating StoreExtension tables: {e}")
            import traceback
            traceback.print_exc()

        # Register tables with the extension registry for proper uninstall support
        try:
            # Define table schemas for registration
            table_schemas = {
                products_table: {
                    "id": {"type": "integer", "primary_key": True},
                    "sku": {"type": "text"},
                    "name": {"type": "text", "multilingual": True},
                    "description": {"type": "text", "multilingual": True},
                    "short_description": {"type": "text", "multilingual": True},
                    "price": {"type": "text"},
                    "sale_price": {"type": "text"},
                    "stock_quantity": {"type": "integer"},
                    "images": {"type": "text"},
                    "categories": {"type": "text"},
                    "is_active": {"type": "boolean"},
                    "created_at": {"type": "timestamp"}
                },
                categories_table: {
                    "id": {"type": "integer", "primary_key": True},
                    "name": {"type": "text", "multilingual": True},
                    "slug": {"type": "text"},
                    "description": {"type": "text", "multilingual": True},
                    "sort_order": {"type": "integer"},
                    "is_active": {"type": "boolean"}
                },
                orders_table: {
                    "id": {"type": "integer", "primary_key": True},
                    "order_number": {"type": "text"},
                    "customer_id": {"type": "integer"},
                    "status": {"type": "text"},
                    "subtotal": {"type": "text"},
                    "tax_amount": {"type": "text"},
                    "shipping_amount": {"type": "text"},
                    "total_amount": {"type": "text"},
                    "billing_address": {"type": "text"},
                    "shipping_address": {"type": "text"},
                    "payment_method": {"type": "text"},
                    "shipping_method": {"type": "text"},
                    "created_at": {"type": "timestamp"},
                    "updated_at": {"type": "timestamp"}
                },
                order_items_table: {
                    "id": {"type": "integer", "primary_key": True},
                    "order_id": {"type": "integer"},
                    "product_id": {"type": "integer"},
                    "product_name": {"type": "text"},
                    "product_sku": {"type": "text"},
                    "quantity": {"type": "integer"},
                    "unit_price": {"type": "text"},
                    "total_price": {"type": "text"},
                    "variant_data": {"type": "text"}
                },
                customers_table: {
                    "id": {"type": "integer", "primary_key": True},
                    "user_id": {"type": "integer"},
                    "email": {"type": "text"},
                    "first_name": {"type": "text"},
                    "last_name": {"type": "text"},
                    "phone": {"type": "text"},
                    "billing_address": {"type": "text"},
                    "shipping_address": {"type": "text"},
                    "is_active": {"type": "boolean"},
                    "created_at": {"type": "timestamp"}
                },
                cart_table: {
                    "id": {"type": "integer", "primary_key": True},
                    "session_id": {"type": "text"},
                    "user_id": {"type": "integer"},
                    "items": {"type": "text"},
                    "created_at": {"type": "timestamp"},
                    "updated_at": {"type": "timestamp"}
                },
                reviews_table: {
                    "id": {"type": "integer", "primary_key": True},
                    "product_id": {"type": "integer"},
                    "customer_name": {"type": "text"},
                    "customer_email": {"type": "text"},
                    "rating": {"type": "integer"},
                    "title": {"type": "text"},
                    "comment": {"type": "text"},
                    "is_approved": {"type": "boolean"},
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
                },
                settings_table: {
                    "id": {"type": "integer", "primary_key": True},
                    "extension_id": {"type": "integer"},
                    "settings_data": {"type": "jsonb"},
                    "created_at": {"type": "timestamp"},
                    "updated_at": {"type": "timestamp"}
                }
            }

            # Register each table synchronously using direct SQL
            for table_name, schema in table_schemas.items():
                translatable_fields = [field for field, config in schema.items() if config.get("multilingual", False)]


                try:
                    # Insert into extension_tables
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
                        "table_name": table_name,
                        "table_schema": json.dumps(schema),
                        "translatable_fields": json.dumps(translatable_fields),
                        "primary_key": "id",
                        "is_multilingual": len(translatable_fields) > 0
                    })
                except Exception as insert_error:
                    if "ON CONFLICT" in str(insert_error):
                        # Try INSERT without ON CONFLICT first
                        execute_main_db_query("""
                            INSERT INTO extension_tables
                            (extension_id, table_name, table_schema, translatable_fields, primary_key_field, is_multilingual)
                            VALUES (:extension_id, :table_name, :table_schema, :translatable_fields, :primary_key, :is_multilingual)
                        """, {
                            "extension_id": extension_db_id,
                            "table_name": table_name,
                            "table_schema": json.dumps(schema),
                            "translatable_fields": json.dumps(translatable_fields),
                            "primary_key": "id",
                            "is_multilingual": len(translatable_fields) > 0
                        })
                    else:
                        raise insert_error

                    # Register individual fields
                    for field_name, field_config in schema.items():
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
                            "table_name": table_name,
                            "field_name": field_name,
                            "field_type": field_config.get("type", "text"),
                            "is_translatable": field_config.get("multilingual", False),
                            "validation_rules": json.dumps(field_config.get("validation", {})),
                            "field_order": field_config.get("order", 0)
                        })

                    print(f"✅ Registered table {table_name} for extension {extension_db_id}")
                except Exception as e:
                    print(f"❌ Failed to register table {table_name}: {e}")

        except Exception as e:
            print(f"Warning: Failed to register tables with extension registry: {e}")
            # Don't fail initialization for registration issues

        router = APIRouter(prefix="/api/store")

        # Product Management
        @router.get("/products")
        def get_products(
            category: Optional[str] = None,
            search: Optional[str] = None,
            limit: int = 20,
            offset: int = 0,
            language: Optional[str] = None
        ):
            """Get products with filtering and translations"""
            try:
                # Get current language from request or default to 'en'
                current_language = language or "en"

                query = f'SELECT * FROM "{products_table}" WHERE is_active = true'
                params = {}

                if category:
                    # First get all categories to debug
                    all_categories = execute_main_db_query(f"""
                        SELECT id, name, slug FROM "{categories_table}" WHERE is_active = true
                    """)

                    # Then get the specific category ID from the slug
                    category_result = execute_main_db_query(f"""
                        SELECT id FROM "{categories_table}" WHERE slug = :slug AND is_active = true
                    """, {"slug": category})

                    if category_result:
                        category_id = category_result[0]["id"]  # Keep as integer for JSON query

                        # Cast category_id to string for JSON ? operator (expects text)
                        category_id_str = str(category_id)

                        # Debug: Check which products have this category
                        products_with_category = execute_main_db_query(f"""
                            SELECT id, name, categories FROM "{products_table}"
                            WHERE is_active = true AND categories::jsonb @> :category_id_json
                        """, {"category_id_json": json.dumps([str(category_id)])})

                        # Also check what categories data looks like for all products
                        all_products_categories = execute_main_db_query(f"""
                            SELECT id, name, categories FROM {products_table}
                            WHERE is_active = true
                        """)

                        # Use PostgreSQL JSON @> operator to check if categories array contains the category ID
                        # Categories are stored as string arrays, so we need to search for the string version
                        query += " AND categories::jsonb @> :category_id_json"
                        params["category_id_json"] = json.dumps([str(category_id)])  # Pass as JSON array containing the string
                    else:
                        # Category not found, return no results
                        query += " AND 1 = 0"

                if search:
                    query += " AND (name ILIKE :search OR description ILIKE :search)"
                    params["search"] = f"%{search}%"

                query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
                params.update({"limit": limit, "offset": offset})

                base_products = execute_main_db_query(query, params)

                # Apply translations synchronously if needed
                if current_language != "en" and base_products:
                    translated_products = []
                    for product in base_products:
                        # Try to get translation from extension-specific translations table
                        translation_query = f"""
                            SELECT translation_data FROM "{translations_table}"
                            WHERE record_id = :record_id
                            AND language_code = :language_code
                        """
                        translation_result = execute_main_db_query(translation_query, {
                            "record_id": product["id"],
                            "language_code": current_language
                        })

                        if translation_result and translation_result[0]["translation_data"]:
                            try:
                                # SQLAlchemy automatically parses JSONB fields, so check if it's already a dict
                                translation_raw = translation_result[0]["translation_data"]
                                if isinstance(translation_raw, dict):
                                    translation_data = translation_raw
                                else:
                                    translation_data = json.loads(translation_raw)
                                # Merge translation with base product
                                translated_product = product.copy()
                                translated_product.update(translation_data)
                                translated_products.append(translated_product)
                            except Exception as e:
                                print(f"Error parsing product translation: {e}")
                                translated_products.append(product)  # Fallback to original
                        else:
                            translated_products.append(product)  # No translation available

                    # Process categories and images for translated products
                    for product in translated_products:
                        if product.get("categories"):
                            try:
                                product["categories"] = json.loads(product["categories"]) if isinstance(product["categories"], str) else product["categories"]
                            except Exception as e:
                                print(f"Error parsing categories for product {product.get('id')}: {e}")
                                product["categories"] = []
                        else:
                            product["categories"] = []

                        if product.get("images"):
                            try:
                                product["images"] = json.loads(product["images"]) if isinstance(product["images"], str) else product["images"]
                            except Exception as e:
                                print(f"Error parsing images for product {product.get('id')}: {e}")
                                product["images"] = []
                        else:
                            product["images"] = []

                    return {"items": translated_products, "total": len(translated_products)}
                else:
                    # Process categories and images for base products
                    for product in base_products:
                        if product.get("categories"):
                            try:
                                product["categories"] = json.loads(product["categories"]) if isinstance(product["categories"], str) else product["categories"]
                            except Exception as e:
                                print(f"Error parsing categories for product {product.get('id')}: {e}")
                                product["categories"] = []
                        else:
                            product["categories"] = []

                        if product.get("images"):
                            try:
                                product["images"] = json.loads(product["images"]) if isinstance(product["images"], str) else product["images"]
                            except Exception as e:
                                print(f"Error parsing images for product {product.get('id')}: {e}")
                                product["images"] = []
                        else:
                            product["images"] = []

                    return {"items": base_products or [], "total": len(base_products or [])}
            except Exception as e:
                print(f"ERROR in get_products: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to fetch products: {str(e)}")

        @router.get("/products/{product_id}")
        def get_product(product_id: int, language: Optional[str] = None):
            """Get single product with translations"""
            current_language = language or "en"

            base_result = execute_main_db_query(
                f'SELECT * FROM "{products_table}" WHERE id = :id AND is_active = true',
                {"id": product_id}
            )
            if not base_result:
                raise HTTPException(status_code=404, detail="Product not found")

            product = base_result[0]

            # Parse categories and images from JSON string to array
            if product.get("categories"):
                try:
                    product["categories"] = json.loads(product["categories"]) if isinstance(product["categories"], str) else product["categories"]
                except Exception as e:
                    print(f"Error parsing categories: {e}")
                    product["categories"] = []
            else:
                product["categories"] = []

            if product.get("images"):
                try:
                    product["images"] = json.loads(product["images"]) if isinstance(product["images"], str) else product["images"]
                except Exception as e:
                    print(f"Error parsing images: {e}")
                    product["images"] = []
            else:
                product["images"] = []

            # Apply translations if needed
            if current_language != "en":
                translation_query = f"""
                    SELECT translation_data FROM "{translations_table}"
                    WHERE record_id = :record_id
                    AND language_code = :language_code
                """
                translation_result = execute_main_db_query(translation_query, {
                    "record_id": product_id,
                    "language_code": current_language
                })

                if translation_result and translation_result[0]["translation_data"]:
                    try:
                        # SQLAlchemy automatically parses JSONB fields, so check if it's already a dict
                        translation_raw = translation_result[0]["translation_data"]
                        if isinstance(translation_raw, dict):
                            translation_data = translation_raw
                        else:
                            translation_data = json.loads(translation_raw)
                        # Merge translation with base product, but exclude images since they are not translatable
                        product = product.copy()
                        for key, value in translation_data.items():
                            if key != 'images':  # Don't overwrite images with translation data
                                product[key] = value
                    except Exception as e:
                        print(f"Error parsing translation data: {e}")

            return product

        @router.put("/products/{product_id}")
        def update_product(product_id: int, product: dict, claims: dict = Depends(require_user)):
            """Update product"""
            update_fields = []
            params = {"product_id": product_id}

            if "name" in product:
                update_fields.append("name = :name")
                params["name"] = product["name"]
            if "description" in product:
                update_fields.append("description = :description")
                params["description"] = product["description"]
            if "short_description" in product:
                update_fields.append("short_description = :short_description")
                params["short_description"] = product["short_description"]
            if "price" in product:
                update_fields.append("price = :price")
                params["price"] = product["price"]
            if "sale_price" in product:
                update_fields.append("sale_price = :sale_price")
                params["sale_price"] = product["sale_price"]
            if "stock_quantity" in product:
                update_fields.append("stock_quantity = :stock_quantity")
                params["stock_quantity"] = product["stock_quantity"]
            if "categories" in product:
                update_fields.append("categories = :categories")
                # Ensure categories are stored as strings for PostgreSQL JSON ? operator
                categories = [str(cat_id) for cat_id in product["categories"]]
                params["categories"] = json.dumps(categories)
            if "images" in product:
                update_fields.append("images = :images")
                params["images"] = json.dumps(product["images"])

            if update_fields:
                execute_main_db_query(f"""
                    UPDATE "{products_table}"
                    SET {', '.join(update_fields)}
                    WHERE id = :product_id
                """, params)

            return {"message": "Product updated successfully"}

        @router.delete("/products/{product_id}")
        def delete_product(product_id: int, claims: dict = Depends(require_user)):
            """Delete product (soft delete by setting inactive)"""
            execute_main_db_query(
                f'UPDATE "{products_table}" SET is_active = false WHERE id = :id',
                {"id": product_id}
            )
            return {"message": "Product deleted successfully"}

        @router.post("/products")
        def create_product(product: dict, claims: dict = Depends(require_user)):
            """Create new product"""
            # Validate required fields
            if not product.get("name") or not product.get("price"):
                raise HTTPException(status_code=400, detail="Name and price are required")

            # Ensure categories are stored as strings for PostgreSQL JSON ? operator
            categories = [str(cat_id) for cat_id in product.get("categories", [])]

            result = execute_main_db_query(f"""
                INSERT INTO "{products_table}"
                (sku, name, description, short_description, price, sale_price, stock_quantity, categories, images)
                VALUES (:sku, :name, :description, :short_description, :price, :sale_price, :stock_quantity, :categories, :images)
                RETURNING id
            """, {
                "sku": product.get("sku", ""),
                "name": product["name"],
                "description": product.get("description", ""),
                "short_description": product.get("short_description", ""),
                "price": product["price"],
                "sale_price": product.get("sale_price"),
                "stock_quantity": product.get("stock_quantity", 0),
                "categories": json.dumps(categories),
                "images": json.dumps(product.get("images", []))
            })

            return {"id": result[0]["id"], "message": "Product created successfully"}

        # Category Management
        @router.get("/categories/{category_id}")
        def get_category(category_id: int):
            """Get single category"""
            result = execute_main_db_query(
                f'SELECT * FROM "{categories_table}" WHERE id = :id AND is_active = true',
                {"id": category_id}
            )
            if not result:
                raise HTTPException(status_code=404, detail="Category not found")
            return result[0]

        @router.get("/categories")
        def get_categories(language: Optional[str] = None):
            """Get all categories with translations"""
            try:
                # Get current language from request or default to 'en'
                current_language = language or "en"

                # Get base categories
                base_categories = execute_main_db_query(
                    f'SELECT * FROM "{categories_table}" WHERE is_active = true ORDER BY sort_order, name'
                )

                # Apply translations synchronously if needed
                if current_language != "en" and base_categories:
                    translated_categories = []
                    for category in base_categories:
                        # Try to get translation from extension-specific translations table
                        translation_query = f"""
                            SELECT translation_data FROM "{translations_table}"
                            WHERE record_id = :record_id
                            AND language_code = :language_code
                        """
                        translation_result = execute_main_db_query(translation_query, {
                            "record_id": category["id"],
                            "language_code": current_language
                        })

                        if translation_result and translation_result[0]["translation_data"]:
                            try:
                                # SQLAlchemy automatically parses JSONB fields, so check if it's already a dict
                                translation_raw = translation_result[0]["translation_data"]
                                if isinstance(translation_raw, dict):
                                    translation_data = translation_raw
                                else:
                                    translation_data = json.loads(translation_raw)
                                # Merge translation with base category
                                translated_category = category.copy()
                                translated_category.update(translation_data)
                                translated_categories.append(translated_category)
                            except Exception as e:
                                print(f"Error parsing category translation: {e}")
                                translated_categories.append(category)  # Fallback to original
                        else:
                            translated_categories.append(category)  # No translation available

                    return {"items": translated_categories}
                else:
                    return {"items": base_categories or []}
            except Exception as e:
                print(f"ERROR in get_categories: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to fetch categories: {str(e)}")

        @router.post("/categories")
        def create_category(category: dict, claims: dict = Depends(require_user)):
            """Create new category"""
            if not category.get("name") or not category.get("slug"):
                raise HTTPException(status_code=400, detail="Name and slug are required")

            result = execute_main_db_query(f"""
                INSERT INTO "{categories_table}" (name, slug, description)
                VALUES (:name, :slug, :description)
                RETURNING id
            """, {
                "name": category["name"],
                "slug": category["slug"],
                "description": category.get("description", "")
            })

            return {"id": result[0]["id"], "message": "Category created successfully"}

        @router.put("/categories/{category_id}")
        def update_category(category_id: int, category: dict, claims: dict = Depends(require_user)):
            """Update category"""
            update_fields = []
            params = {"category_id": category_id}

            if "name" in category:
                update_fields.append("name = :name")
                params["name"] = category["name"]
            if "slug" in category:
                update_fields.append("slug = :slug")
                params["slug"] = category["slug"]
            if "description" in category:
                update_fields.append("description = :description")
                params["description"] = category["description"]

            if update_fields:
                execute_main_db_query(f"""
                    UPDATE "{categories_table}"
                    SET {', '.join(update_fields)}
                    WHERE id = :category_id
                """, params)

            return {"message": "Category updated successfully"}

        @router.delete("/categories/{category_id}")
        def delete_category(category_id: int, claims: dict = Depends(require_user)):
            """Delete category"""
            execute_main_db_query(
                f'DELETE FROM {categories_table} WHERE id = :id',
                {"id": category_id}
            )
            return {"message": "Category deleted successfully"}


        # File Upload Endpoint
        @router.post("/upload-image")
        def upload_product_image(
            file: UploadFile = File(...),
            directory: str = "store",
            replace_filename: str = None,
            claims: dict = Depends(require_user)
        ):
            """Upload product image"""
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
        def list_store_images(directory: str = "store", search: Optional[str] = None, limit: int = 100, offset: int = 0):
            """List images and folders in the store uploads directory"""
            try:
                import os
                from datetime import datetime

                # Base uploads directory
                base_uploads_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'uploads')

                # Target directory (default to 'store')
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
                path_parts = directory.split("/") if directory != "store" else []
                breadcrumb = []
                current_path = "store"
                breadcrumb.append({"name": "Store", "path": "store"})

                for part in path_parts:
                    if part and part != "store":
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
                print(f"Error listing store images: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to list images: {str(e)}")

        # Create Folder Endpoint
        @router.post("/images/folder")
        def create_image_folder(data: dict, claims: dict = Depends(require_user)):
            """Create a new folder in the store uploads directory"""
            try:
                import os

                folder_name = data.get("folder_name")
                directory = data.get("directory", "store")

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

        # Move Image Endpoint
        @router.post("/images/move")
        def move_image(data: dict, claims: dict = Depends(require_user)):
            """Move an image from one directory to another"""
            try:
                import os
                import shutil

                image_name = data.get("image_name")
                from_directory = data.get("from_directory", "store")
                to_directory = data.get("to_directory")

                if not image_name or not to_directory:
                    raise HTTPException(status_code=400, detail="image_name and to_directory are required")

                # Base uploads directory
                base_uploads_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'uploads')

                # Source and destination paths
                source_dir = os.path.join(base_uploads_dir, from_directory)
                dest_dir = os.path.join(base_uploads_dir, to_directory)
                source_file = os.path.join(source_dir, image_name)
                dest_file = os.path.join(dest_dir, image_name)

                # Ensure destination directory exists
                os.makedirs(dest_dir, exist_ok=True)

                # Check if source file exists
                if not os.path.exists(source_file):
                    raise HTTPException(status_code=404, detail="Source image not found")

                # Check if destination file already exists
                if os.path.exists(dest_file):
                    raise HTTPException(status_code=400, detail="Image already exists in destination")

                # Move the file
                shutil.move(source_file, dest_file)

                return {
                    "message": "Image moved successfully",
                    "image": {
                        "name": image_name,
                        "from_directory": from_directory,
                        "to_directory": to_directory,
                        "new_url": f"/uploads/{to_directory}/{image_name}"
                    }
                }

            except HTTPException:
                raise
            except Exception as e:
                print(f"Error moving image: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to move image: {str(e)}")

        # Delete Image Endpoint
        @router.delete("/images/delete")
        def delete_image(data: dict, claims: dict = Depends(require_user)):
            """Delete an image from the store uploads directory"""
            try:
                import os

                image_name = data.get("image_name")
                directory = data.get("directory", "store")

                if not image_name:
                    raise HTTPException(status_code=400, detail="image_name is required")

                # Base uploads directory
                base_uploads_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'uploads')

                # Target directory
                target_dir = os.path.join(base_uploads_dir, directory)

                # Image file path
                image_path = os.path.join(target_dir, image_name)

                # Check if image exists
                if not os.path.exists(image_path):
                    raise HTTPException(status_code=404, detail="Image not found")

                # Delete the image
                os.remove(image_path)

                return {
                    "message": "Image deleted successfully",
                    "image": {
                        "name": image_name,
                        "directory": directory
                    }
                }

            except HTTPException:
                raise
            except Exception as e:
                print(f"Error deleting image: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to delete image: {str(e)}")

        # Rename Image Endpoint
        @router.post("/images/rename")
        def rename_image(data: dict, claims: dict = Depends(require_user)):
            """Rename an image in the store uploads directory"""
            try:
                import os

                current_name = data.get("current_name")
                new_name = data.get("new_name")
                directory = data.get("directory", "store")

                if not current_name or not new_name:
                    raise HTTPException(status_code=400, detail="current_name and new_name are required")

                # Validate new name (prevent directory traversal)
                if ".." in new_name or "/" in new_name or "\\" in new_name:
                    raise HTTPException(status_code=400, detail="Invalid filename")

                # Base uploads directory
                base_uploads_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'uploads')

                # Target directory
                target_dir = os.path.join(base_uploads_dir, directory)

                # Current and new file paths
                current_path = os.path.join(target_dir, current_name)
                new_path = os.path.join(target_dir, new_name)

                # Check if current file exists
                if not os.path.exists(current_path):
                    raise HTTPException(status_code=404, detail="Image not found")

                # Check if new name already exists
                if os.path.exists(new_path):
                    raise HTTPException(status_code=400, detail="A file with this name already exists")

                # Rename the file
                os.rename(current_path, new_path)

                return {
                    "message": "Image renamed successfully",
                    "image": {
                        "old_name": current_name,
                        "new_name": new_name,
                        "directory": directory
                    }
                }

            except HTTPException:
                raise
            except Exception as e:
                print(f"Error renaming image: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to rename image: {str(e)}")

        # Cart Management
        @router.get("/cart")
        def get_cart(session_id: str = None, language: Optional[str] = None):
            """Get cart contents with product details and images"""
            if not session_id:
                return {"items": []}

            # Get current language from request or default to 'en'
            current_language = language or "en"

            result = execute_main_db_query(
                f'SELECT items FROM {cart_table} WHERE session_id = :session_id',
                {"session_id": session_id}
            )
            if result and result[0]["items"]:
                try:
                    items = json.loads(result[0]["items"])

                    # Enrich cart items with product details and images
                    enriched_items = []
                    for item in items:
                        product_id = item["product_id"]

                        # Get product details including images
                        product_result = execute_main_db_query(
                            f'SELECT id, name, images FROM "{products_table}" WHERE id = :id AND is_active = true',
                            {"id": product_id}
                        )

                        if product_result:
                            product = product_result[0]

                            # Apply translations if needed
                            if current_language != "en":
                                translation_query = f"""
                                    SELECT translation_data FROM "{translations_table}"
                                    WHERE record_id = :record_id
                                    AND language_code = :language_code
                                """
                                translation_result = execute_main_db_query(translation_query, {
                                    "record_id": product_id,
                                    "language_code": current_language
                                })

                                if translation_result and translation_result[0]["translation_data"]:
                                    try:
                                        # SQLAlchemy automatically parses JSONB fields, so check if it's already a dict
                                        translation_raw = translation_result[0]["translation_data"]
                                        if isinstance(translation_raw, dict):
                                            translation_data = translation_raw
                                        else:
                                            translation_data = json.loads(translation_raw)
                                        product = product.copy()
                                        product.update(translation_data)
                                    except Exception as e:
                                        print(f"Error parsing product translation data: {e}")

                            # Add product image to cart item
                            try:
                                images = json.loads(product.get("images", "[]"))
                                item["image"] = images[0] if images else None
                            except:
                                item["image"] = None

                            # Update product name if translated
                            if "name" in product:
                                item["name"] = product["name"]

                        enriched_items.append(item)

                    return {"items": enriched_items}
                except Exception as e:
                    print(f"Error loading cart: {e}")
                    return {"items": []}
            return {"items": []}

        @router.post("/cart/add")
        def add_to_cart(item: dict, session_id: str = None):
            """Add item to cart (works for guests and logged-in users)"""
            # Get session_id from query param or item data
            if not session_id:
                session_id = item.get("session_id")
            if not session_id:
                # For guests, we need a session_id - this should be provided by frontend
                raise HTTPException(status_code=400, detail="session_id is required")

            # Get existing cart or create new one
            cart_result = execute_main_db_query(
                f'SELECT id, items FROM {cart_table} WHERE session_id = :session_id',
                {"session_id": session_id}
            )

            if cart_result:
                cart_id = cart_result[0]["id"]
                current_items = json.loads(cart_result[0]["items"]) if cart_result[0]["items"] else []
            else:
                # Create new cart
                cart_insert = execute_main_db_query(f"""
                    INSERT INTO {cart_table} (session_id, items)
                    VALUES (:session_id, :items)
                    RETURNING id
                """, {"session_id": session_id, "items": "[]"})
                cart_id = cart_insert[0]["id"]
                current_items = []

            # Add/update item in cart
            item_found = False
            for cart_item in current_items:
                if (cart_item["product_id"] == item["product_id"] and
                    cart_item.get("variant_data") == item.get("variant_data")):
                    cart_item["quantity"] += item.get("quantity", 1)
                    # Remove item if quantity becomes 0 or negative
                    if cart_item["quantity"] <= 0:
                        current_items.remove(cart_item)
                    item_found = True
                    break

            if not item_found and item.get("quantity", 1) > 0:
                current_items.append({
                    "product_id": item["product_id"],
                    "name": item.get("name", ""),
                    "price": item["price"],
                    "quantity": item.get("quantity", 1),
                    "sku": item.get("sku", ""),
                    "variant_data": item.get("variant_data")
                })

            # Update cart
            execute_main_db_query(f"""
                UPDATE {cart_table}
                SET items = :items, updated_at = CURRENT_TIMESTAMP
                WHERE id = :cart_id
            """, {"items": json.dumps(current_items), "cart_id": cart_id})

            return {"message": "Item added to cart", "cart_count": len(current_items)}

        @router.delete("/cart")
        def clear_cart(session_id: str = None):
            """Clear cart"""
            if session_id:
                execute_main_db_query(
                    f'DELETE FROM "{cart_table}" WHERE session_id = :session_id',
                    {"session_id": session_id}
                )
            return {"message": "Cart cleared"}

        # Order Management
        @router.post("/orders")
        def create_order(order_data: dict, claims: dict = Depends(require_user)):
            """Create new order"""
            user_id = claims.get("user_id")

            # Generate order number
            order_number = f"ORD-{datetime.now().strftime('%Y%m%d')}-{user_id}"

            # Calculate totals
            subtotal = order_data["subtotal"]
            tax_amount = subtotal * 0.1  # 10% tax (configurable)
            shipping_amount = order_data.get("shipping_amount", 0)
            total_amount = subtotal + tax_amount + shipping_amount

            # Create order
            order_result = execute_main_db_query(f"""
                INSERT INTO "{orders_table}"
                (order_number, customer_id, subtotal, tax_amount, shipping_amount, total_amount,
                 billing_address, shipping_address, payment_method, shipping_method)
                VALUES (:order_number, :customer_id, :subtotal, :tax_amount, :shipping_amount, :total_amount,
                        :billing_address, :shipping_address, :payment_method, :shipping_method)
                RETURNING id
            """, {
                "order_number": order_number,
                "customer_id": user_id,
                "subtotal": subtotal,
                "tax_amount": tax_amount,
                "shipping_amount": shipping_amount,
                "total_amount": total_amount,
                "billing_address": json.dumps(order_data["billing_address"]),
                "shipping_address": json.dumps(order_data["shipping_address"]),
                "payment_method": order_data["payment_method"],
                "shipping_method": order_data.get("shipping_method", "standard")
            })

            order_id = order_result[0]["id"]

            # Create order items
            for item in order_data["items"]:
                execute_main_db_query(f"""
                    INSERT INTO "{order_items_table}"
                    (order_id, product_id, product_name, product_sku, quantity, unit_price, total_price, variant_data)
                    VALUES (:order_id, :product_id, :product_name, :product_sku, :quantity, :unit_price, :total_price, :variant_data)
                """, {
                    "order_id": order_id,
                    "product_id": item["product_id"],
                    "product_name": item["name"],
                    "product_sku": item.get("sku", ""),
                    "quantity": item["quantity"],
                    "unit_price": item["price"],
                    "total_price": item["quantity"] * item["price"],
                    "variant_data": json.dumps(item.get("variant_data", {}))
                })

                # Update product stock
                execute_main_db_query(f"""
                    UPDATE "{products_table}"
                    SET stock_quantity = stock_quantity - :quantity
                    WHERE id = :product_id
                """, {"quantity": item["quantity"], "product_id": item["product_id"]})

            # Clear cart
            execute_main_db_query(
                f'DELETE FROM "{cart_table}" WHERE session_id = :session_id',
                {"session_id": order_data.get("session_id")}
            )

            return {
                "order_id": order_id,
                "order_number": order_number,
                "total_amount": total_amount,
                "message": "Order created successfully"
            }

        @router.get("/orders")
        def get_orders(claims: dict = Depends(require_user)):
            """Get user orders"""
            user_id = claims.get("user_id")
            result = execute_main_db_query(
                f'SELECT * FROM "{orders_table}" WHERE customer_id = :user_id ORDER BY created_at DESC',
                {"user_id": user_id}
            )
            return {"items": result}

        # Category Translation Management
        @router.post("/categories/{category_id}/translations")
        def add_category_translation(
            category_id: int,
            data: Dict[str, Any],
            claims: dict = Depends(require_user)
        ):
            """Add translations for a category"""
            try:
                language_code = data.get("language_code")
                translations = data.get("translations", {})

                if not language_code:
                    raise HTTPException(status_code=400, detail="language_code is required")

                if not translations or not isinstance(translations, dict):
                    raise HTTPException(status_code=400, detail="translations must be a non-empty object")

                # Check if category exists
                category_check = execute_main_db_query(
                    f'SELECT id FROM "{categories_table}" WHERE id = :id',
                    {"id": category_id}
                )
                if not category_check:
                    raise HTTPException(status_code=404, detail="Category not found")

                # Insert or update translation
                translation_data = json.dumps(translations)

                # Check if translation already exists
                existing = execute_main_db_query(f"""
                    SELECT id FROM "{translations_table}"
                    WHERE record_id = :record_id
                    AND language_code = :language_code
                """, {
                    "record_id": category_id,
                    "language_code": language_code
                })

                if existing:
                    # Update existing translation
                    execute_main_db_query(f"""
                        UPDATE "{translations_table}"
                        SET translation_data = :translation_data,
                            translation_coverage = :coverage,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE record_id = :record_id
                        AND language_code = :language_code
                    """, {
                        "translation_data": translation_data,
                        "coverage": len(translations) / 2 * 100,  # 2 translatable fields: name, description
                        "record_id": category_id,
                        "language_code": language_code
                    })
                else:
                    # Insert new translation
                    execute_main_db_query(f"""
                        INSERT INTO "{translations_table}"
                        (record_id, language_code, translation_data, translation_coverage)
                        VALUES (:record_id, :language_code, :translation_data, :coverage)
                    """, {
                        "record_id": category_id,
                        "language_code": language_code,
                        "translation_data": translation_data,
                        "coverage": len(translations) / 2 * 100
                    })

                return {"message": f"Translations added for {language_code}"}
            except Exception as e:
                print(f"Error adding category translations: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to add translations: {str(e)}")

        @router.get("/categories/{category_id}/translations")
        def get_category_translations(category_id: int):
            """Get all translations for a category (public access for display)"""
            try:
                result = execute_main_db_query(f"""
                    SELECT language_code, translation_data, translation_coverage
                    FROM "{translations_table}"
                    WHERE record_id = :record_id
                """, {
                    "record_id": category_id
                })

                translations = []
                for row in result or []:
                    # translation_data is already parsed by SQLAlchemy as dict
                    translation_data = row["translation_data"] if isinstance(row["translation_data"], dict) else {}

                    translations.append({
                        "language_code": row["language_code"],
                        "data": translation_data,
                        "coverage": float(row["translation_coverage"]) if row["translation_coverage"] else 0
                    })

                return {
                    "category_id": category_id,
                    "translations": translations
                }
            except Exception as e:
                print(f"Error getting category translations: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get translations: {str(e)}")

        @router.delete("/categories/{category_id}/translations/{language_code}")
        def delete_category_translation(
            category_id: int,
            language_code: str,
            claims: dict = Depends(require_user)
        ):
            """Delete translations for a specific language"""
            try:
                execute_main_db_query(f"""
                    DELETE FROM "{translations_table}"
                    WHERE record_id = :record_id
                    AND language_code = :language_code
                """, {
                    "record_id": category_id,
                    "language_code": language_code
                })

                return {"message": f"Translations deleted for {language_code}"}
            except Exception as e:
                print(f"Error deleting category translations: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to delete translations: {str(e)}")

        # Store Settings Translation Management
        @router.post("/settings/translations")
        def add_store_settings_translation(data: Dict[str, Any], claims: dict = Depends(require_user)):
            """Add translations for store settings"""
            try:
                language_code = data.get("language_code")
                translations = data.get("translations", {})

                if not language_code:
                    raise HTTPException(status_code=400, detail="language_code is required")

                if not translations or not isinstance(translations, dict):
                    raise HTTPException(status_code=400, detail="translations must be a non-empty object")

                # Insert or update translation
                translation_data = json.dumps(translations)

                # Check if translation already exists
                existing = execute_main_db_query(f"""
                    SELECT id FROM "{translations_table}"
                    WHERE record_id = :record_id
                    AND language_code = :language_code
                """, {
                    "record_id": 0,  # Use 0 for store settings
                    "language_code": language_code
                })

                if existing:
                    # Update existing translation
                    execute_main_db_query(f"""
                        UPDATE "{translations_table}"
                        SET translation_data = :translation_data,
                            translation_coverage = :coverage,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE record_id = :record_id
                        AND language_code = :language_code
                    """, {
                        "translation_data": translation_data,
                        "coverage": len(translations) / 1 * 100,  # 1 translatable field: storeName
                        "record_id": 0,
                        "language_code": language_code
                    })
                else:
                    # Insert new translation
                    execute_main_db_query(f"""
                        INSERT INTO "{translations_table}"
                        (record_id, language_code, translation_data, translation_coverage)
                        VALUES (:record_id, :language_code, :translation_data, :coverage)
                    """, {
                        "record_id": 0,
                        "language_code": language_code,
                        "translation_data": translation_data,
                        "coverage": len(translations) / 1 * 100
                    })

                return {"message": f"Store settings translations added for {language_code}"}
            except Exception as e:
                print(f"Error adding store settings translations: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to add translations: {str(e)}")


        # Translation Management
        @router.post("/products/{product_id}/translations")
        def add_product_translation(
            product_id: int,
            data: Dict[str, Any],
            claims: dict = Depends(require_user)
        ):
            """Add translations for a product"""
            try:
                language_code = data.get("language_code")
                translations = data.get("translations", {})

                if not language_code:
                    raise HTTPException(status_code=400, detail="language_code is required")

                if not translations or not isinstance(translations, dict):
                    raise HTTPException(status_code=400, detail="translations must be a non-empty object")

                # Check if product exists
                product_check = execute_main_db_query(
                    f'SELECT id FROM "{products_table}" WHERE id = :id',
                    {"id": product_id}
                )
                if not product_check:
                    raise HTTPException(status_code=404, detail="Product not found")

                # Insert or update translation
                translation_data = json.dumps(translations)

                # Check if translation already exists
                existing = execute_main_db_query(f"""
                    SELECT id FROM "{translations_table}"
                    WHERE record_id = :record_id
                    AND language_code = :language_code
                """, {
                    "record_id": product_id,
                    "language_code": language_code
                })

                if existing:
                    # Update existing translation
                    execute_main_db_query(f"""
                        UPDATE "{translations_table}"
                        SET translation_data = :translation_data,
                            translation_coverage = :coverage,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE record_id = :record_id
                        AND language_code = :language_code
                    """, {
                        "translation_data": translation_data,
                        "coverage": len(translations) / 3 * 100,  # 3 translatable fields
                        "record_id": product_id,
                        "language_code": language_code
                    })
                else:
                    # Insert new translation
                    execute_main_db_query(f"""
                        INSERT INTO "{translations_table}"
                        (record_id, language_code, translation_data, translation_coverage)
                        VALUES (:record_id, :language_code, :translation_data, :coverage)
                    """, {
                        "record_id": product_id,
                        "language_code": language_code,
                        "translation_data": translation_data,
                        "coverage": len(translations) / 3 * 100
                    })

                return {"message": f"Translations added for {language_code}"}
            except Exception as e:
                print(f"Error adding translations: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to add translations: {str(e)}")

        @router.get("/products/{product_id}/translations")
        def get_product_translations(product_id: int):
            """Get all translations for a product (public access for display)"""
            try:
                result = execute_main_db_query(f"""
                    SELECT language_code, translation_data, translation_coverage
                    FROM "{translations_table}"
                    WHERE record_id = :record_id
                """, {
                    "record_id": product_id
                })

                translations = []
                for row in result or []:
                    # translation_data is already parsed by SQLAlchemy as dict
                    translation_data = row["translation_data"] if isinstance(row["translation_data"], dict) else {}

                    translations.append({
                        "language_code": row["language_code"],
                        "data": translation_data,
                        "coverage": float(row["translation_coverage"]) if row["translation_coverage"] else 0
                    })

                return {
                    "product_id": product_id,
                    "translations": translations
                }
            except Exception as e:
                print(f"Error getting translations: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get translations: {str(e)}")

        @router.delete("/products/{product_id}/translations/{language_code}")
        def delete_product_translation(
            product_id: int,
            language_code: str,
            claims: dict = Depends(require_user)
        ):
            """Delete translations for a specific language"""
            try:
                execute_main_db_query(f"""
                    DELETE FROM "{translations_table}"
                    WHERE record_id = :record_id
                    AND language_code = :language_code
                """, {
                    "record_id": product_id,
                    "language_code": language_code
                })

                return {"message": f"Translations deleted for {language_code}"}
            except Exception as e:
                print(f"Error deleting translations: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to delete translations: {str(e)}")

        # Settings Management (public read access for store display)
        @router.get("/settings")
        def get_settings(language: Optional[str] = None):
            """Get store settings with translations"""
            try:
                # Get current language from request or default to 'en'
                current_language = language or "en"

                # Get extension settings from the extension-specific settings table
                settings_result = execute_main_db_query(f"""
                    SELECT settings_data FROM "{settings_table}"
                    WHERE extension_id = :extension_id
                """, {"extension_id": extension_db_id})

                base_settings = None
                if settings_result and settings_result[0]["settings_data"]:
                    settings_data = settings_result[0]["settings_data"]

                    # SQLAlchemy may already parse JSONB, so check if it's already a dict
                    if isinstance(settings_data, dict):
                        base_settings = settings_data
                    else:
                        try:
                            base_settings = json.loads(settings_data)
                        except Exception as e:
                            pass

                default_currency_formats: Dict[str, Dict[str, Any]] = {
                    "USD": {"label": "$", "position": "prefix"},
                    "EUR": {"label": "€", "position": "prefix"},
                    "GBP": {"label": "£", "position": "prefix"},
                    "BGN": {"label": "лв", "position": "suffix"},
                    "JPY": {"label": "¥", "position": "prefix"},
                    "CAD": {"label": "C$", "position": "prefix"},
                    "AUD": {"label": "A$", "position": "prefix"}
                }

                # Return default settings if none exist
                if not base_settings:
                    base_settings = {
                        "storeName": "My Store",
                        "currency": "USD",
                        "currencies": default_currency_formats,
                        "locations": [],
                        "taxRate": 0,
                        "shippingEnabled": True,
                        "paymentMethods": ["stripe"]
                    }

                # Backwards-compat: ensure currency format definitions exist
                if not isinstance(base_settings, dict):
                    base_settings = {}

                currencies = base_settings.get("currencies")
                if not isinstance(currencies, dict) or not currencies:
                    base_settings["currencies"] = default_currency_formats
                else:
                    # Merge defaults for known currencies without overwriting custom ones
                    for code, fmt in default_currency_formats.items():
                        if code not in currencies:
                            currencies[code] = fmt

                # Ensure active currency exists in currencies map
                active_code = (base_settings.get("currency") or "USD").strip() or "USD"
                if active_code not in base_settings["currencies"]:
                    # If unknown code, create a minimal format (prefix) using the code as label
                    base_settings["currencies"][active_code] = {"label": active_code, "position": "prefix"}
                base_settings["currency"] = active_code

                # Ensure locations exists
                locations = base_settings.get("locations")
                if not isinstance(locations, list):
                    base_settings["locations"] = []

                # Apply translations if needed
                if current_language != "en":
                    settings_record_id = 0
                    translation_query = f"""
                        SELECT translation_data FROM "{translations_table}"
                        WHERE record_id = :record_id
                        AND language_code = :language_code
                    """
                    translation_result = execute_main_db_query(translation_query, {
                        "record_id": settings_record_id,
                        "language_code": current_language
                    })

                    if translation_result and translation_result[0]["translation_data"]:
                        translation_raw = translation_result[0]["translation_data"]

                        # SQLAlchemy may already parse JSONB, so check if it's already a dict
                        if isinstance(translation_raw, dict):
                            translation_data = translation_raw
                        else:
                            try:
                                translation_data = json.loads(translation_raw)
                            except Exception as e:
                                print(f"Error parsing settings translation: {e}")
                                return base_settings

                        # Merge translation with base settings.
                        # For locations we keep the base array ordering and apply per-location overrides
                        # from translation_data.locationTranslations (keyed by location id).
                        translated_settings = base_settings.copy()

                        location_translations = translation_data.get("locationTranslations") or translation_data.get("locationsTranslations") or {}

                        for key, value in translation_data.items():
                            if key in ("locationTranslations", "locationsTranslations", "locations"):
                                continue
                            translated_settings[key] = value

                        if isinstance(location_translations, dict) and isinstance(translated_settings.get("locations"), list):
                            for loc in translated_settings["locations"]:
                                if not isinstance(loc, dict):
                                    continue
                                loc_id = str(loc.get("id") or "")
                                if not loc_id:
                                    continue
                                loc_tr = location_translations.get(loc_id)
                                if isinstance(loc_tr, dict):
                                    loc.update(loc_tr)

                        return translated_settings

                return base_settings
            except Exception as e:
                print(f"Error getting settings: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get settings: {str(e)}")

        @router.put("/settings")
        def update_settings(settings: dict, claims: dict = Depends(require_user)):
            """Update store settings"""
            try:
                settings_json = json.dumps(settings)

                # Check if settings already exist
                existing = execute_main_db_query(f"""
                    SELECT id FROM "{settings_table}"
                    WHERE extension_id = :extension_id
                """, {"extension_id": extension_db_id})

                if existing:
                    # Update existing settings
                    execute_main_db_query(f"""
                        UPDATE "{settings_table}"
                        SET settings_data = :settings_data, updated_at = CURRENT_TIMESTAMP
                        WHERE extension_id = :extension_id
                    """, {
                        "settings_data": settings_json,
                        "extension_id": extension_db_id
                    })
                else:
                    # Insert new settings
                    execute_main_db_query(f"""
                        INSERT INTO "{settings_table}" (extension_id, settings_data)
                        VALUES (:extension_id, :settings_data)
                    """, {
                        "extension_id": extension_db_id,
                        "settings_data": settings_json
                    })

                return {"message": "Settings updated successfully"}
            except Exception as e:
                print(f"Error updating settings: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to update settings: {str(e)}")

        # Settings Translation Management
        @router.post("/settings/translations")
        def add_settings_translation(
            data: Dict[str, Any],
            claims: dict = Depends(require_user)
        ):
            """Add translations for settings"""
            try:
                language_code = data.get("language_code")
                translations = data.get("translations", {})

                if not language_code:
                    raise HTTPException(status_code=400, detail="language_code is required")

                if not translations or not isinstance(translations, dict):
                    raise HTTPException(status_code=400, detail="translations must be a non-empty object")

                # Use a special record_id for settings (0)
                settings_record_id = 0

                # Insert or update translation
                translation_data = json.dumps(translations)

                # Check if translation already exists
                existing = execute_main_db_query(f"""
                    SELECT id FROM "{translations_table}"
                    WHERE record_id = :record_id
                    AND language_code = :language_code
                """, {
                    "record_id": settings_record_id,
                    "language_code": language_code
                })

                if existing:
                    # Update existing translation
                    execute_main_db_query(f"""
                        UPDATE "{translations_table}"
                        SET translation_data = :translation_data,
                            translation_coverage = :coverage,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE record_id = :record_id
                        AND language_code = :language_code
                    """, {
                        "translation_data": translation_data,
                        "coverage": len(translations) / 1 * 100,  # 1 translatable field: storeName
                        "record_id": settings_record_id,
                        "language_code": language_code
                    })
                else:
                    # Insert new translation
                    execute_main_db_query(f"""
                        INSERT INTO "{translations_table}"
                        (record_id, language_code, translation_data, translation_coverage)
                        VALUES (:record_id, :language_code, :translation_data, :coverage)
                    """, {
                        "record_id": settings_record_id,
                        "language_code": language_code,
                        "translation_data": translation_data,
                        "coverage": len(translations) / 1 * 100
                    })

                return {"message": f"Settings translations added for {language_code}"}
            except Exception as e:
                print(f"Error adding settings translations: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to add settings translations: {str(e)}")

        @router.get("/settings/translations")
        def get_settings_translations():
            """Get all translations for settings"""
            try:
                settings_record_id = 0
                result = execute_main_db_query(f"""
                    SELECT language_code, translation_data, translation_coverage
                    FROM "{translations_table}"
                    WHERE record_id = :record_id
                """, {
                    "record_id": settings_record_id
                })

                translations = []
                for row in result or []:
                    # translation_data is already parsed by SQLAlchemy as dict
                    translation_data = row["translation_data"] if isinstance(row["translation_data"], dict) else {}

                    translations.append({
                        "language_code": row["language_code"],
                        "data": translation_data,
                        "coverage": float(row["translation_coverage"]) if row["translation_coverage"] else 0
                    })

                return {
                    "settings_id": settings_record_id,
                    "translations": translations
                }
            except Exception as e:
                print(f"Error getting settings translations: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get settings translations: {str(e)}")

        @router.delete("/settings/translations/{language_code}")
        def delete_settings_translation(
            language_code: str,
            claims: dict = Depends(require_user)
        ):
            """Delete translations for settings in a specific language"""
            try:
                settings_record_id = 0
                execute_main_db_query(f"""
                    DELETE FROM "{translations_table}"
                    WHERE record_id = :record_id
                    AND language_code = :language_code
                """, {
                    "record_id": settings_record_id,
                    "language_code": language_code
                })

                return {"message": f"Settings translations deleted for {language_code}"}
            except Exception as e:
                print(f"Error deleting settings translations: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to delete settings translations: {str(e)}")

        # Product Reviews Management
        @router.get("/products/{product_id}/reviews")
        def get_product_reviews(
            product_id: int,
            limit: int = 10,
            offset: int = 0,
            approved_only: bool = True
        ):
            """Get reviews for a product"""
            try:
                # Check if product exists
                product_check = execute_main_db_query(
                    f'SELECT id FROM "{products_table}" WHERE id = :id',
                    {"id": product_id}
                )
                if not product_check:
                    raise HTTPException(status_code=404, detail="Product not found")

                # Get reviews
                where_clause = "product_id = :product_id"
                params = {"product_id": product_id}

                if approved_only:
                    where_clause += " AND is_approved = true"

                reviews = execute_main_db_query(f"""
                    SELECT id, customer_name, rating, title, comment, created_at
                    FROM "{reviews_table}"
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    LIMIT :limit OFFSET :offset
                """, {**params, "limit": limit, "offset": offset})

                # Get total count
                total_result = execute_main_db_query(f"""
                    SELECT COUNT(*) as total FROM "{reviews_table}"
                    WHERE {where_clause}
                """, params)

                total = total_result[0]["total"] if total_result else 0

                # Calculate average rating
                avg_result = execute_main_db_query(f"""
                    SELECT AVG(rating) as avg_rating FROM "{reviews_table}"
                    WHERE product_id = :product_id AND is_approved = true
                """, {"product_id": product_id})

                avg_rating = float(avg_result[0]["avg_rating"]) if avg_result and avg_result[0]["avg_rating"] else 0

                return {
                    "reviews": reviews,
                    "total": total,
                    "average_rating": round(avg_rating, 1) if avg_rating else 0,
                    "rating_distribution": get_rating_distribution(product_id)
                }
            except Exception as e:
                print(f"Error getting product reviews: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get reviews: {str(e)}")

        @router.post("/products/{product_id}/reviews")
        def create_product_review(product_id: int, review: dict):
            """Create a new review for a product"""
            try:
                # Validate required fields
                if not review.get("customer_name") or not review.get("rating"):
                    raise HTTPException(status_code=400, detail="Customer name and rating are required")

                rating = review.get("rating")
                if not isinstance(rating, int) or rating < 1 or rating > 5:
                    raise HTTPException(status_code=400, detail="Rating must be an integer between 1 and 5")

                # Check if product exists
                product_check = execute_main_db_query(
                    f'SELECT id FROM "{products_table}" WHERE id = :id',
                    {"id": product_id}
                )
                if not product_check:
                    raise HTTPException(status_code=404, detail="Product not found")

                # Insert review
                result = execute_main_db_query(f"""
                    INSERT INTO "{reviews_table}"
                    (product_id, customer_name, customer_email, rating, title, comment)
                    VALUES (:product_id, :customer_name, :customer_email, :rating, :title, :comment)
                    RETURNING id
                """, {
                    "product_id": product_id,
                    "customer_name": review["customer_name"],
                    "customer_email": review.get("customer_email", ""),
                    "rating": rating,
                    "title": review.get("title", ""),
                    "comment": review.get("comment", "")
                })

                return {
                    "id": result[0]["id"],
                    "message": "Review submitted successfully. It will be published after approval."
                }
            except Exception as e:
                print(f"Error creating product review: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to create review: {str(e)}")

        @router.put("/reviews/{review_id}")
        def update_review(review_id: int, review: dict, claims: dict = Depends(require_user)):
            """Update a review (admin only)"""
            try:
                update_fields = []
                params = {"review_id": review_id}

                if "is_approved" in review:
                    update_fields.append("is_approved = :is_approved")
                    params["is_approved"] = review["is_approved"]

                if update_fields:
                    execute_main_db_query(f"""
                        UPDATE "{reviews_table}"
                        SET {', '.join(update_fields)}, updated_at = CURRENT_TIMESTAMP
                        WHERE id = :review_id
                    """, params)

                return {"message": "Review updated successfully"}
            except Exception as e:
                print(f"Error updating review: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to update review: {str(e)}")

        @router.delete("/reviews/{review_id}")
        def delete_review(review_id: int, claims: dict = Depends(require_user)):
            """Delete a review (admin only)"""
            try:
                execute_main_db_query(f"""
                    DELETE FROM "{reviews_table}" WHERE id = :id
                """, {"id": review_id})

                return {"message": "Review deleted successfully"}
            except Exception as e:
                print(f"Error deleting review: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to delete review: {str(e)}")

        @router.get("/reviews")
        def get_all_reviews(
            approved: Optional[bool] = None,
            limit: int = 20,
            offset: int = 0,
            claims: dict = Depends(require_user)
        ):
            """Get all reviews (admin only)"""
            try:
                where_clause = "1=1"
                params = {}

                if approved is not None:
                    where_clause += " AND is_approved = :approved"
                    params["approved"] = approved

                reviews = execute_main_db_query(f"""
                    SELECT r.*, p.name as product_name
                    FROM "{reviews_table}" r
                    LEFT JOIN "{products_table}" p ON r.product_id = p.id
                    WHERE {where_clause}
                    ORDER BY r.created_at DESC
                    LIMIT :limit OFFSET :offset
                """, {**params, "limit": limit, "offset": offset})

                # Get total count
                total_result = execute_main_db_query(f"""
                    SELECT COUNT(*) as total FROM "{reviews_table}"
                    WHERE {where_clause}
                """, params)

                total = total_result[0]["total"] if total_result else 0

                return {"reviews": reviews, "total": total}
            except Exception as e:
                print(f"Error getting all reviews: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to get reviews: {str(e)}")

        def get_rating_distribution(product_id: int):
            """Get rating distribution for a product"""
            try:
                result = execute_main_db_query(f"""
                    SELECT rating, COUNT(*) as count
                    FROM "{reviews_table}"
                    WHERE product_id = :product_id AND is_approved = true
                    GROUP BY rating
                    ORDER BY rating
                """, {"product_id": product_id})

                distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
                for row in result:
                    distribution[row["rating"]] = row["count"]

                return distribution
            except Exception as e:
                print(f"Error getting rating distribution: {e}")
                return {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

        # Declare extension capabilities for dynamic inter-extension relationships
        declare_extension_capabilities("StoreExtension", {
            "provides": {
                "components": {
                    "product_selector": {
                        "description": "Product selection component for embedding products in content",
                        "props": ["multiple", "selectedProducts", "language"],
                        "events": ["product-selected", "products-selected"]
                    },
                    "product_card": {
                        "description": "Product display card component for showing product information",
                        "props": ["product", "currency"],
                        "events": ["add-to-cart"]
                    }
                },
                "apis": {
                    "get_products": {
                        "description": "Get products with filtering and pagination",
                        "parameters": ["category", "search", "limit", "offset", "language"]
                    },
                    "get_product": {
                        "description": "Get single product by ID",
                        "parameters": ["product_id", "language"]
                    },
                    "create_product": {
                        "description": "Create a new product",
                        "parameters": ["name", "price", "description", "sku", "categories", "images"]
                    },
                    "get_categories": {
                        "description": "Get product categories",
                        "parameters": ["language"]
                    },
                    "get_cart": {
                        "description": "Get shopping cart contents",
                        "parameters": ["session_id", "language"]
                    },
                    "add_to_cart": {
                        "description": "Add item to shopping cart",
                        "parameters": ["item", "session_id"]
                    }
                }
            },
            "consumes": {
                # StoreExtension doesn't consume other extensions in this example
            }
        })

        # Register extension context and APIs for inter-extension communication
        dependency_manager = get_extension_dependency_manager()
        dependency_manager.register_extension_context(context.extension_id, context)

        # Register APIs that other extensions can call
        dependency_manager.register_api(context.extension_id, "get_products", get_products)
        dependency_manager.register_api(context.extension_id, "get_product", get_product)
        dependency_manager.register_api(context.extension_id, "create_product", create_product)
        dependency_manager.register_api(context.extension_id, "get_categories", get_categories)
        dependency_manager.register_api(context.extension_id, "get_cart", get_cart)
        dependency_manager.register_api(context.extension_id, "add_to_cart", add_to_cart)

        # Product HTML formatting API for embedding in content
        @router.post("/format_product_html")
        def format_product_html(
            products: str = Form(...),
            language: Optional[str] = Form(None),
            currency: Optional[str] = Form(None)
        ):
            """Format products as HTML for embedding in content (e.g., pages)"""
            try:
                current_language = language or "en"

                # Currency code priority:
                # 1) explicit request param
                # 2) StoreExtension settings
                # 3) USD fallback
                currency_code = (currency or "").strip() or None

                settings_data: Dict[str, Any] = {}
                currency_formats: Dict[str, Any] = {}
                try:
                    settings_result = execute_main_db_query(f"""
                        SELECT settings_data FROM "{settings_table}"
                        WHERE extension_id = :extension_id
                    """, {"extension_id": extension_db_id})

                    if settings_result and settings_result[0].get("settings_data"):
                        settings_raw = settings_result[0]["settings_data"]
                        if isinstance(settings_raw, dict):
                            settings_data = settings_raw
                        else:
                            settings_data = json.loads(settings_raw)
                        if not currency_code:
                            currency_code = (settings_data.get("currency") or "").strip() or None
                        cf = settings_data.get("currencies")
                        if isinstance(cf, dict):
                            currency_formats = cf
                except Exception as e:
                    print(f"Warning: Failed to load store settings for currency formatting: {e}")

                currency_code = currency_code or "USD"

                def format_currency(amount: Any, code: str) -> str:
                    default_symbols: Dict[str, str] = {
                        "USD": "$",
                        "EUR": "€",
                        "GBP": "£",
                        "BGN": "лв",
                        "JPY": "¥",
                        "CAD": "C$",
                        "AUD": "A$"
                    }

                    # Normalize amount to string without trailing .0 when possible
                    try:
                        num = float(amount)
                        amount_str = ("%g" % num)
                    except Exception:
                        amount_str = str(amount)

                    fmt = currency_formats.get(code) if isinstance(currency_formats, dict) else None
                    if isinstance(fmt, dict):
                        label = str(fmt.get("label") or default_symbols.get(code, code) or "").strip()
                        position = (fmt.get("position") or "prefix").strip().lower()
                        if position == "suffix":
                            return f"{amount_str} {label}".strip()
                        return f"{label}{amount_str}".strip()

                    # Fallback behavior
                    symbol = default_symbols.get(code, default_symbols.get("USD", "$"))
                    if code == "BGN":
                        return f"{amount_str} {symbol}"
                    return f"{symbol}{amount_str}"
                # Parse products from JSON string
                products_data = json.loads(products)
                formatted_products = []

                for product in products_data:
                    # Get product details with translations if needed
                    product_id = product.get("id")
                    if product_id and current_language != "en":
                        # Get translated product data
                        translation_query = f"""
                            SELECT translation_data FROM "{translations_table}"
                            WHERE record_id = :record_id
                            AND language_code = :language_code
                        """
                        translation_result = execute_main_db_query(translation_query, {
                            "record_id": product_id,
                            "language_code": current_language
                        })

                        if translation_result and translation_result[0]["translation_data"]:
                            try:
                                # SQLAlchemy automatically parses JSONB fields, so check if it's already a dict
                                translation_raw = translation_result[0]["translation_data"]
                                if isinstance(translation_raw, dict):
                                    translation_data = translation_raw
                                else:
                                    translation_data = json.loads(translation_raw)
                                # Merge translation with base product
                                translated_product = product.copy()
                                translated_product.update(translation_data)
                                product = translated_product
                            except Exception as e:
                                print(f"Error parsing product translation: {e}")

                    # Format product as HTML
                    image_html = ""
                    if product.get("images"):
                        try:
                            images = product["images"]
                            if isinstance(images, str):
                                images = json.loads(images)
                            if images and len(images) > 0:
                                image_url = images[0] if isinstance(images[0], str) else images[0].get("url", "")
                                if image_url:
                                    if not image_url.startswith(('http://', 'https://')):
                                        # Ensure we don't add /uploads/store/ if it's already there
                                        if image_url.startswith('/uploads/store/'):
                                            image_url = image_url  # Already has the correct path
                                        else:
                                            image_url = f"/uploads/store/{image_url}"
                                    image_html = f'<img src="{image_url}" alt="{product.get("name", "")}" style="max-width: 100%; height: auto; margin-bottom: 0.5rem;" />'
                        except Exception as e:
                            print(f"Error processing product images: {e}")

                    name = product.get("name", "")
                    price = product.get("price", "0")
                    sale_price = product.get("sale_price")
                    display_price = sale_price or price
                    formatted_price = format_currency(display_price, currency_code)
                    sku = product.get("sku", "")
                    description = product.get("description", "")

                    # Create HTML structure
                    # Include stable identifiers in data-* attributes so PageView can resolve
                    # the real product deterministically (no name/SKU matching required).
                    product_html = f"""
<div class="embedded-product" data-product-id="{product_id}" data-product-sku="{sku}" style="border: 1px solid #e3e3e3; border-radius: 8px; padding: 1rem; margin: 1rem 0; background: #f8f9fa;">
  {image_html}
  <h3 style="margin: 0 0 0.5rem 0; color: #222;">{name}</h3>
  <p style="margin: 0 0 0.5rem 0; font-weight: 600; color: #007bff;">{formatted_price}</p>
  {f'<p style="margin: 0; font-size: 0.875rem; color: #666;">SKU: {sku}</p>' if sku else ''}
  <p style="margin: 0.5rem 0 0 0; color: #666;">{description}</p>
</div>
                    """.strip()

                    formatted_products.append(product_html)

                return {"html": "\n".join(formatted_products)}
            except Exception as e:
                print(f"Error formatting product HTML: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to format product HTML: {str(e)}")

        # UI translations API for extensions that use store functionality
        @router.get("/get_ui_translations")
        def get_ui_translations(language: Optional[str] = None):
            """Get UI translation strings for store-related functionality"""
            current_language = language or "en"

            # IMPORTANT: UI translations must NOT share the same record_id with store settings translations.
            # Store settings translations use record_id=0. Use a dedicated negative record id for UI strings.
            UI_TRANSLATIONS_RECORD_ID = -1

            # Base English translations
            translations = {
                "productSelector": {
                    "title": "Select Products",
                    "searchPlaceholder": "Search products...",
                    "allCategories": "All Categories",
                    "loading": "Loading products...",
                    "noProducts": "No products found",
                    "selectedProducts": "Selected Products",
                    "clearAll": "Clear All",
                    "addSelected": "Add Selected",
                    "selectProduct": "Select Product"
                },
                "toolbar": {
                    "insertProduct": "Insert Product"
                }
            }

            # Apply translations if available
            if current_language != "en":
                print(f"DEBUG: Looking for UI translations for language: {current_language}")
                translation_query = f"""
                    SELECT translation_data FROM "{translations_table}"
                    WHERE record_id = :record_id
                    AND language_code = :language_code
                """
                translation_result = execute_main_db_query(translation_query, {
                    "record_id": UI_TRANSLATIONS_RECORD_ID,
                    "language_code": current_language
                })

                print(f"DEBUG: Translation query result: {translation_result}")

                if translation_result and len(translation_result) > 0 and translation_result[0]["translation_data"]:
                    try:
                        # SQLAlchemy automatically parses JSONB fields, so check if it's already a dict
                        translation_raw = translation_result[0]["translation_data"]
                        if isinstance(translation_raw, dict):
                            ui_translations = translation_raw
                        else:
                            ui_translations = json.loads(translation_raw)
                        print(f"DEBUG: Loaded UI translations: {ui_translations}")
                        # Merge with base translations
                        translations = ui_translations
                    except Exception as e:
                        print(f"Error parsing UI translations: {e}")
                else:
                    print(f"DEBUG: No UI translations found for {current_language}")
                    # For debugging, let's also check what translations exist in the table
                    all_translations = execute_main_db_query(f"""
                        SELECT record_id, language_code, translation_data FROM "{translations_table}"
                        WHERE language_code = :language_code
                    """, {"language_code": current_language})
                    print(f"DEBUG: All translations for {current_language}: {all_translations}")

            return translations

        @router.post("/ui_translations")
        def add_ui_translations(data: Dict[str, Any]):
            """Add UI translations for store-related functionality"""
            try:
                language_code = data.get("language_code")
                translations = data.get("translations", {})

                if not language_code:
                    raise HTTPException(status_code=400, detail="language_code is required")

                if not translations or not isinstance(translations, dict):
                    raise HTTPException(status_code=400, detail="translations must be a non-empty object")

                # Use a dedicated record id for UI translations to avoid collision with store settings (record_id=0)
                ui_record_id = -1

                # Insert or update translation
                translation_data = json.dumps(translations)

                # Check if translation already exists
                existing = execute_main_db_query(f"""
                    SELECT id FROM "{translations_table}"
                    WHERE record_id = :record_id
                    AND language_code = :language_code
                """, {
                    "record_id": ui_record_id,
                    "language_code": language_code
                })

                if existing:
                    # Update existing translation
                    execute_main_db_query(f"""
                        UPDATE "{translations_table}"
                        SET translation_data = :translation_data,
                            translation_coverage = :coverage,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE record_id = :record_id
                        AND language_code = :language_code
                    """, {
                        "translation_data": translation_data,
                        "coverage": len(translations) / 1 * 100,  # UI translations coverage
                        "record_id": ui_record_id,
                        "language_code": language_code
                    })
                else:
                    # Insert new translation
                    execute_main_db_query(f"""
                        INSERT INTO "{translations_table}"
                        (record_id, language_code, translation_data, translation_coverage)
                        VALUES (:record_id, :language_code, :translation_data, :coverage)
                    """, {
                        "record_id": ui_record_id,
                        "language_code": language_code,
                        "translation_data": translation_data,
                        "coverage": len(translations) / 1 * 100
                    })

                return {"message": f"UI translations added for {language_code}"}
            except Exception as e:
                print(f"Error adding UI translations: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to add UI translations: {str(e)}")

        # Dynamically register APIs based on declared capabilities
        api_functions = {
            "get_products": get_products,
            "get_product": get_product,
            "create_product": create_product,
            "get_categories": get_categories,
            "get_cart": get_cart,
            "add_to_cart": add_to_cart,
            "format_product_html": format_product_html,
            "get_ui_translations": get_ui_translations
        }
        register_extension_resources("StoreExtension", api_functions)

        context.register_router(router)

        return {
            "routes_registered": 29,  # Added 4 settings endpoints + 5 review endpoints + 3 images endpoints (list, create folder, move image)
            "tables_created": 9,  # Added ext_storeextension_reviews table
            "status": "initialized"
        }

    except Exception as e:
        print(f"Store extension initialization error: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}

def cleanup_extension(context):
    """Cleanup when extension is disabled"""
    try:
        # Get the extension database ID from name/version
        extension_name, extension_version = context.extension_id.rsplit('_', 1)
        extension_result = execute_main_db_query("""
            SELECT id FROM extensions
            WHERE name = :name AND version = :version
        """, {"name": extension_name, "version": extension_version})

        if extension_result:
            extension_db_id = extension_result[0]["id"]

            # Migrate existing translations from global table to extension-specific table
            # This ensures data continuity when switching table structures
            try:
                # Check if there are translations in the global table for this extension
                existing_translations = execute_main_db_query("""
                    SELECT record_id, language_code, translation_data, translation_coverage
                    FROM table_translations
                    WHERE extension_id = :extension_id
                    AND table_name = :table_name
                """, {
                    "extension_id": extension_db_id,
                    "table_name": "ext_storeextension_products"
                })

                if existing_translations:
                    # Insert into extension-specific table
                    translations_table = "ext_storeextension_translations"
                    for translation in existing_translations:
                        try:
                            execute_main_db_query(f"""
                                INSERT INTO "{translations_table}"
                                (record_id, language_code, translation_data, translation_coverage)
                                VALUES (:record_id, :language_code, :translation_data, :coverage)
                                ON CONFLICT (record_id, language_code) DO UPDATE SET
                                    translation_data = EXCLUDED.translation_data,
                                    translation_coverage = EXCLUDED.translation_coverage,
                                    updated_at = CURRENT_TIMESTAMP
                            """, {
                                "record_id": translation["record_id"],
                                "language_code": translation["language_code"],
                                "translation_data": translation["translation_data"],
                                "coverage": translation["translation_coverage"]
                            })
                        except Exception as e:
                            print(f"Warning: Failed to migrate translation for record {translation['record_id']}: {e}")

                    # Remove migrated translations from global table
                    execute_main_db_query("""
                        DELETE FROM table_translations
                        WHERE extension_id = :extension_id
                        AND table_name = :table_name
                    """, {
                        "extension_id": extension_db_id,
                        "table_name": "ext_storeextension_products"
                    })

            except Exception as e:
                print(f"Warning: Translation migration failed: {e}")
                # Don't fail the entire cleanup for migration issues

        # Note: We don't drop tables as they might contain user data
        # The extension can be safely disabled while preserving data
        return {"status": "cleaned_up"}
    except Exception as e:
        print(f"Store extension cleanup error: {e}")
        return {"status": "cleanup_error", "error": str(e)}
