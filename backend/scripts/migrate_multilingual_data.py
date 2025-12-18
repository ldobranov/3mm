"""
Migration Script for Universal Multilingual System
Transforms existing duplicated menu data into clean multilingual structure
"""

import json
import re
import asyncio
from typing import Dict, List, Tuple, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from datetime import datetime
from backend.db.universal_translation import ExtensionTable, TableTranslation, MigrationHistory, Menu
from backend.db.settings import Settings
from backend.utils.universal_translation_engine import UniversalTranslationEngine, ExtensionTableRegistry
from backend.utils.extension_table_creator import ExtensionTableCreator


class MultilingualMigrationManager:
    """Manage migration from duplicated to universal translation system"""
    
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.translation_engine = UniversalTranslationEngine(db_session)
        self.table_registry = ExtensionTableRegistry(db_session)
        self.table_creator = ExtensionTableCreator(db_session, self.translation_engine)
    
    async def run_full_migration(self):
        """Run complete migration from old to new system"""
        
        try:
            # Step 1: Create new database schema
            await self._create_new_schema()
            
            # Step 2: Migrate menu data (solves user's main problem)
            menu_result = await self._migrate_menu_data()
            
            # Step 3: Migrate settings data
            settings_result = await self._migrate_settings_data()
            
            # Step 4: Register system tables
            await self._register_system_tables()
            
            return {
                "status": "completed",
                "menus_migrated": menu_result["count"],
                "settings_migrated": settings_result["count"],
                "errors": []
            }
            
        except Exception as e:
            await self._log_migration_error("full_migration", str(e))
            raise Exception(f"Migration failed: {str(e)}")
    
    async def _create_new_schema(self):
        """Create new schema for universal translation system"""
        
        # Note: In production, these would be proper Alembic migrations
        # For now, we create the tables directly
        
        # Create extension_tables table (if not exists)
        await self.db_session.execute(text("""
            CREATE TABLE IF NOT EXISTS extension_tables (
                id SERIAL PRIMARY KEY,
                extension_id INTEGER NOT NULL,
                table_name VARCHAR(100) NOT NULL,
                table_schema JSON NOT NULL,
                translatable_fields JSON NOT NULL DEFAULT '[]',
                primary_key_field VARCHAR(100) NOT NULL DEFAULT 'id',
                is_multilingual BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                FOREIGN KEY (extension_id) REFERENCES extensions(id) ON DELETE CASCADE,
                UNIQUE(extension_id, table_name)
            )
        """))
        
        # Create table_translations table
        await self.db_session.execute(text("""
            CREATE TABLE IF NOT EXISTS table_translations (
                id SERIAL PRIMARY KEY,
                extension_id INTEGER NOT NULL,
                table_name VARCHAR(100) NOT NULL,
                record_id INTEGER NOT NULL,
                language_code VARCHAR(10) NOT NULL,
                translation_data JSON NOT NULL,
                translation_coverage NUMERIC(5,2) DEFAULT 0.0,
                is_fallback BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                FOREIGN KEY (extension_id) REFERENCES extensions(id) ON DELETE CASCADE,
                UNIQUE(extension_id, table_name, record_id, language_code)
            )
        """))
        
        # Create extension_fields table
        await self.db_session.execute(text("""
            CREATE TABLE IF NOT EXISTS extension_fields (
                id SERIAL PRIMARY KEY,
                extension_id INTEGER NOT NULL,
                table_name VARCHAR(100) NOT NULL,
                field_name VARCHAR(100) NOT NULL,
                field_type VARCHAR(50) NOT NULL,
                is_translatable BOOLEAN DEFAULT FALSE,
                validation_rules JSON DEFAULT '{}',
                field_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                FOREIGN KEY (extension_id) REFERENCES extensions(id) ON DELETE CASCADE,
                UNIQUE(extension_id, table_name, field_name)
            )
        """))
        
        # Create migration_history table
        await self.db_session.execute(text("""
            CREATE TABLE IF NOT EXISTS migration_history (
                id SERIAL PRIMARY KEY,
                migration_type VARCHAR(50) NOT NULL,
                status VARCHAR(20) NOT NULL,
                records_processed INTEGER DEFAULT 0,
                total_records INTEGER DEFAULT 0,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP
            )
        """))
        
        # Add columns to existing menus table
        await self.db_session.execute(text("""
            ALTER TABLE menus 
            ADD COLUMN IF NOT EXISTS structure JSON,
            ADD COLUMN IF NOT EXISTS default_language VARCHAR(10) DEFAULT 'en',
            ADD COLUMN IF NOT EXISTS has_translations BOOLEAN DEFAULT FALSE
        """))
        
        # Add columns to existing settings table
        await self.db_session.execute(text("""
            ALTER TABLE settings 
            ADD COLUMN IF NOT EXISTS is_translatable BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS content_type VARCHAR(50) DEFAULT 'setting'
        """))
        
        # Create setting_translations table
        await self.db_session.execute(text("""
            CREATE TABLE IF NOT EXISTS setting_translations (
                id SERIAL PRIMARY KEY,
                setting_id INTEGER NOT NULL REFERENCES settings(id) ON DELETE CASCADE,
                language_code VARCHAR(10) NOT NULL,
                translated_value TEXT,
                translated_description TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(setting_id, language_code)
            )
        """))
        
        await self.db_session.commit()
    
    async def _migrate_menu_data(self) -> Dict[str, Any]:
        """Migrate existing menu configuration data (main user problem)"""
        
        print("🔄 Starting menu data migration...")
        
        try:
            # Find all menu configuration entries
            menu_settings = await self.db_session.execute(
                select(Settings).where(Settings.key.like('menu_config_%'))
            )
            menu_settings = menu_settings.scalars().all()
            
            if not menu_settings:
                print("ℹ️  No menu configuration entries found")
                return {"count": 0, "errors": []}
            
            # Group by base key (remove language suffix)
            menu_groups = self._group_menu_settings(menu_settings)
            
            migrated_count = 0
            errors = []
            
            # Process each menu group
            for base_key, language_versions in menu_groups.items():
                try:
                    await self._migrate_single_menu(base_key, language_versions)
                    migrated_count += 1
                    print(f"✅ Migrated menu: {base_key}")
                except Exception as e:
                    error_msg = f"Failed to migrate menu {base_key}: {str(e)}"
                    errors.append(error_msg)
                    print(f"❌ {error_msg}")
            
            # Log migration
            await self._log_migration_progress("menu_data", migrated_count, len(menu_groups), errors)
            
            print(f"🎉 Menu migration completed: {migrated_count} menus migrated")
            return {"count": migrated_count, "errors": errors}
            
        except Exception as e:
            await self._log_migration_error("menu_data", str(e))
            raise e
    
    def _group_menu_settings(self, menu_settings: List[Settings]) -> Dict[str, Dict[str, str]]:
        """Group menu settings by base key (remove language suffixes)"""
        
        menu_groups = {}
        
        for setting in menu_settings:
            # Extract base key and language code
            match = re.match(r'(.+?)_([a-z]{2})$', setting.key)
            
            if match:
                base_key = match.group(1)
                lang_code = match.group(2)
            else:
                # No language suffix, assume default language
                base_key = setting.key
                lang_code = 'en'
            
            if base_key not in menu_groups:
                menu_groups[base_key] = {}
            
            menu_groups[base_key][lang_code] = setting.value
        
        return menu_groups
    
    async def _migrate_single_menu(self, base_key: str, language_versions: Dict[str, str]):
        """Migrate a single menu from old format to new structure"""
        
        # Determine default language
        default_lang = 'en' if 'en' in language_versions else list(language_versions.keys())[0]
        default_menu_data = json.loads(language_versions[default_lang])
        
        # Create language-agnostic structure
        clean_structure = {
            "id": default_menu_data.get("id", 1),
            "name": default_menu_data.get("name", "Main Menu"),
            "config": {
                "position": "top",
                "style": "horizontal",
                "source": "migrated"
            },
            "items": []
        }
        
        # Extract translatable fields from items
        for item in default_menu_data.get("items", []):
            translatable_fields = []
            
            # Find multilingual fields in the item
            for field_key, field_value in item.items():
                if isinstance(field_value, dict) and len(field_value) > 1:
                    # This is a multilingual field
                    translatable_fields.append(field_key)
            
            # Build clean item structure
            clean_item = {
                "id": item.get("id", f"item_{len(clean_structure['items']) + 1}"),
                "path": item.get("path", ""),
                "icon": item.get("icon", ""),
                "order": len(clean_structure['items']) + 1,
                "translatable_fields": translatable_fields
            }
            
            # Add non-translatable fields
            for field_key, field_value in item.items():
                if field_key not in translatable_fields:
                    clean_item[field_key] = field_value
            
            clean_structure["items"].append(clean_item)
        
        # Insert or update menu record
        menu_result = await self.db_session.execute(
            select(Menu).where(Menu.id == clean_structure["id"])
        )
        existing_menu = menu_result.scalar_one_or_none()
        
        if existing_menu:
            # Update existing menu
            existing_menu.structure = clean_structure
            existing_menu.default_language = default_lang
            existing_menu.has_translations = len(language_versions) > 1
        else:
            # Create new menu record
            new_menu = Menu(
                id=clean_structure["id"],
                name=clean_structure["name"],
                structure=clean_structure,
                default_language=default_lang,
                has_translations=len(language_versions) > 1,
                is_active=True
            )
            self.db_session.add(new_menu)
        
        await self.db_session.commit()
        
        # Register menu table for translations
        await self.table_registry.register_table(
            extension_id=1,  # System extension
            table_name="menus",
            schema={"type": "menu", "structure": clean_structure},
            translatable_fields=self._extract_menu_translatable_fields(clean_structure["items"]),
            primary_key="id",
            is_multilingual=True
        )
        
        # Create translations for each language
        for lang_code, menu_json_str in language_versions.items():
            menu_data = json.loads(menu_json_str)
            
            # Build translation data (just the parts that change per language)
            translation_data = {}
            
            for item in menu_data.get("items", []):
                item_id = item.get("id")
                
                for field_name in self._extract_menu_translatable_fields([item]):
                    if field_name in item and isinstance(item[field_name], dict) and lang_code in item[field_name]:
                        translation_data[f"{item_id}_{field_name}"] = item[field_name][lang_code]
            
            if translation_data:
                await self.translation_engine.update_translations(
                    extension_id=1,  # System extension
                    table_name="menus",
                    record_id=clean_structure["id"],
                    language_code=lang_code,
                    translations=translation_data
                )
    
    def _extract_menu_translatable_fields(self, items: List[Dict]) -> List[str]:
        """Extract translatable field names from menu items"""
        translatable_fields = set()
        
        for item in items:
            for field_name, field_value in item.items():
                if isinstance(field_value, dict) and len(field_value) > 1:
                    # This field contains translations for multiple languages
                    translatable_fields.add(field_name)
        
        return list(translatable_fields)
    
    async def _migrate_settings_data(self) -> Dict[str, Any]:
        """Migrate settings data to new translation system"""
        
        print("🔄 Starting settings data migration...")
        
        try:
            # Find settings with language-specific keys
            settings_result = await self.db_session.execute(
                select(Settings).where(Settings.language_code.isnot(None))
            )
            settings_with_language = settings_result.scalars().all()
            
            if not settings_with_language:
                print("ℹ️  No language-specific settings found")
                return {"count": 0, "errors": []}
            
            # Group settings by base key (remove language suffix)
            setting_groups = {}
            
            for setting in settings_with_language:
                base_key = setting.key
                lang_code = setting.language_code
                
                if base_key not in setting_groups:
                    setting_groups[base_key] = {}
                
                setting_groups[base_key][lang_code] = setting
            
            migrated_count = 0
            errors = []
            
            # Process each setting group
            for base_key, language_versions in setting_groups.items():
                try:
                    await self._migrate_single_setting(base_key, language_versions)
                    migrated_count += 1
                except Exception as e:
                    error_msg = f"Failed to migrate setting {base_key}: {str(e)}"
                    errors.append(error_msg)
                    print(f"❌ {error_msg}")
            
            await self._log_migration_progress("settings_data", migrated_count, len(setting_groups), errors)
            
            print(f"🎉 Settings migration completed: {migrated_count} settings migrated")
            return {"count": migrated_count, "errors": errors}
            
        except Exception as e:
            await self._log_migration_error("settings_data", str(e))
            raise e
    
    async def _migrate_single_setting(self, base_key: str, language_versions: Dict[str, Settings]):
        """Migrate a single setting from old format to new structure"""
        
        # Use the first setting as base
        base_setting = list(language_versions.values())[0]
        
        # Update base setting to be translatable
        base_setting.is_translatable = True
        base_setting.language_code = None  # Remove language code from base
        
        # Create translations for other languages
        for lang_code, setting in language_versions.items():
            if lang_code != list(language_versions.keys())[0]:
                # Create translation record
                from backend.db.universal_translation import SettingTranslation
                
                translation = SettingTranslation(
                    setting_id=base_setting.id,
                    language_code=lang_code,
                    translated_value=setting.value,
                    translated_description=setting.description
                )
                self.db_session.add(translation)
                
                # Remove the old language-specific setting
                await self.db_session.delete(setting)
        
        await self.db_session.commit()
    
    async def _register_system_tables(self):
        """Register system tables in translation registry"""
        
        # Register menus table
        await self.table_registry.register_table(
            extension_id=1,  # System extension ID
            table_name="menus",
            schema={"type": "system", "name": "System Menus"},
            translatable_fields=["name", "items"],
            primary_key="id",
            is_multilingual=True
        )
        
        # Register settings table
        await self.table_registry.register_table(
            extension_id=1,  # System extension ID
            table_name="settings",
            schema={"type": "system", "name": "System Settings"},
            translatable_fields=["value", "description"],
            primary_key="id",
            is_multilingual=True
        )
        
        await self.db_session.commit()
    
    async def _log_migration_progress(self, migration_type: str, processed: int, total: int, errors: List[str]):
        """Log migration progress"""
        
        record = MigrationHistory(
            migration_type=migration_type,
            status="completed" if not errors else "completed_with_errors",
            records_processed=processed,
            total_records=total,
            error_message="; ".join(errors) if errors else None,
            completed_at=datetime.utcnow()
        )
        
        self.db_session.add(record)
        await self.db_session.commit()
    
    async def _log_migration_error(self, migration_type: str, error_message: str):
        """Log migration error"""
        
        record = MigrationHistory(
            migration_type=migration_type,
            status="failed",
            records_processed=0,
            total_records=0,
            error_message=error_message,
            completed_at=datetime.utcnow()
        )
        
        self.db_session.add(record)
        await self.db_session.commit()
    
    async def get_migration_status(self) -> Dict[str, Any]:
        """Get current migration status"""
        
        result = await self.db_session.execute(
            select(MigrationHistory).order_by(MigrationHistory.created_at.desc())
        )
        
        migrations = result.scalars().all()
        
        return {
            "migrations": [
                {
                    "type": m.migration_type,
                    "status": m.status,
                    "records_processed": m.records_processed,
                    "total_records": m.total_records,
                    "error_message": m.error_message,
                    "created_at": m.created_at.isoformat(),
                    "completed_at": m.completed_at.isoformat() if m.completed_at else None
                }
                for m in migrations
            ]
        }


# Migration script runner
async def run_migration():
    """Run the migration process"""
    
    from backend.utils.db_utils import get_db_session
    
    # Get database session
    async for db_session in get_db_session():
        try:
            migration_manager = MultilingualMigrationManager(db_session)
            result = await migration_manager.run_full_migration()
            
            print("\n🎉 Migration completed successfully!")
            print(f"Menus migrated: {result['menus_migrated']}")
            print(f"Settings migrated: {result['settings_migrated']}")
            
            if result['errors']:
                print(f"\n⚠️  Errors occurred during migration:")
                for error in result['errors']:
                    print(f"  - {error}")
            
            return result
            
        except Exception as e:
            print(f"\n❌ Migration failed: {str(e)}")
            raise
        finally:
            await db_session.close()


if __name__ == "__main__":
    # Run migration
    asyncio.run(run_migration())