#!/usr/bin/env python3
"""Initialize database with admin user and security setup"""

import sys
import os
# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.database import SessionLocal, init_db
from backend.db.user import User
from backend.db.menu import Menu
from backend.db.role import Role, Group
from backend.utils.auth import hash_password

def create_admin_user(db):
    """Create admin user if not exists, or update password if exists"""
    admin = db.query(User).filter(User.email == "admin@example.com").first()
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
                {"label": "Settings", "path": "/settings", "icon": "settings"},
                {"label": "Extensions", "path": "/extensions", "icon": "extensions"},
                {"label": "Security", "path": "/security", "icon": "security"},
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
        {
            "name": "admin",
            "description": "Administrator role with full system access",
            "is_system_role": 1
        },
        {
            "name": "user",
            "description": "Standard user role with limited access",
            "is_system_role": 1
        },
    ]
    for r in roles:
        db.add(Role(**r))
    db.commit()
    print("✓ Seeded roles: admin, user")

def setup_security_tables(db):
    """Setup security tables and assign roles to existing users"""
    # Import association tables to ensure they're created
    from backend.db.association_tables import user_roles, user_groups
    
    # Create all tables if they don't exist (this happens via Base.metadata.create_all in init_db)
    
    # Assign roles to existing admin users
    admin_users = db.query(User).filter(User.role == "admin").all()
    
    for admin_user in admin_users:
        # Check if user already has admin role
        existing_admin_roles = admin_user.roles.filter(Role.name == "admin").all()
        if not existing_admin_roles:
            admin_role = db.query(Role).filter(Role.name == "admin").first()
            if admin_role:
                admin_user.roles.append(admin_role)
                print(f"✓ Assigned admin role to user: {admin_user.username}")
    
    db.commit()
    print("✓ Security tables setup completed")

def init_database():
    """Initialize database with security setup"""
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
        
        # Setup security tables (roles/groups)
        setup_security_tables(db)

        print("\n=== Database Initialization Complete ===\n")
        print("You can now login with:")
        print("  Email: admin@example.com")
        print("  Password: admin")
        print("\nSecurity setup created:")
        print("  - 2 menus (Main Menu, Admin Menu)")
        print("  - 2 system roles (admin, user)")
        print("  - Security tables for advanced role/group management")
        
    except Exception as e:
        print(f"\n❌ Error during initialization: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    init_database()