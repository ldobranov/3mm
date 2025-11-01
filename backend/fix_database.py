#!/usr/bin/env python3
"""
Script to fix database schema issues
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from backend.db.base import Base

# Import all models to register them with Base
import backend.db.user
import backend.db.role
import backend.db.page
import backend.db.settings
import backend.db.menu
import backend.db.display
import backend.db.widget
import backend.db.session
import backend.db.audit_log
import backend.db.permission

def fix_database():
    # Get database path
    db_path = os.path.join(os.path.dirname(__file__), 'mega_monitor.db')
    
    # Create engine
    engine = create_engine(f'sqlite:///{db_path}')
    
    # Check if audit_logs table exists and has wrong schema
    with engine.connect() as conn:
        # Check if table exists
        result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs'"))
        if result.fetchone():
            print("Dropping old audit_logs table...")
            conn.execute(text("DROP TABLE IF EXISTS audit_logs"))
            conn.commit()
        
        # Also drop sessions and permissions tables if they exist
        conn.execute(text("DROP TABLE IF EXISTS sessions"))
        conn.execute(text("DROP TABLE IF EXISTS permissions"))
        conn.commit()
    
    # Create tables with correct schema
    print("Creating tables with correct schema...")
    Base.metadata.create_all(bind=engine, tables=[
        backend.db.session.Session.__table__,
        backend.db.audit_log.AuditLog.__table__,
        backend.db.permission.Permission.__table__
    ])
    
    print("Database schema fixed successfully!")
    
    # Recreate admin user if needed
    from sqlalchemy.orm import sessionmaker
    from backend.db.user import User, hash_password
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Check if admin exists
    admin = session.query(User).filter_by(username='admin').first()
    if not admin:
        print("Creating admin user...")
        admin = User(
            username='admin',
            email='admin@example.com',
            hashed_password=hash_password('admin'),
            role='admin'
        )
        session.add(admin)
        session.commit()
        print("Admin user created")
    
    session.close()

if __name__ == "__main__":
    fix_database()