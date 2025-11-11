#!/usr/bin/env python3
"""
Script to check and enable PagesExtension
"""

import sys
import os
from pathlib import Path

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from backend.database import get_db, init_db
from backend.db.extension import Extension

def check_and_enable_pages_extension():
    """Check extension status and enable if needed"""
    
    # Initialize the database
    init_db()
    
    # Get database session
    db = next(get_db())
    
    try:
        # Find the PagesExtension in the database
        extension = db.query(Extension).filter(
            Extension.name == "PagesExtension",
            Extension.version == "1.0.0"
        ).first()
        
        if not extension:
            print("PagesExtension not found in database")
            print("Available extensions:")
            for ext in db.query(Extension).all():
                print(f"  - {ext.name} v{ext.version} (enabled: {ext.is_enabled})")
            return False
        
        print(f"Found extension: {extension.name} v{extension.version}")
        print(f"Current status: {extension.status} (enabled: {extension.is_enabled})")
        
        # If not enabled, enable it
        if not extension.is_enabled:
            print("Enabling extension...")
            extension.is_enabled = True
            extension.status = "active"
            db.commit()
            print("✅ Extension enabled!")
        else:
            print("Extension is already enabled")
            
        return True
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    print("Checking PagesExtension status...")
    check_and_enable_pages_extension()