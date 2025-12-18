"""
Universal Translation API Endpoints
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from backend.utils.universal_translation_engine import UniversalTranslationEngine, TableNotRegisteredError, ValidationError
from backend.utils.db_utils import get_db_session

router = APIRouter(prefix="/api/translations", tags=["universal-translations"])

@router.get("/extensions/{extension_id}/tables/{table_name}/records/{record_id}")
async def get_multilingual_record(
    extension_id: int,
    table_name: str, 
    record_id: int,
    language: str = Query(default="en", description="Language code to fetch translations for"),
    db: AsyncSession = Depends(get_db_session)
):
    """Get record with translations in specified language"""
    
    try:
        translation_engine = UniversalTranslationEngine(db)
        record = await translation_engine.get_translated_record(
            extension_id, table_name, record_id, language
        )
        
        if not record:
            raise HTTPException(404, "Record not found")
        
        return {
            "record": record,
            "language": language,
            "has_translations": bool(record.get("name") != record.get("name"))  # Simple check
        }
        
    except TableNotRegisteredError:
        raise HTTPException(404, "Table not registered for translations")

@router.put("/extensions/{extension_id}/tables/{table_name}/records/{record_id}/translations/{language_code}")
async def update_record_translations(
    extension_id: int,
    table_name: str,
    record_id: int,
    language_code: str,
    translation_data: dict,
    db: AsyncSession = Depends(get_db_session)
):
    """Update translations for a specific record"""
    
    try:
        translation_engine = UniversalTranslationEngine(db)
        await translation_engine.update_translations(
            extension_id, table_name, record_id, language_code, translation_data
        )
        
        return {"message": "Translations updated successfully"}
        
    except TableNotRegisteredError:
        raise HTTPException(404, "Table not registered for translations")
    except ValidationError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to update translations: {str(e)}")

@router.get("/extensions/{extension_id}/tables/{table_name}/translations/coverage")
async def get_translation_coverage(
    extension_id: int,
    table_name: str,
    language_code: str = Query(default=None, description="Specific language to get coverage for"),
    db: AsyncSession = Depends(get_db_session)
):
    """Get translation coverage statistics for a table"""
    
    try:
        translation_engine = UniversalTranslationEngine(db)
        coverage = await translation_engine.get_table_coverage(
            extension_id, table_name, language_code
        )
        
        return coverage
        
    except TableNotRegisteredError:
        raise HTTPException(404, "Table not registered for translations")

@router.get("/extensions/{extension_id}/tables")
async def get_extension_tables(
    extension_id: int,
    multilingual_only: bool = Query(default=False, description="Only return multilingual tables"),
    db: AsyncSession = Depends(get_db_session)
):
    """Get all tables for an extension with their multilingual capabilities"""
    
    try:
        translation_engine = UniversalTranslationEngine(db)
        
        if multilingual_only:
            tables = await translation_engine.table_registry.get_multilingual_tables(extension_id)
        else:
            tables = await translation_engine.table_registry.get_extension_tables(extension_id)
        
        result = []
        for table in tables:
            result.append({
                "table_name": table.table_name,
                "translatable_fields": table.translatable_fields,
                "is_multilingual": table.is_multilingual,
                "schema": table.table_schema,
                "primary_key": table.primary_key_field
            })
        
        return {"tables": result}
        
    except Exception as e:
        raise HTTPException(500, f"Failed to get extension tables: {str(e)}")

@router.post("/extensions/{extension_id}/tables/{table_name}/translations/bulk")
async def bulk_update_translations(
    extension_id: int,
    table_name: str,
    language_code: str,
    translation_batch: List[Dict[str, Any]],
    db: AsyncSession = Depends(get_db_session)
):
    """Bulk update translations for multiple records"""
    
    try:
        translation_engine = UniversalTranslationEngine(db)
        result = await translation_engine.bulk_update_translations(
            extension_id, table_name, language_code, translation_batch
        )
        
        return result
        
    except TableNotRegisteredError:
        raise HTTPException(404, "Table not registered for translations")
    except ValidationError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to bulk update translations: {str(e)}")

@router.get("/search")
async def search_translatable_content(
    extension_id: int = Query(..., description="Extension ID"),
    table_name: str = Query(..., description="Table name to search in"),
    search_term: str = Query(..., description="Search term"),
    language_code: str = Query(default="en", description="Language to search in"),
    db: AsyncSession = Depends(get_db_session)
):
    """Search for records with specific content in translations"""
    
    try:
        translation_engine = UniversalTranslationEngine(db)
        results = await translation_engine.search_translatable_content(
            extension_id, table_name, search_term, language_code
        )
        
        return {"results": results}
        
    except TableNotRegisteredError:
        raise HTTPException(404, "Table not registered for translations")

@router.get("/languages")
async def get_available_languages(
    extension_id: int = Query(default=None, description="Filter by extension ID"),
    db: AsyncSession = Depends(get_db_session)
):
    """Get list of available language codes"""
    
    try:
        translation_engine = UniversalTranslationEngine(db)
        languages = await translation_engine.get_available_languages(extension_id)
        
        return {"languages": languages}
        
    except Exception as e:
        raise HTTPException(500, f"Failed to get available languages: {str(e)}")

# Menu-specific endpoints (for your original problem)
@router.get("/menus/{menu_id}")
async def get_multilingual_menu(
    menu_id: int,
    language: str = Query(default="en", description="Language code for menu translations"),
    db: AsyncSession = Depends(get_db_session)
):
    """Get menu with translations (solves your original menu_config problem)"""
    
    try:
        translation_engine = UniversalTranslationEngine(db)
        
        # Get menu with translations
        menu_data = await translation_engine.get_translated_record(
            extension_id=1,  # System extension
            table_name="menus",
            record_id=menu_id,
            language_code=language
        )
        
        if not menu_data:
            raise HTTPException(404, "Menu not found")
        
        # Return clean menu structure with translations applied
        return {
            "id": menu_data["id"],
            "name": menu_data.get("name", ""),
            "items": menu_data.get("items", []),
            "is_active": menu_data.get("is_active", False),
            "language": language,
            "structure": menu_data.get("structure", {})
        }
        
    except TableNotRegisteredError:
        raise HTTPException(404, "Menu system not initialized")
    except Exception as e:
        raise HTTPException(500, f"Failed to get menu: {str(e)}")

@router.put("/menus/{menu_id}/translations/{language_code}")
async def update_menu_translations(
    menu_id: int,
    language_code: str,
    translation_data: dict,
    db: AsyncSession = Depends(get_db_session)
):
    """Update menu translations for specific language"""
    
    try:
        translation_engine = UniversalTranslationEngine(db)
        await translation_engine.update_translations(
            extension_id=1,  # System extension
            table_name="menus",
            record_id=menu_id,
            language_code=language_code,
            translations=translation_data
        )
        
        return {"message": "Menu translations updated successfully"}
        
    except TableNotRegisteredError:
        raise HTTPException(404, "Menu system not initialized")
    except ValidationError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to update menu translations: {str(e)}")

@router.get("/menus/{menu_id}/coverage")
async def get_menu_translation_coverage(
    menu_id: int,
    db: AsyncSession = Depends(get_db_session)
):
    """Get translation coverage statistics for menu"""
    
    try:
        translation_engine = UniversalTranslationEngine(db)
        coverage = await translation_engine.get_table_coverage(
            extension_id=1,
            table_name="menus"
        )
        
        return {
            "menu_id": menu_id,
            "coverage": coverage
        }
        
    except TableNotRegisteredError:
        raise HTTPException(404, "Menu system not initialized")
    except Exception as e:
        raise HTTPException(500, f"Failed to get menu coverage: {str(e)}")

# Settings-specific endpoints
@router.get("/settings/{setting_id}")
async def get_multilingual_setting(
    setting_id: int,
    language: str = Query(default="en", description="Language code for setting translations"),
    db: AsyncSession = Depends(get_db_session)
):
    """Get setting with translations"""
    
    try:
        translation_engine = UniversalTranslationEngine(db)
        
        # Check if setting is translatable
        from sqlalchemy import select
        from backend.db.settings import Settings
        
        setting_result = await db.execute(
            select(Settings).where(Settings.id == setting_id)
        )
        setting = setting_result.scalar_one_or_none()
        
        if not setting:
            raise HTTPException(404, "Setting not found")
        
        if not setting.is_translatable:
            # Return base setting without translations
            return {
                "id": setting.id,
                "key": setting.key,
                "value": setting.value,
                "description": setting.description,
                "language": language,
                "translatable": False
            }
        
        # Get translated setting
        translation = await translation_engine.get_table_translation(
            extension_id=1,  # System extension
            table_name="settings",
            record_id=setting_id,
            language_code=language
        )
        
        return {
            "id": setting.id,
            "key": setting.key,
            "value": translation.translation_data.get("value", setting.value) if translation else setting.value,
            "description": translation.translation_data.get("description", setting.description) if translation else setting.description,
            "language": language,
            "translatable": True,
            "has_translation": translation is not None
        }
        
    except Exception as e:
        raise HTTPException(500, f"Failed to get setting: {str(e)}")

@router.put("/settings/{setting_id}/translations/{language_code}")
async def update_setting_translations(
    setting_id: int,
    language_code: str,
    translation_data: dict,
    db: AsyncSession = Depends(get_db_session)
):
    """Update setting translations for specific language"""
    
    try:
        translation_engine = UniversalTranslationEngine(db)
        await translation_engine.update_translations(
            extension_id=1,  # System extension
            table_name="settings",
            record_id=setting_id,
            language_code=language_code,
            translations=translation_data
        )
        
        return {"message": "Setting translations updated successfully"}
        
    except TableNotRegisteredError:
        raise HTTPException(404, "Settings system not initialized")
    except ValidationError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to update setting translations: {str(e)}")