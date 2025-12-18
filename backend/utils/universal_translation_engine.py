"""
Universal Translation Engine - Core multilingual system for extension-agnostic translations
"""

import json
import re
from typing import Dict, List, Optional, Any, Union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from backend.db.universal_translation import ExtensionTable, TableTranslation, ExtensionField
from backend.db.extension import Extension
from backend.utils.db_utils import get_db_session


class TableNotRegisteredError(Exception):
    """Raised when trying to access unregistered table"""
    pass


class ValidationError(Exception):
    """Raised when validation fails"""
    pass


class ExtensionTableRegistry:
    """Registry for tracking extension-created tables and their multilingual capabilities"""
    
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
    
    async def register_table(self, extension_id: int, table_name: str, schema: Dict[str, Any],
                           translatable_fields: List[str], primary_key: str = "id",
                           is_multilingual: bool = None):
        """Register a new extension table with multilingual capabilities"""
        
        # Determine if multilingual
        if is_multilingual is None:
            is_multilingual = len(translatable_fields) > 0
        
        # Check if table already exists
        existing = await self.db_session.execute(
            select(ExtensionTable).where(
                ExtensionTable.extension_id == extension_id,
                ExtensionTable.table_name == table_name
            )
        )
        
        if existing.scalar_one_or_none():
            # Update existing record
            table_record = existing.scalar_one()
            table_record.table_schema = schema
            table_record.translatable_fields = translatable_fields
            table_record.primary_key_field = primary_key
            table_record.is_multilingual = is_multilingual
        else:
            # Create new record
            table_record = ExtensionTable(
                extension_id=extension_id,
                table_name=table_name,
                table_schema=schema,
                translatable_fields=translatable_fields,
                primary_key_field=primary_key,
                is_multilingual=is_multilingual
            )
            self.db_session.add(table_record)
        
        await self.db_session.commit()
        return table_record
    
    async def register_field(self, extension_id: int, table_name: str, field_name: str,
                           field_type: str, is_translatable: bool = False,
                           validation_rules: Dict = None, field_order: int = 0):
        """Register individual field for an extension table"""
        
        # Check if field already exists
        existing = await self.db_session.execute(
            select(ExtensionField).where(
                ExtensionField.extension_id == extension_id,
                ExtensionField.table_name == table_name,
                ExtensionField.field_name == field_name
            )
        )
        
        if existing.scalar_one_or_none():
            # Update existing field
            field_record = existing.scalar_one()
            field_record.field_type = field_type
            field_record.is_translatable = is_translatable
            field_record.validation_rules = validation_rules or {}
            field_record.field_order = field_order
        else:
            # Create new field record
            field_record = ExtensionField(
                extension_id=extension_id,
                table_name=table_name,
                field_name=field_name,
                field_type=field_type,
                is_translatable=is_translatable,
                validation_rules=validation_rules or {},
                field_order=field_order
            )
            self.db_session.add(field_record)
        
        await self.db_session.commit()
        return field_record
    
    async def get_extension_tables(self, extension_id: int) -> List[ExtensionTable]:
        """Get all tables for an extension"""
        result = await self.db_session.execute(
            select(ExtensionTable).where(ExtensionTable.extension_id == extension_id)
        )
        return result.scalars().all()
    
    async def get_translatable_fields(self, extension_id: int, table_name: str) -> List[str]:
        """Get list of translatable fields for a table"""
        table_record = await self.get_table_record(extension_id, table_name)
        return table_record.translatable_fields if table_record else []
    
    async def get_table_record(self, extension_id: int, table_name: str) -> Optional[ExtensionTable]:
        """Get table registration record"""
        result = await self.db_session.execute(
            select(ExtensionTable).where(
                ExtensionTable.extension_id == extension_id,
                ExtensionTable.table_name == table_name
            )
        )
        return result.scalar_one_or_none()
    
    async def is_table_registered(self, extension_id: int, table_name: str) -> bool:
        """Check if table is registered for translations"""
        return await self.get_table_record(extension_id, table_name) is not None
    
    async def get_multilingual_tables(self, extension_id: int = None) -> List[ExtensionTable]:
        """Get all multilingual tables, optionally filtered by extension"""
        query = select(ExtensionTable).where(ExtensionTable.is_multilingual == True)
        if extension_id:
            query = query.where(ExtensionTable.extension_id == extension_id)
        
        result = await self.db_session.execute(query)
        return result.scalars().all()


class UniversalTranslationEngine:
    """Universal translation system that works with ANY extension table"""
    
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.table_registry = ExtensionTableRegistry(db_session)
    
    async def get_translated_record(self, extension_id: int, table_name: str, 
                                   record_id: int, language_code: str):
        """Get a record with translations merged in"""
        
        # Validate table registration
        if not await self.table_registry.is_table_registered(extension_id, table_name):
            raise TableNotRegisteredError(f"Table {table_name} not registered for translations")
        
        # Get table record for schema info
        table_record = await self.table_registry.get_table_record(extension_id, table_name)
        primary_key = table_record.primary_key_field
        
        # Get base record using raw SQL
        query = text(f"SELECT * FROM {table_name} WHERE {primary_key} = :record_id")
        result = await self.db_session.execute(query, {"record_id": record_id})
        base_record = result.mappings().first()
        
        if not base_record:
            return None
        
        # Convert to dict
        base_dict = dict(base_record)
        
        # Get translations
        translation = await self.get_table_translation(extension_id, table_name, record_id, language_code)
        
        # Merge translations into base record
        if translation:
            merged_record = base_dict.copy()
            for field_name, translated_value in translation.translation_data.items():
                if field_name in base_dict:
                    merged_record[field_name] = translated_value
            return merged_record
        
        return base_dict
    
    async def get_table_translation(self, extension_id: int, table_name: str,
                                  record_id: int, language_code: str) -> Optional[TableTranslation]:
        """Get translation record for a specific table/record/language"""
        result = await self.db_session.execute(
            select(TableTranslation).where(
                TableTranslation.extension_id == extension_id,
                TableTranslation.table_name == table_name,
                TableTranslation.record_id == record_id,
                TableTranslation.language_code == language_code
            )
        )
        return result.scalar_one_or_none()
    
    async def update_translations(self, extension_id: int, table_name: str,
                                record_id: int, language_code: str, translations: Dict[str, Any]):
        """Update translations for a specific record"""

        # Validate translations against registered fields
        translatable_fields = await self.table_registry.get_translatable_fields(extension_id, table_name)

        invalid_fields = set(translations.keys()) - set(translatable_fields)
        if invalid_fields:
            raise ValidationError(f"Cannot translate non-translatable fields: {invalid_fields}")

        # Calculate coverage percentage
        coverage = await self._calculate_translation_coverage(extension_id, table_name, record_id, translations)

        # Update or create translation record
        existing_translation = await self.get_table_translation(extension_id, table_name, record_id, language_code)

        if existing_translation:
            existing_translation.translation_data = translations
            existing_translation.translation_coverage = coverage
        else:
            translation_record = TableTranslation(
                extension_id=extension_id,
                table_name=table_name,
                record_id=record_id,
                language_code=language_code,
                translation_data=translations,
                translation_coverage=coverage
            )
            self.db_session.add(translation_record)

        await self.db_session.commit()

        # Update menu translation status if this is a system table
        await self._update_translation_status(extension_id, table_name, record_id)
    
    async def _calculate_translation_coverage(self, extension_id: int, table_name: str,
                                           record_id: int, new_translations: Dict) -> float:
        """Calculate translation coverage percentage for a record"""
        
        translatable_fields = await self.table_registry.get_translatable_fields(extension_id, table_name)
        if not translatable_fields:
            return 100.0
        
        # Get existing translations
        result = await self.db_session.execute(
            select(TableTranslation).where(
                TableTranslation.extension_id == extension_id,
                TableTranslation.table_name == table_name,
                TableTranslation.record_id == record_id
            )
        )
        all_translations = result.scalars().all()
        
        # Count unique fields that have translations across all languages
        translated_fields = set()
        for translation in all_translations:
            translated_fields.update(translation.translation_data.keys())
        
        # Add fields from new translations
        translated_fields.update(new_translations.keys())
        
        # Calculate coverage
        total_translatable = len(translatable_fields)
        currently_translated = len(translated_fields.intersection(set(translatable_fields)))
        
        return round((currently_translated / total_translatable) * 100, 2)
    
    async def _update_translation_status(self, extension_id: int, table_name: str, record_id: int):
        """Update translation status for system tables like menus"""

        if table_name == "menus" and extension_id == 1:  # System extension
            # Check if menu exists and update has_translations flag
            result = await self.db_session.execute(
                text("SELECT id FROM menus WHERE id = :record_id"),
                {"record_id": record_id}
            )
            if result.scalar_one_or_none():
                await self.db_session.execute(
                    text("UPDATE menus SET has_translations = true WHERE id = :record_id"),
                    {"record_id": record_id}
                )
                await self.db_session.commit()
        
    async def get_table_coverage(self, extension_id: int, table_name: str, 
                               language_code: str = None) -> Dict[str, Any]:
        """Get translation coverage statistics for a table"""
        
        if language_code:
            # Get coverage for specific language
            result = await self.db_session.execute(
                select(TableTranslation.translation_coverage).where(
                    TableTranslation.extension_id == extension_id,
                    TableTranslation.table_name == table_name,
                    TableTranslation.language_code == language_code
                )
            )
            coverages = result.scalars().all()
            
            return {
                "language_code": language_code,
                "average_coverage": round(sum(coverages) / len(coverages), 2) if coverages else 0,
                "records_with_translations": len(coverages),
                "coverage_by_record": {i: cov for i, cov in enumerate(coverages)}
            }
        else:
            # Get overall coverage for table
            result = await self.db_session.execute(
                select(TableTranslation.language_code, TableTranslation.translation_coverage).where(
                    TableTranslation.extension_id == extension_id,
                    TableTranslation.table_name == table_name
                )
            )
            all_translations = result.all()
            
            language_coverage = {}
            for lang_code, coverage in all_translations:
                if lang_code not in language_coverage:
                    language_coverage[lang_code] = []
                language_coverage[lang_code].append(coverage)
            
            return {
                "languages": {
                    lang: {
                        "average_coverage": round(sum(coverages) / len(coverages), 2),
                        "records_translated": len(coverages)
                    }
                    for lang, coverages in language_coverage.items()
                },
                "total_languages": len(language_coverage)
            }
    
    async def bulk_update_translations(self, extension_id: int, table_name: str,
                                     language_code: str, translation_batch: List[Dict[str, Any]]):
        """Bulk update translations for multiple records"""
        
        for translation_data in translation_batch:
            record_id = translation_data.pop("record_id")
            translations = translation_data  # Remaining fields are translations
            
            await self.update_translations(
                extension_id, table_name, record_id, language_code, translations
            )
        
        return {"message": f"Bulk updated {len(translation_batch)} records"}
    
    async def get_available_languages(self, extension_id: int = None) -> List[str]:
        """Get list of available language codes"""
        query = select(TableTranslation.language_code).distinct()
        
        if extension_id:
            query = query.where(TableTranslation.extension_id == extension_id)
        
        result = await self.db_session.execute(query)
        return [lang[0] for lang in result.all()]
    
    async def search_translatable_content(self, extension_id: int, table_name: str,
                                        search_term: str, language_code: str = "en") -> List[Dict[str, Any]]:
        """Search for records with specific content in translations"""
        
        if not await self.table_registry.is_table_registered(extension_id, table_name):
            raise TableNotRegisteredError(f"Table {table_name} not registered for translations")
        
        # Get all translations for the table
        result = await self.db_session.execute(
            select(TableTranslation).where(
                TableTranslation.extension_id == extension_id,
                TableTranslation.table_name == table_name,
                TableTranslation.language_code == language_code
            )
        )
        
        translations = result.scalars().all()
        matching_records = []
        
        for translation in translations:
            for field_name, field_value in translation.translation_data.items():
                if isinstance(field_value, str) and search_term.lower() in field_value.lower():
                    matching_records.append({
                        "record_id": translation.record_id,
                        "field_name": field_name,
                        "content": field_value,
                        "language_code": translation.language_code,
                        "coverage": translation.translation_coverage
                    })
                    break  # Don't duplicate record if multiple fields match
        
        return matching_records