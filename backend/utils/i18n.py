"""
Internationalization (i18n) utilities
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.db.language_pack import LanguagePack

class I18nManager:
    """Manages translations for different languages"""

    def __init__(self):
        self.translations: Dict[str, Dict[str, Any]] = {}
        self.current_language = "bg"  # Default to Bulgarian
        self._default_loaded = False

    def load_language_pack_from_db(self, language_code: str):
        """Load translations for a language from database"""
        try:
            db = next(get_db())
            language_pack = db.query(LanguagePack).filter(
                LanguagePack.code == language_code,
                LanguagePack.is_active == True
            ).first()
            
            if not language_pack:
                print(f"Language pack {language_code} not found in database")
                return False
            
            self.translations[language_code] = {}
            
            # Start with English as base if not exists
            if "en" not in self.translations:
                self.translations["en"] = self._get_default_english_translations()
            
            # Load frontend translations
            if language_pack.frontend_translations:
                self._merge_dict(self.translations[language_code], language_pack.frontend_translations)
            
            # Load backend translations
            if language_pack.backend_translations:
                self._merge_dict(self.translations[language_code], language_pack.backend_translations)
            
            # Load extensions translations
            if language_pack.extensions_translations:
                self._merge_dict(self.translations[language_code], language_pack.extensions_translations)
            
            print(f"Loaded {language_code} translations from database: {len(self.translations[language_code])} keys")
            db.close()
            return True
            
        except Exception as e:
            print(f"Error loading language pack {language_code} from database: {e}")
            return False

    def load_language_pack(self, language_code: str, translations_dir: Path):
        """Load translations for a language from a directory"""
        if not translations_dir.exists():
            print(f"Translations directory not found: {translations_dir}")
            return

        self.translations[language_code] = {}

        # Load all json files in the translations directory
        for json_file in translations_dir.glob("*.json"):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Merge into the language dict
                    self._merge_dict(self.translations[language_code], data)
            except Exception as e:
                print(f"Error loading translation file {json_file}: {e}")

        print(f"Loaded {language_code} translations: {len(self.translations[language_code])} keys")

    def _get_default_english_translations(self) -> Dict[str, Any]:
        """Get default English translations as fallback"""
        return {
            "api": {
                "errors": {
                    "unauthorized": "Unauthorized access",
                    "forbidden": "Access forbidden",
                    "not_found": "Resource not found",
                    "validation_error": "Validation error",
                    "internal_error": "Internal server error",
                    "bad_request": "Bad request",
                    "server_error": "Server error"
                },
                "messages": {
                    "success": "Operation completed successfully",
                    "created": "Resource created successfully",
                    "updated": "Resource updated successfully",
                    "deleted": "Resource deleted successfully",
                    "saved": "Data saved",
                    "loaded": "Data loaded",
                    "exported": "Data exported",
                    "imported": "Data imported"
                }
            },
            "extensions": {
                "messages": {
                    "installed": "Extension installed successfully",
                    "uninstalled": "Extension uninstalled successfully",
                    "enabled": "Extension enabled",
                    "disabled": "Extension disabled",
                    "updated": "Extension updated",
                    "uploaded": "Extension uploaded",
                    "deleted": "Extension deleted"
                }
            },
            "language": {
                "messages": {
                    "detected": "Language automatically detected",
                    "switched": "Language switched to {language}",
                    "loaded": "Language files loaded",
                    "cached": "Translations cached"
                }
            }
        }

    def _merge_dict(self, target: Dict[str, Any], source: Dict[str, Any]):
        """Recursively merge source dict into target"""
        for key, value in source.items():
            if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                self._merge_dict(target[key], value)
            else:
                target[key] = value

    def set_language(self, language_code: str):
        """Set the current language"""
        if language_code == "en":
            self.current_language = language_code
            if not self._default_loaded:
                self.translations["en"] = self._get_default_english_translations()
                self._default_loaded = True
        elif language_code in self.translations:
            self.current_language = language_code
        else:
            # Try to load from database
            if self.load_language_pack_from_db(language_code):
                self.current_language = language_code
            else:
                print(f"Language {language_code} not available, falling back to en")
                self.current_language = "en"
                if not self._default_loaded:
                    self.translations["en"] = self._get_default_english_translations()
                    self._default_loaded = True

    def get(self, key: str, default: str = None, language: str = None) -> str:
        """Get a translated string"""
        lang = language or self.current_language

        # Try the specified language
        if lang in self.translations:
            value = self._get_nested_value(self.translations[lang], key)
            if value is not None:
                return value

        # Fallback to English (default)
        if lang != "en" and "en" in self.translations:
            value = self._get_nested_value(self.translations["en"], key)
            if value is not None:
                return value

        # Return default or the key itself
        return default or key

    def _get_nested_value(self, data: Dict[str, Any], key: str) -> Optional[str]:
        """Get a nested value from dict using dot notation"""
        keys = key.split('.')
        current = data

        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return None

        return current if isinstance(current, str) else None

    def get_current_language(self) -> str:
        """Get the current language code"""
        return self.current_language

    def get_available_languages(self) -> list:
        """Get list of available language codes"""
        try:
            db = next(get_db())
            language_packs = db.query(LanguagePack.code).filter(
                LanguagePack.is_active == True
            ).all()
            db.close()

            codes = [pack.code for pack in language_packs]
            # Always include English
            if "en" not in codes:
                codes.append("en")
            return codes
        except Exception as e:
            print(f"Error getting available languages: {e}")
            # Fallback to loaded translations
            return list(self.translations.keys()) + ["en"]

# Global instance
i18n_manager = I18nManager()

# Convenience functions
def _(key: str, default: str = None, language: str = None) -> str:
    """Translate a key"""
    return i18n_manager.get(key, default, language)

def set_language(language_code: str):
    """Set the current language"""
    i18n_manager.set_language(language_code)

def get_current_language() -> str:
    """Get the current language"""
    return i18n_manager.get_current_language()