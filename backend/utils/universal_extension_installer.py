"""
Universal Extension Installer - Enhanced with multilingual support
"""

import json
import re
from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from backend.utils.extension_table_creator import ExtensionTableCreator, ECommerceExtensionTableCreator
from backend.utils.universal_translation_engine import UniversalTranslationEngine, ExtensionTableRegistry
from backend.db.language_pack import LanguagePack


class UniversalExtensionInstaller:
    """Install any type of extension with automatic multilingual support"""
    
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.translation_engine = UniversalTranslationEngine(db_session)
        self.table_registry = ExtensionTableRegistry(db_session)
        self.table_creator = ExtensionTableCreator(db_session, self.translation_engine)
    
    async def install_extension(self, extension_package: Dict[str, Any], extension_id: int) -> Dict[str, Any]:
        """Install any extension type with multilingual support"""
        
        extension_type = extension_package.get("type", "basic")
        extension_name = extension_package.get("name", "Unknown Extension")
        
        print(f"🔧 Installing {extension_type} extension: {extension_name}")
        
        try:
            if extension_type == "language_pack":
                result = await self._install_language_pack(extension_package, extension_id)
            elif extension_type == "ecommerce":
                result = await self._install_ecommerce_extension(extension_package, extension_id)
            elif extension_type == "pos_system":
                result = await self._install_pos_extension(extension_package, extension_id)
            else:
                result = await self._install_basic_extension(extension_package, extension_id)
            
            print(f"✅ Successfully installed {extension_name}")
            return result
            
        except Exception as e:
            print(f"❌ Failed to install {extension_name}: {str(e)}")
            raise Exception(f"Installation failed: {str(e)}")
    
    async def _install_language_pack(self, package: Dict[str, Any], extension_id: int) -> Dict[str, Any]:
        """Install language pack with automatic translation application"""
        
        # Create language pack record
        language_info = package["language"]
        language_pack = LanguagePack(
            name=package["name"],
            code=language_info["code"],
            native_name=language_info["nativeName"],
            extension_id=extension_id
        )
        
        self.db_session.add(language_pack)
        await self.db_session.commit()
        await self.db_session.refresh(language_pack)
        
        print(f"🌍 Created language pack: {language_info['name']} ({language_info['code']})")
        
        # Apply translations from the language pack
        translations = package.get("translations", {})
        
        if translations:
            print(f"📝 Applying {len(translations)} translation categories...")
            
            # System menu translations
            if "system_menus" in translations:
                await self._apply_system_menu_translations(
                    translations["system_menus"], language_info["code"]
                )
            
            # Settings translations
            if "settings" in translations:
                await self._apply_settings_translations(
                    translations["settings"], language_info["code"]
                )
            
            # Extension-specific translations
            if "extension_translations" in translations:
                await self._apply_extension_translations(
                    translations["extension_translations"], language_info["code"]
                )
            
            # Frontend/backend translations
            if "frontend" in translations:
                await self._apply_ui_translations(
                    translations["frontend"], language_info["code"], "frontend"
                )
            
            if "backend" in translations:
                await self._apply_ui_translations(
                    translations["backend"], language_info["code"], "backend"
                )
        
        return {
            "status": "installed",
            "language_pack_id": language_pack.id,
            "language_code": language_info["code"],
            "translations_applied": bool(translations)
        }
    
    async def _apply_system_menu_translations(self, menu_translations: Dict[str, Any], language_code: str):
        """Apply translations to system menus"""
        
        print(f"🍽️  Applying menu translations for {language_code}")
        
        # Handle menu_translations for backward compatibility
        if "menu_translations" in menu_translations:
            for menu_id, menu_translation in menu_translations["menu_translations"].items():
                try:
                    await self.translation_engine.update_translations(
                        extension_id=1,  # System extension ID
                        table_name="menus",
                        record_id=int(menu_id),
                        language_code=language_code,
                        translations=menu_translation
                    )
                    print(f"  ✅ Menu {menu_id} translated")
                except Exception as e:
                    print(f"  ❌ Failed to translate menu {menu_id}: {str(e)}")
    
    async def _apply_settings_translations(self, settings_translations: Dict[str, Any], language_code: str):
        """Apply translations to system settings"""
        
        print(f"⚙️  Applying settings translations for {language_code}")
        
        # This would apply translations to system settings
        # For now, just log that we received them
        print(f"  📋 Settings translations ready for {len(settings_translations)} settings")
    
    async def _apply_extension_translations(self, extension_translations: Dict[str, Any], language_code: str):
        """Apply translations to other extension tables"""
        
        print(f"🔌 Applying extension translations for {language_code}")
        
        for ext_name, ext_translations in extension_translations.items():
            try:
                # Find extension ID by name
                result = await self.db_session.execute(
                    select(text("id")).select_from(text("extensions")).where(text(f"name = '{ext_name}'"))
                )
                target_extension = result.fetchone()
                
                if target_extension:
                    extension_id = target_extension[0]
                    
                    for table_name, table_translations in ext_translations.items():
                        for record_translation in table_translations:
                            # Handle different record formats
                            if "product_id" in record_translation:
                                record_id = record_translation["product_id"]
                            elif "id" in record_translation:
                                record_id = record_translation["id"]
                            else:
                                continue
                            
                            await self.translation_engine.update_translations(
                                extension_id=extension_id,
                                table_name=table_name,
                                record_id=record_id,
                                language_code=language_code,
                                translations=record_translation.get("translations", {})
                            )
                    
                    print(f"  ✅ Extension {ext_name} translated")
                else:
                    print(f"  ⚠️  Extension {ext_name} not found for translations")
                    
            except Exception as e:
                print(f"  ❌ Failed to translate extension {ext_name}: {str(e)}")
    
    async def _apply_ui_translations(self, ui_translations: Dict[str, Any], language_code: str, ui_type: str):
        """Apply frontend/backend UI translations"""
        
        print(f"🖥️  Applying {ui_type} translations for {language_code}")
        
        # Store UI translations for the frontend/backend to use
        # This would typically go to a separate file or cache system
        print(f"  📱 {ui_type.capitalize()} translations ready for {len(ui_translations)} categories")
    
    async def _install_ecommerce_extension(self, package: Dict[str, Any], extension_id: int) -> Dict[str, Any]:
        """Install e-commerce extension with multilingual tables"""
        
        print(f"🛒 Installing e-commerce extension: {package.get('name', 'Unknown Store')}")
        
        # Use specialized e-commerce table creator
        ecommerce_creator = ECommerceExtensionTableCreator(self.db_session, self.translation_engine)
        
        # Create e-commerce tables
        created_tables = await ecommerce_creator.create_ecommerce_tables(extension_id)
        print(f"📦 Created {len(created_tables)} e-commerce tables")
        
        # Install translations if provided
        if "translations" in package:
            translations = package["translations"]
            
            if "products" in translations:
                await self._install_ecommerce_product_translations(
                    extension_id, translations["products"], package["language"]["code"]
                )
            
            if "categories" in translations:
                await self._install_ecommerce_category_translations(
                    extension_id, translations["categories"], package["language"]["code"]
                )
        
        return {
            "status": "installed",
            "extension_id": extension_id,
            "tables_created": created_tables,
            "multilingual_enabled": True
        }
    
    async def _install_ecommerce_product_translations(self, extension_id: int, product_translations: List[Dict], language_code: str):
        """Install e-commerce product translations"""
        
        print(f"🛍️  Installing product translations for {language_code}")
        
        for product in product_translations:
            try:
                # Create translation data
                translation_data = {
                    "name": product.get("name", ""),
                    "description": product.get("description", ""),
                    "short_description": product.get("short_description", "")
                }
                
                await self.translation_engine.update_translations(
                    extension_id=extension_id,
                    table_name="store_products",
                    record_id=product["product_id"],
                    language_code=language_code,
                    translations=translation_data
                )
                
                print(f"  ✅ Product {product['product_id']} translated")
                
            except Exception as e:
                print(f"  ❌ Failed to translate product {product.get('product_id', 'unknown')}: {str(e)}")
    
    async def _install_ecommerce_category_translations(self, extension_id: int, category_translations: List[Dict], language_code: str):
        """Install e-commerce category translations"""
        
        print(f"📂 Installing category translations for {language_code}")
        
        for category in category_translations:
            try:
                translation_data = {
                    "name": category.get("name", ""),
                    "description": category.get("description", "")
                }
                
                await self.translation_engine.update_translations(
                    extension_id=extension_id,
                    table_name="store_categories",
                    record_id=category["category_id"],
                    language_code=language_code,
                    translations=translation_data
                )
                
                print(f"  ✅ Category {category['category_id']} translated")
                
            except Exception as e:
                print(f"  ❌ Failed to translate category {category.get('category_id', 'unknown')}: {str(e)}")
    
    async def _install_pos_extension(self, package: Dict[str, Any], extension_id: int) -> Dict[str, Any]:
        """Install POS system extension"""
        
        print(f"💰 Installing POS system extension: {package.get('name', 'Unknown POS')}")
        
        # POS systems need different tables (products, inventory, transactions, etc.)
        pos_tables = [
            {
                "name": "pos_products",
                "primary_key": "product_id",
                "fields": {
                    "product_id": {"type": "serial", "primary_key": True},
                    "barcode": {"type": "varchar", "multilingual": False},
                    "price": {"type": "decimal", "multilingual": False},
                    "name": {"type": "varchar", "multilingual": True},
                    "description": {"type": "text", "multilingual": True}
                }
            },
            {
                "name": "pos_transactions", 
                "primary_key": "transaction_id",
                "fields": {
                    "transaction_id": {"type": "serial", "primary_key": True},
                    "total_amount": {"type": "decimal", "multilingual": False},
                    "payment_method": {"type": "varchar", "multilingual": False}
                }
            }
        ]
        
        created_tables = await self.table_creator.create_extension_tables(extension_id, pos_tables)
        
        return {
            "status": "installed",
            "extension_id": extension_id,
            "tables_created": created_tables,
            "multilingual_enabled": True
        }
    
    async def _install_basic_extension(self, package: Dict[str, Any], extension_id: int) -> Dict[str, Any]:
        """Install basic extension"""
        
        print(f"🔧 Installing basic extension: {package.get('name', 'Unknown')}")
        
        # Handle basic extensions with database tables
        if "database" in package and "tables" in package["database"]:
            created_tables = await self.table_creator.create_extension_tables(
                extension_id, package["database"]["tables"]
            )
            
            # Install translations if provided
            if "translations" in package:
                translations = package["translations"]
                if "data" in translations:
                    # Apply translations to extension tables
                    for table_translations in translations["data"]:
                        # Handle extension-specific translation format
                        pass
            
            return {
                "status": "installed",
                "extension_id": extension_id,
                "tables_created": created_tables,
                "multilingual_enabled": bool(package.get("translations"))
            }
        else:
            # No database tables, just basic extension
            return {
                "status": "installed", 
                "extension_id": extension_id,
                "tables_created": [],
                "multilingual_enabled": False
            }
    
    async def uninstall_extension(self, extension_id: int) -> Dict[str, Any]:
        """Uninstall extension and clean up its tables and translations"""
        
        print(f"🗑️  Uninstalling extension {extension_id}")
        
        try:
            # Get all tables for this extension
            extension_tables = await self.table_registry.get_extension_tables(extension_id)
            
            # Drop tables
            for table in extension_tables:
                try:
                    await self.db_session.execute(
                        text(f"DROP TABLE IF EXISTS {table.table_name}")
                    )
                    print(f"  🗑️  Dropped table: {table.table_name}")
                except Exception as e:
                    print(f"  ⚠️  Failed to drop table {table.table_name}: {str(e)}")
            
            # Clean up translation records
            await self.db_session.execute(
                text("DELETE FROM table_translations WHERE extension_id = :extension_id"),
                {"extension_id": extension_id}
            )
            
            await self.db_session.execute(
                text("DELETE FROM extension_tables WHERE extension_id = :extension_id"),
                {"extension_id": extension_id}
            )
            
            await self.db_session.execute(
                text("DELETE FROM extension_fields WHERE extension_id = :extension_id"),
                {"extension_id": extension_id}
            )
            
            await self.db_session.commit()
            
            return {
                "status": "uninstalled",
                "tables_removed": len(extension_tables),
                "translations_cleaned": True
            }
            
        except Exception as e:
            print(f"❌ Failed to uninstall extension {extension_id}: {str(e)}")
            raise Exception(f"Uninstallation failed: {str(e)}")


# Example Bulgarian Language Pack Installation
async def install_bulgarian_language_pack():
    """Example: Install Bulgarian language pack with all translations"""
    
    bulgarian_pack = {
        "name": "BulgarianLanguagePack",
        "version": "1.0.0",
        "type": "language_pack",
        "language": {
            "code": "bg",
            "name": "Bulgarian", 
            "nativeName": "Български"
        },
        "translations": {
            "system_menus": {
                "menu_translations": {
                    "1": {
                        "name": "Главно меню",
                        "items": [
                            {"id": "home", "label": "Начало", "tooltip": "Начална страница"},
                            {"id": "dashboard", "label": "Табло", "tooltip": "Табло за управление"},
                            {"id": "settings", "label": "Настройки", "tooltip": "Настройки на системата"},
                            {"id": "extensions", "label": "Разширения", "tooltip": "Управление на разширенията"},
                            {"id": "security", "label": "Сигурност", "tooltip": "Настройки за сигурност"},
                            {"id": "profile", "label": "Профил", "tooltip": "Моят профил"}
                        ]
                    }
                }
            },
            "settings": {
                "user_preferences": {
                    "theme": "Тема",
                    "language": "Език",
                    "notifications": "Уведомления"
                }
            },
            "frontend": {
                "common": {
                    "save": "Запази",
                    "cancel": "Отказ",
                    "delete": "Изтрий",
                    "edit": "Редактирай",
                    "search": "Търсене"
                },
                "navigation": {
                    "home": "Начало",
                    "dashboard": "Табло",
                    "settings": "Настройки"
                }
            },
            "backend": {
                "admin": {
                    "users": "Потребители",
                    "extensions": "Разширения",
                    "system": "Система"
                }
            }
        }
    }
    
    from backend.utils.db_utils import get_db_session
    
    async for db_session in get_db_session():
        try:
            installer = UniversalExtensionInstaller(db_session)
            result = await installer.install_extension(bulgarian_pack, extension_id=2)
            
            print("\n🎉 Bulgarian Language Pack installed successfully!")
            print(f"Language: {result['language_code']}")
            print(f"Status: {result['status']}")
            
            return result
            
        except Exception as e:
            print(f"\n❌ Failed to install Bulgarian Language Pack: {str(e)}")
            raise
        finally:
            await db_session.close()


if __name__ == "__main__":
    # Example installation
    import asyncio
    asyncio.run(install_bulgarian_language_pack())