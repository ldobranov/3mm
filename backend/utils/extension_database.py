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
            if extension_id in self.extension_engines:
                engine = self.extension_engines[extension_id]
                metadata = MetaData()

                # Get all tables with the extension prefix
                metadata.reflect(bind=engine)
                tables_to_drop = [
                    table for table_name, table in metadata.tables.items()
                    if table_name.startswith(f"ext_{extension_id}_")
                ]

                for table in tables_to_drop:
                    table.drop(engine)

                # Clean up
                del self.extension_sessions[extension_id]
                del self.extension_engines[extension_id]

                print(f"Dropped database schema for extension {extension_id}")
                return True
            return False

        except Exception as e:
            print(f"Error dropping database for extension {extension_id}: {e}")
            return False

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


# Global instance
extension_db_manager = ExtensionDatabaseManager("sqlite:///./mega_monitor.db")  # Should be configurable