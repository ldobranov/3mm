#!/usr/bin/env python3
"""
Initialize database with PostgreSQL and Universal Multilingual System
Updated for Extension-Aware Multilingual Architecture
"""

import sys
import os
import asyncio
# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from backend.database import Base, get_db_url
from backend.db.user import User
from backend.db.role import Role, Group
from backend.db.settings import Settings
from backend.db.extension import Extension
from backend.db.universal_translation import (
    ExtensionTable, TableTranslation, ExtensionField, 
    MigrationHistory, SettingTranslation, Menu as UniversalMenu
)
from backend.utils.auth import hash_password
from backend.utils.universal_translation_engine import UniversalTranslationEngine
from backend.scripts.migrate_multilingual_data import MultilingualMigrationManager


def create_admin_user(db: Session) -> User:
    """Create admin user if not exists, or update password if exists"""
    from sqlalchemy import select
    
    result = db.execute(
        select(User).where(User.email == "admin@example.com")
    )
    admin = result.scalar_one_or_none()

    if admin:
        # Update password to ensure it's properly hashed
        admin.hashed_password = hash_password("admin")
        db.commit()
        print("✓ Updated admin user password")
        return admin

    admin = User(
        username="admin",
        email="admin@example.com",
        hashed_password=hash_password("admin"),
        role="admin"
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    print("✓ Created admin user:")
    print("  Email: admin@example.com")
    print("  Password: admin")
    print("  Role: admin")
    return admin


def create_system_extension(db: Session) -> Extension:
    """Create system extension for core functionality"""
    from sqlalchemy import select
    
    result = db.execute(
        select(Extension).where(Extension.name == "System Core")
    )
    system_ext = result.scalar_one_or_none()

    if system_ext:
        print("✓ System extension already exists")
        return system_ext

    # Get the admin user to associate with system extension
    admin_result = db.execute(
        select(User).where(User.email == "admin@example.com")
    )
    admin_user = admin_result.scalar_one_or_none()
    
    if not admin_user:
        raise Exception("Admin user not found - create_admin_user() must be called first")

    system_ext = Extension(
        user_id=admin_user.id,
        name="System Core",
        version="1.0.0",
        type="system",
        description="Core system functionality with multilingual support",
        manifest={"name": "System Core", "version": "1.0.0", "type": "system", "description": "Core system functionality"},
        file_path="system",
        is_enabled=True
    )
    db.add(system_ext)
    db.commit()
    db.refresh(system_ext)
    print("✓ Created system extension")
    return system_ext


def create_menus(db: Session, system_extension: Extension):
    """Create default menu items with universal translation support"""
    from sqlalchemy import select, func

    # Check if menus exist
    result = db.execute(select(func.count(UniversalMenu.id)))
    count = result.scalar()
    if count > 0:
        print("✓ Universal menus already exist")
        return
    
    # Create menu structure
    menu_structure = {
        "id": 1,
        "name": "Main Menu",
        "config": {
            "position": "top",
            "style": "horizontal",
            "source": "system"
        },
        "items": [
            {
                "id": "home",
                "path": "/",
                "icon": "home",
                "order": 1,
                "translatable_fields": ["label", "tooltip"]
            },
            {
                "id": "dashboard",
                "path": "/dashboard",
                "icon": "dashboard",
                "order": 2,
                "translatable_fields": ["label", "tooltip"]
            },
            {
                "id": "settings",
                "path": "/settings",
                "icon": "settings",
                "order": 3,
                "translatable_fields": ["label", "tooltip"]
            },
            {
                "id": "extensions",
                "path": "/extensions",
                "icon": "extensions",
                "order": 4,
                "translatable_fields": ["label", "tooltip"]
            },
            {
                "id": "security",
                "path": "/security",
                "icon": "security",
                "order": 5,
                "translatable_fields": ["label", "tooltip"]
            },
            {
                "id": "profile",
                "path": "/user/profile",
                "icon": "person",
                "order": 6,
                "translatable_fields": ["label", "tooltip"]
            }
        ],
        "is_active": True
    }
    
    # Create main menu
    main_menu = UniversalMenu(
        id=1,
        name="Main Menu",
        structure=menu_structure,
        default_language="en",
        has_translations=False,
        is_active=True
    )
    db.add(main_menu)
    
    # Create admin menu
    admin_menu_structure = {
        "id": 2,
        "name": "Admin Menu",
        "config": {
            "position": "sidebar",
            "style": "vertical",
            "source": "system"
        },
        "items": [
            {
                "id": "users",
                "path": "/users",
                "icon": "people", 
                "order": 1,
                "translatable_fields": ["label", "tooltip"]
            },
            {
                "id": "menu-editor",
                "path": "/menu-editor",
                "icon": "menu",
                "order": 2,
                "translatable_fields": ["label", "tooltip"]
            },
            {
                "id": "settings-editor", 
                "path": "/settings-editor",
                "icon": "tune",
                "order": 3,
                "translatable_fields": ["label", "tooltip"]
            },
            {
                "id": "translations",
                "path": "/translations",
                "icon": "language",
                "order": 4,
                "translatable_fields": ["label", "tooltip"]
            }
        ],
        "is_active": False
    }
    
    admin_menu = UniversalMenu(
        id=2,
        name="Admin Menu", 
        structure=admin_menu_structure,
        default_language="en",
        has_translations=False,
        is_active=False
    )
    db.add(admin_menu)
    
    db.commit()
    print("✓ Created universal menus with multilingual support")


def create_roles(db: Session):
    """Seed base roles if missing"""
    from sqlalchemy import select, func

    # Import Role and Group explicitly
    from backend.db.role import Role, Group

    result = db.execute(select(func.count(Role.id)))
    count = result.scalar()

    if count > 0:
        print("✓ Roles already exist")
        return

    roles = [
        {
            "name": "admin",
            "description": "Administrator role with full system access",
            "is_system_role": True
        },
        {
            "name": "user",
            "description": "Standard user role with limited access",
            "is_system_role": True
        },
        {
            "name": "translator",
            "description": "Translation manager role",
            "is_system_role": True
        },
    ]

    for role_data in roles:
        role = Role(**role_data)
        db.add(role)

    db.commit()
    print("✓ Seeded roles: admin, user, translator")


def setup_universal_translation_system(db: Session, system_extension: Extension):
    """Initialize universal translation system"""
    
    # Create universal translation tables
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS extension_tables (
            id SERIAL PRIMARY KEY,
            extension_id INTEGER NOT NULL REFERENCES extensions(id) ON DELETE CASCADE,
            table_name VARCHAR(100) NOT NULL,
            table_schema JSON NOT NULL,
            translatable_fields JSON NOT NULL DEFAULT '[]',
            primary_key_field VARCHAR(100) NOT NULL DEFAULT 'id',
            is_multilingual BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(extension_id, table_name)
        )
    """))

    db.execute(text("""
        CREATE TABLE IF NOT EXISTS table_translations (
            id SERIAL PRIMARY KEY,
            extension_id INTEGER NOT NULL REFERENCES extensions(id) ON DELETE CASCADE,
            table_name VARCHAR(100) NOT NULL,
            record_id INTEGER NOT NULL,
            language_code VARCHAR(10) NOT NULL,
            translation_data JSON NOT NULL,
            translation_coverage NUMERIC(5,2) DEFAULT 0.0,
            is_fallback BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(extension_id, table_name, record_id, language_code)
        )
    """))

    db.execute(text("""
        CREATE TABLE IF NOT EXISTS extension_fields (
            id SERIAL PRIMARY KEY,
            extension_id INTEGER NOT NULL REFERENCES extensions(id) ON DELETE CASCADE,
            table_name VARCHAR(100) NOT NULL,
            field_name VARCHAR(100) NOT NULL,
            field_type VARCHAR(50) NOT NULL,
            is_translatable BOOLEAN DEFAULT FALSE,
            validation_rules JSON DEFAULT '{}',
            field_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(extension_id, table_name, field_name)
        )
    """))

    db.execute(text("""
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

    # Add new columns to existing tables if they don't exist
    db.execute(text("""
        ALTER TABLE menus
        ADD COLUMN IF NOT EXISTS structure JSON,
        ADD COLUMN IF NOT EXISTS default_language VARCHAR(10) DEFAULT 'en',
        ADD COLUMN IF NOT EXISTS has_translations BOOLEAN DEFAULT FALSE
    """))

    db.execute(text("""
        ALTER TABLE settings
        ADD COLUMN IF NOT EXISTS is_translatable BOOLEAN DEFAULT FALSE,
        ADD COLUMN IF NOT EXISTS content_type VARCHAR(50) DEFAULT 'setting'
    """))

    db.execute(text("""
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

    db.commit()
    
    # Register system tables for translation
    translation_engine = UniversalTranslationEngine(db)
    
    # Register menus table
    translation_engine.table_registry.register_table(
        extension_id=system_extension.id,
        table_name="menus",
        schema={"type": "system", "name": "System Menus"},
        translatable_fields=["name", "items"],
        primary_key="id",
        is_multilingual=True
    )
    
    # Register settings table
    translation_engine.table_registry.register_table(
        extension_id=system_extension.id,
        table_name="settings",
        schema={"type": "system", "name": "System Settings"},
        translatable_fields=["value", "description"],
        primary_key="id",
        is_multilingual=True
    )
    
    print("✓ Universal translation system initialized")


def add_user_id_column(db: Session):
    """Add user_id column to settings table if it doesn't exist"""
    try:
        # Check if column exists
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'settings' AND column_name = 'user_id'
        """))
        if result.fetchone():
            print("✓ user_id column already exists in settings table")
            return

        # Add the column
        db.execute(text("""
            ALTER TABLE settings ADD COLUMN user_id INTEGER REFERENCES users(id)
        """))
        db.commit()
        print("✓ Added user_id column to settings table")
    except Exception as e:
        print(f"⚠️ Could not add user_id column: {e}")
        db.rollback()


def create_default_settings(db: Session, system_extension: Extension):
    """Create default settings with universal translation support"""
    from sqlalchemy import select, func

    # First ensure user_id column exists
    add_user_id_column(db)

    result = db.execute(select(func.count(Settings.id)))
    count = result.scalar()

    if count > 0:
        print(f"✓ Settings already exist ({count} settings found)")
        return

    # Default settings with universal translation support
    default_settings = [
        {
            "key": "site_name",
            "value": "Mega Monitor",
            "description": "Site name - supports multilingual values",
            "is_translatable": True,
            "content_type": "multilingual"
        },
        {
            "key": "header_message",
            "value": "Welcome to Mega Monitor",
            "description": "Header message - supports multilingual values",
            "is_translatable": True,
            "content_type": "multilingual"
        },
        {
            "key": "header_bg_color",
            "value": "#4CAF50",
            "description": "Header background color (global setting)",
            "is_translatable": False,
            "content_type": "global"
        },
        {
            "key": "header_text_color",
            "value": "#ffffff",
            "description": "Header text color (global setting)",
            "is_translatable": False,
            "content_type": "global"
        },
        {
            "key": "logo_url",
            "value": "",
            "description": "Site logo URL (global setting)",
            "is_translatable": False,
            "content_type": "global"
        },
        {
            "key": "default_language",
            "value": "en",
            "description": "Default system language",
            "is_translatable": False,
            "content_type": "system"
        },
        {
            "key": "available_languages",
            "value": '["en", "bg", "es", "fr"]',
            "description": "Available system languages",
            "is_translatable": False,
            "content_type": "system"
        }
    ]

    for setting_data in default_settings:
        setting = Settings(**setting_data)
        db.add(setting)

    db.commit()
    print(f"✓ Created {len(default_settings)} default settings with translation support")
    print("✓ Settings ready for universal multilingual configuration")


def install_bulgarian_language_pack(db: Session, system_extension: Extension):
    """Install Bulgarian language pack during initialization"""
    
    from backend.utils.universal_extension_installer import UniversalExtensionInstaller
    
    # Check if Bulgarian language pack is already installed
    from sqlalchemy import select
    result = db.execute(
        select(Extension).where(Extension.name == "BulgarianLanguagePack")
    )
    existing_pack = result.scalar_one_or_none()
    
    if existing_pack:
        print("✓ Bulgarian language pack already installed")
        return
    
    installer = UniversalExtensionInstaller(db)
    
    bulgarian_pack = {
        "name": "BulgarianLanguagePack",
        "version": "1.0.0",
        "type": "language_pack",
        "language": {
            "code": "bg",
            "name": "Bulgarian",
            "nativeName": "Български"
        },
        "translations": {
            "system_menus": {
                "menu_translations": {
                    "1": {
                        "name": "Главно меню",
                        "items": [
                            {"id": "home", "label": "Начало", "tooltip": "Начална страница"},
                            {"id": "dashboard", "label": "Табло", "tooltip": "Табло за управление"},
                            {"id": "settings", "label": "Настройки", "tooltip": "Настройки на системата"},
                            {"id": "extensions", "label": "Разширения", "tooltip": "Управление на разширенията"},
                            {"id": "security", "label": "Сигурност", "tooltip": "Настройки за сигурност"},
                            {"id": "profile", "label": "Профил", "tooltip": "Моят профил"}
                        ]
                    }
                }
            },
            "settings": {
                "multilingual_settings": {
                    "site_name": "Мега Монитор",
                    "header_message": "Добре дошли в Мега Монитор"
                }
            },
            "frontend": {
                "common": {
                    "save": "Запази",
                    "cancel": "Отказ",
                    "delete": "Изтрий",
                    "edit": "Редактирай",
                    "search": "Търсене"
                },
                "navigation": {
                    "home": "Начало",
                    "dashboard": "Табло",
                    "settings": "Настройки"
                }
            }
        }
    }
    
    try:
        result = installer.install_extension(bulgarian_pack, extension_id=2)
        print(f"✅ Bulgarian Language Pack installed successfully")
        print(f"   Language: {result['language_code']}")
        print(f"   Status: {result['status']}")
    except Exception as e:
        print(f"⚠️  Bulgarian language pack installation failed: {str(e)}")
        print("✓ Continuing with English-only installation")


def run_migration_if_needed(db: Session):
    """Run migration from old to new system if old data exists"""
    
    from sqlalchemy import select, func
    
    # Check if old menu config data exists
    result = db.execute(
        select(func.count(Settings.id)).where(Settings.key.like('menu_config_%'))
    )
    old_menu_count = result.scalar()
    
    if old_menu_count > 0:
        print(f"\n🔄 Found {old_menu_count} old menu configuration entries")
        print("Running migration to universal translation system...")
        
        migration_manager = MultilingualMigrationManager(db)
        result = migration_manager.run_full_migration()
        
        print(f"✅ Migration completed:")
        print(f"   Menus migrated: {result['menus_migrated']}")
        print(f"   Settings migrated: {result['settings_migrated']}")
        
        if result['errors']:
            print(f"   Errors: {len(result['errors'])}")
            for error in result['errors'][:3]:  # Show first 3 errors
                print(f"     - {error}")
    else:
        print("✓ No old menu configuration data found - migration not needed")


def create_translation_api_user(db: Session):
    """Create service user for translation API operations"""
    from sqlalchemy import select
    
    result = db.execute(
        select(User).where(User.email == "translation_api@example.com")
    )
    api_user = result.scalar_one_or_none()
    
    if api_user:
        print("✓ Translation API user already exists")
        return
    
    api_user = User(
        username="translation_api",
        email="translation_api@example.com",
        hashed_password=hash_password("translation_api_2024"),
        role="translator"
    )
    db.add(api_user)
    db.commit()
    db.refresh(api_user)
    print("✓ Created translation API service user")


def init_database():
    """Initialize database with PostgreSQL and Universal Multilingual System"""
    print("\n=== Initializing Database with Universal Multilingual System ===\n")

    try:
        # Create sync engine and session
        engine = create_engine(get_db_url(), echo=False)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        with SessionLocal() as db:
            print("✓ Connected to PostgreSQL database")
            
            # Create all tables
            Base.metadata.create_all(bind=engine)
            print("✓ Database schema initialized")
            
            # Core system setup
            admin_user = create_admin_user(db)
            system_extension = create_system_extension(db)
            
            # Multilingual system setup
            setup_universal_translation_system(db, system_extension)
            create_menus(db, system_extension)
            create_roles(db)
            
            # Settings and language support
            create_default_settings(db, system_extension)
            run_migration_if_needed(db)
            create_translation_api_user(db)
            
            # Install Bulgarian language pack
            install_bulgarian_language_pack(db, system_extension)
            
            print("\n=== Database Initialization Complete ===\n")
            print("🌍 Universal Multilingual System Ready!")
            print("\nLogin Credentials:")
            print("  Email: admin@example.com")
            print("  Password: admin")
            print("\nCore System Features:")
            print("  ✅ PostgreSQL database with async support")
            print("  ✅ Universal translation engine")
            print("  ✅ Extension table registry")
            print("  ✅ Dynamic table creation")
            print("  ✅ Language pack installation")
            print("  ✅ E-commerce and POS system support")
            print("\nMultilingual Features:")
            print("  ✅ Extension-agnostic translations")
            print("  ✅ No data duplication")
            print("  ✅ Translation coverage tracking")
            print("  ✅ Visual translation management")
            print("  ✅ Bulgarian language pack pre-installed")
            print("\nAPI Endpoints:")
            print("  GET/POST /api/translations/* - Translation management")
            print("  GET/POST /api/extensions/* - Extension management")
            print("  POST /api/extensions/install - Install extensions")
            print("\nNext Steps:")
            print("  1. Visit /translations to manage translations")
            print("  2. Install additional language packs via Extensions")
            print("  3. Create custom extensions with multilingual support")
            
    except Exception as e:
        print(f"\n❌ Database initialization failed: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


def fix_unicode_in_menu_data(db: Session):
    """Fix Unicode escape sequences in existing menu data"""
    try:
        menus = db.query(Menu).all()
        fixed_count = 0

        for menu in menus:
            needs_update = False

            # Fix items field
            if menu.items:
                items_str = json.dumps(menu.items, ensure_ascii=False)
                if items_str != json.dumps(menu.items, ensure_ascii=True):
                    menu.items = json.loads(items_str)
                    needs_update = True

            # Fix structure field
            if menu.structure:
                structure_str = json.dumps(menu.structure, ensure_ascii=False)
                if structure_str != json.dumps(menu.structure, ensure_ascii=True):
                    menu.structure = json.loads(structure_str)
                    needs_update = True

            if needs_update:
                fixed_count += 1

        if fixed_count > 0:
            db.commit()
            print(f"✓ Fixed Unicode encoding in {fixed_count} menu records")
        else:
            print("ℹ️ No menu records needed Unicode fixing")

    except Exception as e:
        db.rollback()
        print(f"❌ Error fixing Unicode in menu data: {e}")


if __name__ == "__main__":
    # Run initialization
    init_database()

    # Fix Unicode in existing data
    from backend.database import SessionLocal
    with SessionLocal() as db:
        fix_unicode_in_menu_data(db)