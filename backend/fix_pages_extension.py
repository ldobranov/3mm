#!/usr/bin/env python3
"""
Check and fix PagesExtension status
"""

import sys
import os
from pathlib import Path

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from backend.database import get_db, init_db
from backend.db.extension import Extension

def check_and_fix_pages_extension():
    """Check and fix PagesExtension status"""
    
    # Initialize the database
    init_db()
    
    # Get database session
    db = next(get_db())
    
    try:
        print("=== Checking Extensions in Database ===")
        all_extensions = db.query(Extension).all()
        
        if not all_extensions:
            print("No extensions found in database")
            return False
        
        pages_extension = None
        for ext in all_extensions:
            print(f"Extension: {ext.name} v{ext.version}")
            print(f"  Status: {ext.status}, Enabled: {ext.is_enabled}")
            print(f"  Type: {ext.type}, File path: {ext.file_path}")
            print(f"  Security: {ext.security_status}")
            print()
            
            if ext.name == "PagesExtension" and ext.version == "1.0.0":
                pages_extension = ext
        
        if not pages_extension:
            print("❌ PagesExtension not found in database!")
            return False
        
        print(f"=== PagesExtension Found ===")
        print(f"Current status: {pages_extension.status}")
        print(f"Is enabled: {pages_extension.is_enabled}")
        print(f"File path: {pages_extension.file_path}")
        
        # Check if file path exists
        file_path = Path(pages_extension.file_path)
        if not file_path.exists():
            print(f"❌ Extension file path does not exist: {file_path}")
            return False
        
        print(f"✅ Extension files exist at: {file_path}")
        
        # Enable the extension if not already enabled
        if not pages_extension.is_enabled:
            print("Enabling PagesExtension...")
            pages_extension.is_enabled = True
            pages_extension.status = "active"
            db.commit()
            print("✅ PagesExtension enabled!")
        else:
            print("✅ PagesExtension is already enabled")
        
        # Check if database schema file exists
        schema_file = file_path / "database_schema.json"
        if not schema_file.exists():
            print(f"⚠️ Database schema file missing: {schema_file}")
            # Copy it if it exists in temp directory
            temp_schema = Path("temp_PagesExtension_1.0.0/database_schema.json")
            if temp_schema.exists():
                import shutil
                shutil.copy2(temp_schema, schema_file)
                print(f"✅ Copied database schema to: {schema_file}")
        
        print("\n=== Next Steps ===")
        print("1. Restart the backend server to load the enabled extension")
        print("2. The extension routes should be available at /api/pages/*")
        print("3. The frontend should be able to access /pages")
        
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
    check_and_fix_pages_extension()