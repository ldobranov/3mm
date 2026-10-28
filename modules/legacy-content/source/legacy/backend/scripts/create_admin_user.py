import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from backend.db.settings import Settings
from backend.utils.auth import hash_password
from backend.database import SessionLocal, engine
import json
import logging
from sqlalchemy import MetaData
from backend.db.base import Base

logging.basicConfig(level=logging.INFO)

# Explicit imports for User and Role models
from backend.db.user import User
from backend.db.role import Role
from backend.db.menu import Menu  # Import Menu model
from backend.db.page import Page  # Import Page model

# Deferred imports for User and Role models
def get_user_model():
    from backend.db.user import User
    return User

def get_role_model():
    from backend.db.role import Role
    return Role

# Verify model registration in Base.metadata
logging.info("Verifying model registration in Base.metadata.")
for table_name in Base.metadata.tables.keys():
    logging.info(f"Registered table: {table_name}")

# Drop all tables and indexes using Base.metadata.drop_all
with engine.connect() as connection:
    logging.info("Dropping all tables and indexes.")
    Base.metadata.drop_all(bind=engine)
    logging.info("Successfully dropped all tables and indexes.")

# # Recreate schema using Base.metadata.create_all
logging.info("Recreating schema using Base.metadata.create_all.")
Base.metadata.create_all(bind=engine)
logging.info("Successfully recreated schema.")

def create_admin_user():
    admin_username = "admin"
    admin_email = "admin@example.com"
    admin_password = "admin"
    admin_role = "admin"  # Default role for admin user
    hashed_password = hash_password(admin_password)

    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.username == admin_username).first()
        if not user:
            user = User(
                username=admin_username,
                email=admin_email,
                hashed_password=hashed_password,
                role=admin_role  # Assign default role
            )
            db.add(user)
            db.commit()
            print(f"Admin user '{admin_username}' created.")
        else:
            print(f"Admin user '{admin_username}' already exists.")
    finally:
        db.close()

def seed_page_table(db):
    pages = [
        {"title": "About Us", "content": "<h1>About Us</h1><p>This is the <strong>About Us</strong> page with HTML content.", "slug": "about-us"},
        {"title": "Contact", "content": "<h1>Contact</h1><p>This is the <em>Contact</em> page with HTML content.", "slug": "contact"},
    ]
    for page_data in pages:
        page = Page(title=page_data["title"], content=page_data["content"], slug=page_data["slug"])
        db.add(page)
    db.commit()
    print("Page table seeded with HTML content.")

def seed_test_data(db):
    # Seed roles
    roles = ["Admin", "Editor", "Viewer"]
    for role_name in roles:
        role = get_role_model()(name=role_name)
        db.add(role)
    
    db.commit()
    print("Test data seeded.")

def seed_roles_and_users(db):
    roles = [
        {"name": "admin"},
        {"name": "user"},
    ]

    for role_data in roles:
        existing_role = db.query(Role).filter(Role.name == role_data["name"]).first()
        if not existing_role:
            role = Role(**role_data)
            db.add(role)
    db.commit()

    users = [
        {
            "username": "test_user",
            "email": "test_user@example.com",
            "hashed_password": hash_password("test_password"),
            "role": "user",  # Assign default role
        }
    ]

    for user_data in users:
        existing_user = db.query(User).filter(User.email == user_data["email"]).first()
        if not existing_user:
            user = User(**user_data)
            db.add(user)
    db.commit()

def seed_settings(db):
    initial_settings = {
        "name": "Mega Monitor",
        "language": "en",
        "data": {"additional_data": "test data"},
    }
    settings = db.query(Settings).first()
    if not settings:
        settings = Settings(
            name=initial_settings["name"],
            language=initial_settings["language"],
            data=initial_settings["data"]
        )
        db.add(settings)
    else:
        settings.name = initial_settings["name"]
        settings.language = initial_settings["language"]
        settings.data.update(initial_settings["data"])
    db.commit()
    print("Settings seeded successfully.")

def seed_menu(db):
    initial_menu = [
        {"name": "Home", "path": "/", "order": 1},
        {"name": "Settings", "path": "/settings", "order": 2},
        {"name": "Users", "path": "/users", "order": 3},
        {"name": "Extensions", "path": "/extensions", "order": 4},
    ]

    for menu_item in initial_menu:
        existing_menu_item = db.query(Menu).filter(Menu.name == menu_item["name"]).first()
        if not existing_menu_item:
            new_menu_item = Menu(
                name=menu_item["name"],
                path=menu_item["path"],
                order=menu_item["order"]
            )
            db.add(new_menu_item)
    db.commit()
    print("Menu seeded successfully.")

def populate_initial_data():
    """Populate the database with initial data."""
    db: Session = SessionLocal()
    try:
        # Create admin user
        admin_username = "admin"
        admin_email = "admin@example.com"
        admin_password = "admin"
        hashed_password = hash_password(admin_password)

        admin_user = db.query(User).filter(User.username == admin_username).first()
        if not admin_user:
            admin_user = User(username=admin_username, email=admin_email, hashed_password=hashed_password)
            db.add(admin_user)

        # Add initial menu items
        # Check for existing menu items before adding new ones
        existing_menu_names = {menu.name for menu in db.query(Menu).all()}
        menu_items = [
            Menu(name="Home", path="/", order=1),
            Menu(name="Settings", path="/settings", order=2)
        ]
        for menu_item in menu_items:
            if menu_item.name not in existing_menu_names:
                db.add(menu_item)

        db.commit()
        logging.info("Successfully populated initial data.")
    except Exception as e:
        logging.error(f"Error populating initial data: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_admin_user()
    db: Session = SessionLocal()
    try:
        seed_page_table(db)
        seed_test_data(db)
        seed_roles_and_users(db)
        seed_settings(db)
        seed_menu(db)
        populate_initial_data()
    finally:
        db.close()