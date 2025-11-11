#!/usr/bin/env python3
"""
Script to force enable the PagesExtension
"""

import sys
import os
from pathlib import Path

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from backend.database import get_db, init_db
from backend.utils.extension_manager import extension_manager
from backend.db.extension import Extension

def force_enable_pages_extension():
    """Force enable the PagesExtension"""
    
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
            return False
        
        print(f"Found extension: {extension.name} v{extension.version}")
        print(f"Current status: {extension.status} (enabled: {extension.is_enabled})")
        
        # Force enable the extension
        extension.is_enabled = True
        extension.status = "active"
        db.commit()
        
        print("Extension marked as enabled in database")
        
        # Now try to initialize it
        extension_id = f"{extension.name}_{extension.version}"
        extension_path = Path(extension.file_path)
        
        print(f"Initializing extension from: {extension_path}")
        
        success = extension_manager.initialize_extension(
            extension_id=extension_id,
            extension_path=extension_path,
            app=None,  # Will use the one from extension manager
            db=db
        )
        
        if success:
            print("✅ Extension successfully initialized!")
            
            # Check routes
            context = extension_manager.get_extension_context(extension_id)
            if context:
                print(f"Routes registered: {len(context.routes_registered)}")
                for i, router in enumerate(context.routes_registered):
                    print(f"  Route {i+1}: {router.prefix}")
            
            return True
        else:
            print("❌ Failed to initialize extension")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    print("Force enabling PagesExtension...")
    success = force_enable_pages_extension()
    if success:
        print("\n🎉 PagesExtension successfully enabled!")
    else:
        print("\n💥 Failed to enable PagesExtension!")