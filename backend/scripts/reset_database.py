#!/usr/bin/env python3
"""Reset database - drop all tables and reinitialize with fresh data"""

import sys
import os
import shutil
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.database import engine, Base
from backend.scripts.init_database import init_database

def reset_database():
    """Drop all tables and recreate database from scratch"""
    print("\n=== Database Reset ===\n")
    
    # Get database path
    db_path = Path("mega_monitor.db")
    
    # Backup existing database if it exists
    if db_path.exists():
        backup_path = Path("mega_monitor.db.backup")
        print(f"✓ Backing up existing database to {backup_path}")
        shutil.copy2(db_path, backup_path)
        
        # Remove existing database
        print("✓ Removing existing database")
        db_path.unlink()
    
    # Now recreate the database from scratch
    # The engine will create a new database file when we create tables
    print("✓ Creating fresh database schema")
    Base.metadata.create_all(bind=engine)
    
    # Initialize with sample data
    print("\n=== Initializing Fresh Database ===\n")
    init_database()
    
    print("\n=== Database Reset Complete ===\n")
    print("Database has been reset to a fresh state.")
    if db_path.exists():
        print("Previous database backed up to mega_monitor.db.backup")

if __name__ == "__main__":
    response = input("\n⚠️  WARNING: This will delete all existing data!\nAre you sure you want to reset the database? (yes/no): ")
    if response.lower() == 'yes':
        reset_database()
    else:
        print("Database reset cancelled.")