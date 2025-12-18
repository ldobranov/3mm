"""
Extension Table Creator - Dynamic schema migration system for extensions
"""

import json
import re
from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from backend.utils.universal_translation_engine import ExtensionTableRegistry, UniversalTranslationEngine


class ExtensionTableCreator:
    """Create tables dynamically for extensions"""
    
    def __init__(self, db_session: AsyncSession, translation_engine: UniversalTranslationEngine):
        self.db_session = db_session
        self.translation_engine = translation_engine
        self.table_registry = ExtensionTableRegistry(db_session)
    
    async def create_extension_tables(self, extension_id: int, table_definitions: List[Dict[str, Any]]):
        """Create all tables for an extension"""
        
        created_tables = []
        
        for table_def in table_definitions:
            try:
                await self.create_single_table(extension_id, table_def)
                created_tables.append(table_def["name"])
                
                # Register tables in translation system
                await self.translation_engine.table_registry.register_table(
                    extension_id, table_def["name"], table_def["fields"], 
                    self._extract_translatable_fields(table_def["fields"]),
                    table_def.get("primary_key", "id")
                )
                
                # Register individual fields
                for field_name, field_config in table_def["fields"].items():
                    await self.table_registry.register_field(
                        extension_id=extension_id,
                        table_name=table_def["name"],
                        field_name=field_name,
                        field_type=field_config.get("type", "text"),
                        is_translatable=field_config.get("multilingual", False),
                        validation_rules=field_config.get("validation", {}),
                        field_order=field_config.get("order", 0)
                    )
                
            except Exception as e:
                # Rollback any tables created so far
                await self._rollback_tables(created_tables)
                raise Exception(f"Failed to create table {table_def['name']}: {str(e)}")
        
        return created_tables
    
    async def create_single_table(self, extension_id: int, table_def: Dict[str, Any]):
        """Create a single table with proper structure"""
        
        table_name = table_def["name"]
        primary_key = table_def.get("primary_key", "id")
        
        # Build CREATE TABLE statement
        columns = []
        constraints = []
        indexes = []
        
        for field_name, field_config in table_def["fields"].items():
            column_def = self._build_column_definition(field_name, field_config)
            columns.append(column_def)
        
        # Add primary key constraint
        if primary_key != "id":
            constraints.append(f"PRIMARY KEY ({primary_key})")
        
        # Add foreign key constraints
        for field_name, field_config in table_def["fields"].items():
            if field_config.get("foreign_key"):
                fk_table, fk_field = field_config["foreign_key"].split(".")
                constraints.append(
                    f"FOREIGN KEY ({field_name}) REFERENCES {fk_table}({fk_field})"
                )
        
        # Add unique constraints
        for unique_constraint in table_def.get("unique_constraints", []):
            if isinstance(unique_constraint, str):
                constraints.append(f"UNIQUE ({unique_constraint})")
            else:
                constraints.append(f"UNIQUE ({', '.join(unique_constraint)})")
        
        # Build complete SQL
        create_sql = f"""
        CREATE TABLE {table_name} (
            {", ".join(columns + constraints)}
        )
        """
        
        # Execute table creation
        try:
            await self.db_session.execute(text(create_sql))
            await self.db_session.commit()
        except SQLAlchemyError as e:
            await self.db_session.rollback()
            raise Exception(f"Failed to create table {table_name}: {str(e)}")
        
        # Create indexes
        for index_def in table_def.get("indexes", []):
            await self._create_index(table_name, index_def)
        
        # Create triggers if specified
        for trigger_def in table_def.get("triggers", []):
            await self._create_trigger(table_name, trigger_def)
    
    def _build_column_definition(self, field_name: str, field_config: Dict[str, Any]) -> str:
        """Build SQL column definition"""
        
        field_type = field_config["type"]
        
        # Map field types to SQL types
        type_mapping = {
            "serial": "SERIAL",
            "integer": "INTEGER", 
            "bigint": "BIGINT",
            "varchar": f"VARCHAR({field_config.get('length', 255)})",
            "text": "TEXT",
            "boolean": "BOOLEAN",
            "decimal": f"DECIMAL({field_config.get('precision', 10)}, {field_config.get('scale', 2)})",
            "json": "JSONB",
            "jsonb": "JSONB",
            "datetime": "TIMESTAMP",
            "date": "DATE",
            "time": "TIME",
            "uuid": "UUID",
            "array": f"{field_config.get('array_type', 'TEXT')}[]",
            "point": "POINT",
            "inet": "INET"
        }
        
        column_def = f"{field_name} {type_mapping.get(field_type, 'TEXT')}"
        
        # Add constraints
        if field_config.get("required", False):
            column_def += " NOT NULL"
        
        if field_config.get("unique", False):
            column_def += " UNIQUE"
        
        if field_config.get("primary_key", False):
            column_def += " PRIMARY KEY"
        
        # Add default values
        if field_config.get("default") is not None:
            default_value = field_config["default"]
            if isinstance(default_value, str) and field_type in ["varchar", "text"]:
                column_def += f" DEFAULT '{default_value}'"
            elif isinstance(default_value, (int, float)):
                column_def += f" DEFAULT {default_value}"
            elif isinstance(default_value, bool):
                column_def += f" DEFAULT {str(default_value).upper()}"
            elif isinstance(default_value, dict) and "function" in default_value:
                column_def += f" DEFAULT {default_value['function']}"
        
        # Add check constraints
        if field_config.get("check_constraint"):
            column_def += f" CHECK ({field_config['check_constraint']})"
        
        # Add comments
        if field_config.get("comment"):
            comment = field_config["comment"].replace("'", "''")  # Escape single quotes
            column_def += f" COMMENT '{comment}'"
        
        return column_def
    
    async def _create_index(self, table_name: str, index_def: Dict[str, Any]):
        """Create index for table"""
        
        if isinstance(index_def, str):
            index_name = f"idx_{table_name}_{index_def}"
            index_sql = f"CREATE INDEX {index_name} ON {table_name} ({index_def})"
        else:
            index_name = f"idx_{table_name}_{index_def['name']}"
            columns = ", ".join(index_def["columns"])
            index_sql = f"CREATE INDEX {index_name} ON {table_name} ({columns})"
        
        try:
            await self.db_session.execute(text(index_sql))
            await self.db_session.commit()
        except SQLAlchemyError as e:
            await self.db_session.rollback()
            print(f"Warning: Failed to create index {index_name}: {str(e)}")
    
    async def _create_trigger(self, table_name: str, trigger_def: Dict[str, Any]):
        """Create database trigger"""
        
        trigger_name = f"trg_{table_name}_{trigger_def['name']}"
        
        # Build trigger SQL based on type
        if trigger_def["type"] == "updated_at":
            trigger_sql = f"""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.updated_at = NOW();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            
            CREATE TRIGGER {trigger_name}
            BEFORE UPDATE ON {table_name}
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
            """
        
        await self.db_session.execute(text(trigger_sql))
        await self.db_session.commit()
    
    def _extract_translatable_fields(self, fields: Dict[str, Any]) -> List[str]:
        """Extract list of translatable fields from field definitions"""
        return [
            field_name for field_name, field_config in fields.items()
            if field_config.get("multilingual", False)
        ]
    
    async def _rollback_tables(self, table_names: List[str]):
        """Rollback created tables in case of error"""
        for table_name in table_names:
            try:
                await self.db_session.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
                await self.db_session.commit()
            except Exception as e:
                print(f"Warning: Failed to rollback table {table_name}: {str(e)}")


# E-commerce Extension Example Implementation
class ECommerceExtensionTableCreator(ExtensionTableCreator):
    """Specialized table creator for e-commerce extensions"""
    
    async def create_ecommerce_tables(self, extension_id: int):
        """Create standard e-commerce extension tables"""
        
        ecommerce_tables = [
            {
                "name": "store_products",
                "primary_key": "product_id",
                "fields": {
                    "product_id": {"type": "serial", "primary_key": True},
                    "sku": {"type": "varchar", "length": 50, "required": True, "unique": True},
                    "barcode": {"type": "varchar", "length": 50},
                    "price": {"type": "decimal", "precision": 10, "scale": 2, "required": True},
                    "cost_price": {"type": "decimal", "precision": 10, "scale": 2},
                    "compare_at_price": {"type": "decimal", "precision": 10, "scale": 2},
                    "weight": {"type": "decimal", "precision": 8, "scale": 3},
                    "stock_quantity": {"type": "integer", "default": 0},
                    "track_quantity": {"type": "boolean", "default": True},
                    "requires_shipping": {"type": "boolean", "default": True},
                    "is_digital": {"type": "boolean", "default": False},
                    "seo_title": {"type": "varchar", "length": 255},
                    "seo_description": {"type": "text"},
                    "tags": {"type": "text"},  # Comma-separated tags
                    "status": {"type": "varchar", "length": 20, "default": "draft"},
                    "product_type": {"type": "varchar", "length": 100},
                    "vendor": {"type": "varchar", "length": 100},
                    "handle": {"type": "varchar", "length": 255, "unique": True},
                    "created_at": {"type": "datetime", "default": {"function": "NOW()"}},
                    "updated_at": {"type": "datetime", "default": {"function": "NOW()"}},
                    "published_at": {"type": "datetime"}
                },
                "indexes": ["sku", "status", "product_type", "vendor"],
                "unique_constraints": ["handle"],
                "triggers": [{"name": "updated_at", "type": "updated_at"}]
            },
            {
                "name": "store_product_translations",
                "primary_key": "translation_id",
                "fields": {
                    "translation_id": {"type": "serial", "primary_key": True},
                    "product_id": {"type": "integer", "required": True, "foreign_key": "store_products.product_id"},
                    "language_code": {"type": "varchar", "length": 10, "required": True},
                    "name": {"type": "varchar", "length": 255, "multilingual": True, "required": True},
                    "description": {"type": "text", "multilingual": True},
                    "short_description": {"type": "text", "multilingual": True},
                    "meta_title": {"type": "varchar", "length": 255, "multilingual": True},
                    "meta_description": {"type": "text", "multilingual": True},
                    "created_at": {"type": "datetime", "default": {"function": "NOW()"}},
                    "updated_at": {"type": "datetime", "default": {"function": "NOW()"}}
                },
                "indexes": ["product_id", "language_code"],
                "unique_constraints": ["product_id, language_code"],
                "triggers": [{"name": "updated_at", "type": "updated_at"}]
            },
            {
                "name": "store_categories",
                "primary_key": "category_id",
                "fields": {
                    "category_id": {"type": "serial", "primary_key": True},
                    "parent_id": {"type": "integer", "foreign_key": "store_categories.category_id"},
                    "handle": {"type": "varchar", "length": 255, "unique": True},
                    "sort_order": {"type": "integer", "default": 0},
                    "is_active": {"type": "boolean", "default": True},
                    "seo_title": {"type": "varchar", "length": 255},
                    "seo_description": {"type": "text"},
                    "image_id": {"type": "integer"},
                    "created_at": {"type": "datetime", "default": {"function": "NOW()"}},
                    "updated_at": {"type": "datetime", "default": {"function": "NOW()"}}
                },
                "indexes": ["parent_id", "sort_order", "is_active"],
                "triggers": [{"name": "updated_at", "type": "updated_at"}]
            },
            {
                "name": "store_category_translations",
                "primary_key": "translation_id", 
                "fields": {
                    "translation_id": {"type": "serial", "primary_key": True},
                    "category_id": {"type": "integer", "required": True, "foreign_key": "store_categories.category_id"},
                    "language_code": {"type": "varchar", "length": 10, "required": True},
                    "name": {"type": "varchar", "length": 255, "multilingual": True, "required": True},
                    "description": {"type": "text", "multilingual": True},
                    "meta_title": {"type": "varchar", "length": 255, "multilingual": True},
                    "meta_description": {"type": "text", "multilingual": True},
                    "created_at": {"type": "datetime", "default": {"function": "NOW()"}},
                    "updated_at": {"type": "datetime", "default": {"function": "NOW()"}}
                },
                "indexes": ["category_id", "language_code"],
                "unique_constraints": ["category_id, language_code"],
                "triggers": [{"name": "updated_at", "type": "updated_at"}]
            },
            {
                "name": "store_product_categories",
                "primary_key": "product_category_id",
                "fields": {
                    "product_category_id": {"type": "serial", "primary_key": True},
                    "product_id": {"type": "integer", "required": True, "foreign_key": "store_products.product_id"},
                    "category_id": {"type": "integer", "required": True, "foreign_key": "store_categories.category_id"},
                    "created_at": {"type": "datetime", "default": {"function": "NOW()"}}
                },
                "indexes": ["product_id", "category_id"],
                "unique_constraints": ["product_id, category_id"]
            }
        ]
        
        return await self.create_extension_tables(extension_id, ecommerce_tables)