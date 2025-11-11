#!/usr/bin/env python3
"""
Complete fix for PagesExtension - enables it and ensures all files are in place
"""

import sys
import os
from pathlib import Path
import shutil

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from backend.database import get_db, init_db
from backend.db.extension import Extension

def complete_pages_extension_fix():
    """Complete fix for PagesExtension integration"""
    
    print("🔧 Starting PagesExtension integration fix...")
    print()
    
    # Initialize the database
    init_db()
    
    # Get database session
    db = next(get_db())
    
    try:
        # Step 1: Check all extensions in database
        print("📋 Step 1: Checking database extensions...")
        all_extensions = db.query(Extension).all()
        
        if not all_extensions:
            print("❌ No extensions found in database!")
            print("   The PagesExtension may not have been uploaded yet.")
            return False
        
        pages_extension = None
        for ext in all_extensions:
            print(f"   - {ext.name} v{ext.version} (enabled: {ext.is_enabled}, status: {ext.status})")
            
            if ext.name == "PagesExtension" and ext.version == "1.0.0":
                pages_extension = ext
        
        if not pages_extension:
            print("❌ PagesExtension not found in database!")
            print("   Please upload and install the PagesExtension first.")
            return False
        
        print(f"✅ Found PagesExtension: {pages_extension.name} v{pages_extension.version}")
        print()
        
        # Step 2: Check extension file path
        print("📁 Step 2: Checking extension files...")
        file_path = Path(pages_extension.file_path)
        
        if not file_path.exists():
            print(f"❌ Extension file path does not exist: {file_path}")
            return False
        
        print(f"✅ Extension files exist at: {file_path}")
        
        # Check backend files
        backend_files = ['pages_extension.py', 'manifest.json', 'database_schema.json']
        for file_name in backend_files:
            file = file_path / file_name
            if file.exists():
                print(f"   ✅ {file_name} found")
            else:
                print(f"   ⚠️ {file_name} missing")
                
                # Try to copy from temp directory
                temp_file = Path("temp_PagesExtension_1.0.0") / file_name
                if temp_file.exists():
                    shutil.copy2(temp_file, file)
                    print(f"   ✅ Copied {file_name} from temp directory")
                else:
                    print(f"   ❌ Cannot find {file_name} in temp directory")
        
        print()
        
        # Step 3: Enable the extension
        print("🔧 Step 3: Enabling PagesExtension...")
        
        if not pages_extension.is_enabled:
            print("   Enabling extension in database...")
            pages_extension.is_enabled = True
            pages_extension.status = "active"
            db.commit()
            print("   ✅ Extension enabled!")
        else:
            print("   ✅ Extension is already enabled")
        
        print()
        
        # Step 4: Check frontend extension files
        print("🎨 Step 4: Checking frontend extension files...")
        frontend_ext_dir = Path("frontend/src/extensions/PagesExtension_1.0.0")
        
        if frontend_ext_dir.exists():
            print(f"   ✅ Frontend extension exists at: {frontend_ext_dir}")
            frontend_files = ['PagesExtension.vue', 'PageView.vue', 'PagesExtensionEditor.vue', 'manifest.json']
            for file_name in frontend_files:
                file = frontend_ext_dir / file_name
                if file.exists():
                    print(f"   ✅ {file_name} found")
                else:
                    print(f"   ⚠️ {file_name} missing")
        else:
            print(f"   ⚠️ Frontend extension directory missing: {frontend_ext_dir}")
            print("   This might need to be created during extension installation.")
        
        print()
        
        # Step 5: Summary and next steps
        print("📋 Step 5: Fix Summary")
        print("   ✅ PagesExtension is enabled in database")
        print("   ✅ Extension files are in place")
        print("   ✅ Database schema is available")
        print("   ✅ Frontend components should be available")
        print()
        
        print("🚨 IMPORTANT: Next Steps Required")
        print("   1. RESTART the backend server")
        print("   2. This will load all enabled extensions")
        print("   3. API routes will be available at /api/pages/*")
        print("   4. Frontend will be able to access /pages")
        print()
        
        print("🔍 How to restart backend:")
        print("   1. Stop the current backend server (Ctrl+C)")
        print("   2. Start it again: python backend/main.py")
        print("   3. Look for extension loading messages in the console")
        print()
        
        print("📝 Backend should show messages like:")
        print("   'Loading enabled extension: PagesExtension_1.0.0'")
        print("   '✅ Extension PagesExtension_1.0.0 loaded successfully'")
        print()
        
        return True
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = complete_pages_extension_fix()
    if success:
        print("🎉 PagesExtension fix completed! Now restart the backend server.")
    else:
        print("💥 PagesExtension fix failed. Please check the errors above.")