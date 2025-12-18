"""
Extension Database Management - Handles extension-specific database schemas
"""

from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, DateTime, Text, Float, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.sql import text
from pathlib import Path
from typing import Dict, Any, List, Optional
import json

# Extension-specific base for models
ExtensionBase = declarative_base()

class ExtensionDatabaseManager:
    """Manages database operations for extensions"""

    def __init__(self, main_db_url: str):
        self.main_db_url = main_db_url
        self.extension_engines: Dict[str, Any] = {}
        self.extension_sessions: Dict[str, Any] = {}

    def create_extension_database(self, extension_id: str, schema_definition: Dict[str, Any]) -> bool:
        """Create database tables for an extension"""
        try:
            # For now, we'll use the main database with prefixed table names
            # In production, you might want separate databases per extension
            engine = create_engine(self.main_db_url)
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

            self.extension_engines[extension_id] = engine
            self.extension_sessions[extension_id] = SessionLocal

            # Create tables based on schema definition
            metadata = MetaData()

            for table_name, table_schema in schema_definition.get('tables', {}).items():
                prefixed_table_name = f"ext_{extension_id}_{table_name}"

                columns = []
                for col_name, col_def in table_schema.get('columns', {}).items():
                    col_type = col_def.get('type', 'string')
                    col_nullable = col_def.get('nullable', True)

                    # Map string types to SQLAlchemy types
                    if col_type == 'integer':
                        columns.append(Column(col_name, Integer, nullable=col_nullable))
                    elif col_type == 'float':
                        columns.append(Column(col_name, Float, nullable=col_nullable))
                    elif col_type == 'boolean':
                        columns.append(Column(col_name, Boolean, nullable=col_nullable))
                    elif col_type == 'datetime':
                        columns.append(Column(col_name, DateTime, nullable=col_nullable))
                    elif col_type == 'text':
                        columns.append(Column(col_name, Text, nullable=col_nullable))
                    else:  # default to string
                        columns.append(Column(col_name, String(255), nullable=col_nullable))

                # Add standard columns
                columns.insert(0, Column('id', Integer, primary_key=True, autoincrement=True))
                columns.append(Column('created_at', DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP')))
                # SQLite doesn't support ON UPDATE CURRENT_TIMESTAMP, so we'll handle updates in application code
                columns.append(Column('updated_at', DateTime, nullable=False, server_default=text('CURRENT_TIMESTAMP')))

                table = Table(prefixed_table_name, metadata, *columns)
                table.create(engine, checkfirst=True)

            print(f"Created database schema for extension {extension_id}")
            return True

        except Exception as e:
            print(f"Error creating database for extension {extension_id}: {e}")
            return False

    def drop_extension_database(self, extension_id: str) -> bool:
        """Drop all tables for an extension"""
        try:
            from sqlalchemy import text
            from backend.database import get_db
            
            # Always use SQL to safely find and drop extension tables
            # This avoids metadata reflection issues
            db = next(get_db())
            
            # First, let's see what extension tables exist
            # Use PostgreSQL-compatible query
            list_query = text("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public' AND tablename LIKE :prefix
            """)
            result = db.execute(list_query, {"prefix": f"ext_{extension_id}_%"})
            table_names = [row[0] for row in result.fetchall()]
            
            if not table_names:
                print(f"No extension tables found for {extension_id}")
                db.close()
                return True
            
            # Only drop extension-specific tables with strict validation
            dropped_count = 0
            main_tables = {'users', 'extensions', 'language_packs', 'roles', 'permissions', 'pages'}
            
            for table_name in table_names:
                try:
                    # Safety check: only drop tables that start with ext_ and don't interfere with main tables
                    if table_name.startswith(f"ext_{extension_id}_"):
                        # Additional safety: make sure it's not a main table
                        base_name = table_name.split('_')[-1] if '_' in table_name else table_name
                        
                        # Skip if it matches any main table names
                        if base_name in main_tables:
                            print(f"Skipping main table: {table_name}")
                            continue
                        
                        # Safe to drop
                        db.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
                        print(f"Dropped extension table: {table_name}")
                        dropped_count += 1
                        
                except Exception as drop_error:
                    print(f"Warning: Could not drop table {table_name}: {drop_error}")
                    continue
            
            db.commit()
            db.close()
            
            # Clean up managed references if they exist
            if extension_id in self.extension_sessions:
                del self.extension_sessions[extension_id]
            if extension_id in self.extension_engines:
                del self.extension_engines[extension_id]
            
            print(f"Extension database cleanup completed for {extension_id} ({dropped_count} tables dropped)")
            return True

        except Exception as e:
            print(f"Error dropping database for extension {extension_id}: {e}")
            # Return True anyway to prevent extension cleanup from failing completely
            return True

    def get_extension_session(self, extension_id: str):
        """Get a database session for an extension"""
        if extension_id in self.extension_sessions:
            return self.extension_sessions[extension_id]()
        return None

    def execute_extension_query(self, extension_id: str, query: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Execute a raw SQL query for an extension"""
        session = self.get_extension_session(extension_id)
        if not session:
            raise Exception(f"No database session available for extension {extension_id}")

        try:
            result = session.execute(text(query), params or {})
            if result.returns_rows:
                # Convert SQLAlchemy result rows to dictionaries safely
                rows = []
                for row in result.fetchall():
                    try:
                        # Handle different row types
                        if hasattr(row, '_mapping'):
                            rows.append(dict(row._mapping))
                        elif hasattr(row, 'items'):
                            rows.append(dict(row.items()))
                        else:
                            # Fallback for named tuples
                            rows.append({key: getattr(row, key) for key in row._fields})
                    except Exception as e:
                        print(f"Error converting row to dict: {e}")
                        rows.append({})
                return rows
            else:
                session.commit()
                return []
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def load_schema_from_file(self, schema_file: Path) -> Dict[str, Any]:
        """Load database schema definition from a file"""
        try:
            with open(schema_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading schema file {schema_file}: {e}")
            return {}

    def initialize_extension_database(self, extension_path: Path, extension_id: str) -> bool:
        """Initialize database for an extension based on its schema file"""
        schema_file = extension_path / "database_schema.json"
        if schema_file.exists():
            schema = self.load_schema_from_file(schema_file)
            return self.create_extension_database(extension_id, schema)
        else:
            # No schema file, create basic structure
            basic_schema = {
                "tables": {
                    "settings": {
                        "columns": {
                            "key": {"type": "string", "nullable": False},
                            "value": {"type": "text", "nullable": True}
                        }
                    }
                }
            }
            return self.create_extension_database(extension_id, basic_schema)


# Global instance - use the same database as the main application
import os
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://lazar:admin@localhost:5432/mega_monitor")
extension_db_manager = ExtensionDatabaseManager(DATABASE_URL)