#!/usr/bin/env python3
"""Initialize database with admin user and sample data"""

import sys
import os
# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.database import SessionLocal, init_db
from backend.db.user import User
from backend.db.menu import Menu
from backend.db.page import Page
from backend.db.display import Display
from backend.db.widget import Widget
from backend.db.settings import Settings
from backend.db.role import Role
from backend.db.extension import Extension
from backend.utils.auth import hash_password
import json

def create_admin_user(db):
    """Create admin user if not exists"""
    admin = db.query(User).filter(User.email == "admin@example.com").first()
    if admin:
        print("✓ Admin user already exists")
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

def create_menus(db):
    """Create default menu items"""
    # Check if menus exist
    existing = db.query(Menu).first()
    if existing:
        print("✓ Menus already exist")
        return
    
    menu_items = [
        {
            "name": "Main Menu",
            "items": [
                {"label": "Home", "path": "/", "icon": "home"},
                {"label": "Dashboard", "path": "/dashboard", "icon": "dashboard"},
                {"label": "Pages", "path": "/pages", "icon": "pages"},
                {"label": "Settings", "path": "/settings", "icon": "settings"},
                {"label": "Profile", "path": "/user/profile", "icon": "person"},
            ],
            "is_active": True
        },
        {
            "name": "Admin Menu",
            "items": [
                {"label": "Users", "path": "/users", "icon": "people"},
                {"label": "Menu Editor", "path": "/menu-editor", "icon": "menu"},
                {"label": "Settings Editor", "path": "/settings-editor", "icon": "tune"},
            ],
            "is_active": False
        }
    ]
    
    for menu_data in menu_items:
        menu = Menu(
            name=menu_data["name"],
            items=menu_data["items"],
            is_active=menu_data["is_active"]
        )
        db.add(menu)
    
    db.commit()
    print("✓ Created default menus")

def create_roles(db):
    """Seed base roles if missing"""
    existing = db.query(Role).count()
    if existing:
        print("✓ Roles already exist")
        return

    roles = [
        {"name": "admin"},
        {"name": "user"},
    ]
    for r in roles:
        db.add(Role(**r))
    db.commit()
    print("✓ Seeded roles: admin, user")


def create_pages(db, admin_user):
    """Create sample pages"""
    # Check if pages exist
    existing = db.query(Page).first()
    if existing:
        print("✓ Pages already exist")
        return
    
    pages_data = [
        {
            "title": "Welcome",
            "slug": "welcome",
            "content": "<h1>Welcome to Mega Monitor</h1><p>This is your monitoring dashboard system.</p>",
            "is_public": True,
            "allowed_roles": [],
            "owner_id": admin_user.id
        },
        {
            "title": "Documentation",
            "slug": "docs",
            "content": "<h1>Documentation</h1><p>Learn how to use the system:</p><ul><li>Create displays</li><li>Add widgets</li><li>Manage pages</li></ul>",
            "is_public": True,
            "allowed_roles": [],
            "owner_id": admin_user.id
        },
        {
            "title": "Admin Guide",
            "slug": "admin-guide",
            "content": "<h1>Admin Guide</h1><p>This page is only visible to administrators.</p>",
            "is_public": False,
            "allowed_roles": ["admin"],
            "owner_id": admin_user.id
        }
    ]
    
    for page_data in pages_data:
        page = Page(**page_data)
        db.add(page)
    
    db.commit()
    print("✓ Created sample pages")

def create_displays(db, admin_user):
    """Create sample displays with widgets"""
    # Check if displays exist
    existing = db.query(Display).first()
    if existing:
        print("✓ Displays already exist")
        return
    
    # Create a sample display
    display = Display(
        user_id=admin_user.id,
        title="My Dashboard",
        slug="my-dashboard",
        is_public=True
    )
    db.add(display)
    db.commit()
    db.refresh(display)
    
    # Add some widgets
    widgets_data = [
        {
            "display_id": display.id,
            "type": "CLOCK",
            "config": {
                "timezone": "UTC",
                "format": "24h",
                "showSeconds": True
            },
            "x": 10,
            "y": 10,
            "width": 300,
            "height": 100,
            "z_index": 1
        },
        {
            "display_id": display.id,
            "type": "TEXT",
            "config": {
                "content": "Welcome to your dashboard!",
                "fontSize": "24px",
                "color": "#333"
            },
            "x": 10,
            "y": 120,
            "width": 400,
            "height": 80,
            "z_index": 2
        },
        {
            "display_id": display.id,
            "type": "RSS",
            "config": {
                "url": "https://news.ycombinator.com/rss",
                "maxItems": 5,
                "refreshInterval": 300
            },
            "x": 320,
            "y": 10,
            "width": 400,
            "height": 300,
            "z_index": 3
        }
    ]
    
    for widget_data in widgets_data:
        widget = Widget(**widget_data)
        db.add(widget)
    
    db.commit()
    print("✓ Created sample display with widgets")

def create_settings(db):
    """Create default settings"""
    # Check if settings exist
    existing = db.query(Settings).first()
    if existing:
        print("✓ Settings already exist")
        return
    
    settings_data = [
        {
            "key": "site_name",
            "value": "Mega Monitor",
            "description": "The name of your monitoring site"
        },
        {
            "key": "theme",
            "value": "light",
            "description": "UI theme (light or dark)"
        },
        {
            "key": "timezone",
            "value": "UTC",
            "description": "Default timezone for the application"
        },
        {
            "key": "language",
            "value": "en",
            "description": "Default language"
        },
        {
            "key": "allow_registration",
            "value": "true",
            "description": "Allow new users to register"
        },
        {
            "key": "theme_accent",
            "value": "#10b981",
            "description": "Accent color"
        },
        {
            "key": "theme_background",
            "value": "#ffffff",
            "description": "Background color"
        },
        {
            "key": "theme_text",
            "value": "#0f172a",
            "description": "Text color"
        },
        {
            "key": "theme_border",
            "value": "#e5e7eb",
            "description": "Border color"
        },
        {
            "key": "theme_radius_md",
            "value": "8px",
            "description": "Medium border radius"
        },
        {
            "key": "theme_shadow_md",
            "value": "0 2px 8px rgba(0,0,0,0.10)",
            "description": "Medium shadow"
        }
    ]
    
    for setting_data in settings_data:
        setting = Settings(**setting_data)
        db.add(setting)
    
    db.commit()
    print("✓ Created default settings")

def init_database():
    """Initialize database with all sample data"""
    print("\n=== Initializing Database ===\n")
    
    # Initialize database schema
    init_db()
    print("✓ Database schema initialized")
    
    # Create session
    db = SessionLocal()
    
    try:
        # Create admin user
        admin = create_admin_user(db)
        
        # Create menus
        create_menus(db)

        # Create base roles
        create_roles(db)
        
        # Create pages
        create_pages(db, admin)
        
        # Create displays
        create_displays(db, admin)
        
        # Create settings
        create_settings(db)
        
        print("\n=== Database Initialization Complete ===\n")
        print("You can now login with:")
        print("  Email: admin@example.com")
        print("  Password: admin")
        print("\nSample data created:")
        print("  - 2 menus (Main Menu, Admin Menu)")
        print("  - 3 pages (Welcome, Documentation, Admin Guide)")
        print("  - 1 display with 3 widgets")
        print("  - 5 settings")
        
    except Exception as e:
        print(f"\n❌ Error during initialization: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    init_database()