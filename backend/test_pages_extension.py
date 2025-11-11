#!/usr/bin/env python3
"""
Test script to verify PagesExtension can be loaded properly
"""

import sys
import os
from pathlib import Path
from fastapi import FastAPI
from sqlalchemy.orm import Session

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from backend.database import get_db, init_db
from backend.utils.extension_manager import extension_manager

def test_pages_extension_loading():
    """Test that PagesExtension can be loaded by the extension manager"""
    
    # Initialize the database
    init_db()
    
    # Create a FastAPI app (mock)
    app = FastAPI()
    
    # Get database session
    db = next(get_db())
    
    # Test path to the PagesExtension
    extension_path = Path("temp_PagesExtension_1.0.0")
    extension_id = "PagesExtension_1.0.0"
    
    if not extension_path.exists():
        print(f"Extension path {extension_path} does not exist!")
        return False
    
    print(f"Testing extension loading for {extension_id} at {extension_path}")
    
    try:
        # Try to load the extension module
        print("1. Loading extension module...")
        module = extension_manager.load_extension_module(extension_path, extension_id)
        if not module:
            print("❌ Failed to load extension module")
            return False
        print("✅ Extension module loaded successfully")
        
        # Try to initialize the extension
        print("2. Initializing extension...")
        success = extension_manager.initialize_extension(
            extension_id=extension_id,
            extension_path=extension_path,
            app=app,
            db=db
        )
        
        if not success:
            print("❌ Failed to initialize extension")
            return False
        print("✅ Extension initialized successfully")
        
        # Check if context was created
        print("3. Checking extension context...")
        context = extension_manager.get_extension_context(extension_id)
        if not context:
            print("❌ Extension context not found")
            return False
        print("✅ Extension context created successfully")
        
        # Check if routes were registered
        print("4. Checking registered routes...")
        routes_registered = len(context.routes_registered)
        print(f"   Routes registered: {routes_registered}")
        for i, router in enumerate(context.routes_registered):
            print(f"   Route {i+1}: {router.prefix}")
        
        if routes_registered > 0:
            print("✅ Routes registered successfully")
        else:
            print("⚠️ No routes registered (this might be expected)")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during extension testing: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Cleanup
        if extension_manager.is_extension_loaded(extension_id):
            print("5. Cleaning up extension...")
            extension_manager.cleanup_extension(extension_id)
            print("✅ Extension cleaned up successfully")

if __name__ == "__main__":
    print("Testing PagesExtension integration...")
    success = test_pages_extension_loading()
    if success:
        print("\n🎉 PagesExtension integration test PASSED!")
        sys.exit(0)
    else:
        print("\n💥 PagesExtension integration test FAILED!")
        sys.exit(1)