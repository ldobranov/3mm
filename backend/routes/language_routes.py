"""
Language pack management routes
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import json
import os
from pathlib import Path

from backend.database import get_db
from backend.db.language_pack import LanguagePack
from backend.db.extension import Extension
from backend.utils.i18n import i18n_manager, set_language, get_current_language
from backend.utils.auth_dep import require_user
from backend.db.user import User
from typing import Dict, Any
from pathlib import Path

router = APIRouter()


@router.get("/language-packs")
async def get_language_packs(db: Session = Depends(get_db)):
    """Get all installed language packs"""
    try:
        language_packs = db.query(LanguagePack).filter(
            LanguagePack.is_active == True
        ).all()
        
        return {
            "language_packs": [pack.to_dict() for pack in language_packs],
            "current_language": get_current_language()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching language packs: {str(e)}")


@router.get("/language-packs/{language_code}")
async def get_language_pack(language_code: str, db: Session = Depends(get_db)):
    """Get a specific language pack by code"""
    try:
        language_pack = db.query(LanguagePack).filter(
            LanguagePack.code == language_code,
            LanguagePack.is_active == True
        ).first()
        
        if not language_pack:
            raise HTTPException(status_code=404, detail="Language pack not found")
        
        return language_pack.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching language pack: {str(e)}")


@router.post("/language-packs/{language_code}/activate")
async def activate_language_pack(
    language_code: str,
    db: Session = Depends(get_db)
):
    """Activate a language pack and set it as current"""
    try:
        # Get the language pack
        language_pack = db.query(LanguagePack).filter(
            LanguagePack.code == language_code,
            LanguagePack.is_active == True
        ).first()
        
        if not language_pack:
            raise HTTPException(status_code=404, detail="Language pack not found")
        
        # Load translations into i18n manager
        if language_pack.frontend_translations:
            i18n_manager.translations[language_code] = {
                **i18n_manager.translations.get("en", {}),  # Start with English as base
                **language_pack.frontend_translations
            }
        
        if language_pack.backend_translations:
            i18n_manager.translations[language_code] = {
                **i18n_manager.translations.get(language_code, {}),
                **language_pack.backend_translations
            }
        
        if language_pack.extensions_translations:
            i18n_manager.translations[language_code] = {
                **i18n_manager.translations.get(language_code, {}),
                **language_pack.extensions_translations
            }
        
        # Set as current language
        set_language(language_code)
        
        return {
            "message": f"Language pack '{language_pack.name}' activated successfully",
            "language_code": language_code,
            "language_name": language_pack.name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error activating language pack: {str(e)}")


@router.get("/translations/{language_code}")
async def get_translations(language_code: str, db: Session = Depends(get_db)):
    """Get all translations for a specific language"""
    try:
        language_pack = db.query(LanguagePack).filter(
            LanguagePack.code == language_code,
            LanguagePack.is_active == True
        ).first()
        
        if not language_pack:
            # Return empty translations if language pack not found
            return {
                "language_code": language_code,
                "frontend": {},
                "backend": {},
                "extensions": {}
            }
        
        return {
            "language_code": language_code,
            "frontend": language_pack.frontend_translations or {},
            "backend": language_pack.backend_translations or {},
            "extensions": language_pack.extensions_translations or {}
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching translations: {str(e)}")


@router.post("/language-packs/{extension_id}/install")
async def install_language_pack_from_extension(
    extension_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_user)
):
    """Install a language pack from an extension"""
    try:
        # Get the extension
        extension = db.query(Extension).filter(Extension.id == extension_id).first()
        
        if not extension:
            raise HTTPException(status_code=404, detail="Extension not found")
        
        if extension.type != "language":
            raise HTTPException(status_code=400, detail="Extension is not a language pack")
        
        # Parse manifest
        manifest = extension.manifest
        if not manifest:
            raise HTTPException(status_code=400, detail="Extension manifest is missing")
        
        # Create language pack from manifest
        language_pack = LanguagePack.from_manifest(manifest, extension_id)
        
        # Load translation files from extension directory
        extension_path = Path(extension.file_path)
        if extension_path.exists():
            # Extract extension if it's a zip file
            if extension_path.suffix == '.zip':
                import zipfile
                with zipfile.ZipFile(extension_path, 'r') as zip_ref:
                    extract_path = extension_path.parent / f"{extension.name}_{extension.version}"
                    zip_ref.extractall(extract_path)
                    extension_path = extract_path
            
            # Load translations from frontend/ and backend/ subdirectories (new structure)
            print(f"Loading translations from extension path: {extension_path}")
            
            # Load frontend translations
            frontend_dir = extension_path / "frontend"
            if frontend_dir.exists():
                print(f"Found frontend directory: {frontend_dir}")
                frontend_data = {}
                for json_file in frontend_dir.glob("*.json"):
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        # Merge frontend translations
                        frontend_data.update(data)
                        print(f"Loaded frontend file {json_file.name}: {len(data)} keys")
                    except Exception as e:
                        print(f"Error loading frontend file {json_file}: {e}")
                
                if frontend_data:
                    language_pack.frontend_translations = frontend_data
                    print(f"Set frontend translations: {len(frontend_data)} total keys")
            
            # Load backend translations
            backend_dir = extension_path / "backend"
            if backend_dir.exists():
                print(f"Found backend directory: {backend_dir}")
                backend_data = {}
                for json_file in backend_dir.glob("*.json"):
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        # Merge backend translations
                        backend_data.update(data)
                        print(f"Loaded backend file {json_file.name}: {len(data)} keys")
                    except Exception as e:
                        print(f"Error loading backend file {json_file}: {e}")
                
                if backend_data:
                    language_pack.backend_translations = backend_data
                    print(f"Set backend translations: {len(backend_data)} total keys")
            
            # Also try old structure for compatibility
            translations_dir = extension_path / "translations"
            if translations_dir.exists():
                for json_file in translations_dir.glob("*.json"):
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        filename = json_file.stem
                        if filename == "frontend" and not language_pack.frontend_translations:
                            language_pack.frontend_translations = data
                        elif filename == "backend" and not language_pack.backend_translations:
                            language_pack.backend_translations = data
                        elif filename == "extensions":
                            language_pack.extensions_translations = data
                    except Exception as e:
                        print(f"Error loading legacy translation file {json_file}: {e}")
            
            # Set coverage based on loaded translations
            if language_pack.frontend_translations:
                language_pack.frontend_coverage = min(95, len(language_pack.frontend_translations))
            if language_pack.backend_translations:
                language_pack.backend_coverage = min(80, len(language_pack.backend_translations))
        
        # Add to database
        db.add(language_pack)
        db.commit()
        db.refresh(language_pack)
        
        return {
            "message": f"Language pack '{language_pack.name}' installed successfully",
            "language_pack": language_pack.to_dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error installing language pack: {str(e)}")


@router.delete("/language-packs/{language_code}")
async def uninstall_language_pack(
    language_code: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(require_user)
):
    """Uninstall a language pack"""
    try:
        # Don't allow uninstalling the default language
        if language_code == "en":
            raise HTTPException(status_code=400, detail="Cannot uninstall default English language pack")

        language_pack = db.query(LanguagePack).filter(
            LanguagePack.code == language_code
        ).first()

        if not language_pack:
            raise HTTPException(status_code=404, detail="Language pack not found")

        # If this is an extension-based language pack, delete the extension instead
        if language_pack.extension_id:
            from backend.routes.extension_routes import delete_extension
            # Call the extension delete function
            return await delete_extension(language_pack.extension_id, db, current_user)
        else:
            # For non-extension language packs, just deactivate
            language_pack.is_active = False
            db.commit()

            return {
                "message": f"Language pack '{language_pack.name}' uninstalled successfully"
            }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error uninstalling language pack: {str(e)}")


@router.get("/extensions/{extension_name}/translations/{language_code}")
async def get_extension_translations(extension_name: str, language_code: str, db: Session = Depends(get_db)):
    """Get translations for a specific extension in a specific language"""
    try:
        # Find the extension
        extension = db.query(Extension).filter(
            Extension.name == extension_name,
            Extension.is_enabled == True
        ).first()

        if not extension:
            raise HTTPException(status_code=404, detail="Extension not found or not enabled")

        # Check if extension supports this language
        manifest = extension.manifest
        if not (isinstance(manifest, dict) and manifest.get('locales', {}).get('supported', [])):
            raise HTTPException(status_code=400, detail="Extension does not support locales")

        supported_languages = manifest['locales']['supported']
        if language_code not in supported_languages:
            raise HTTPException(status_code=400, detail=f"Extension does not support language: {language_code}")

        # Load translations from extension directory
        extension_path = Path(extension.file_path)
        locales_dir = extension_path / "locales"
        translation_file = locales_dir / f"{language_code}.json"

        if not translation_file.exists():
            return {}  # Return empty translations if file doesn't exist

        import json
        with open(translation_file, 'r', encoding='utf-8') as f:
            translations = json.load(f)

        return {
            "extension_name": extension_name,
            "language_code": language_code,
            "translations": translations
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting extension translations: {str(e)}")


@router.get("/language/available")
async def get_available_languages(db: Session = Depends(get_db)):
    """Get list of available languages from enabled extensions and language packs"""
    try:
        available_languages = ["en"]  # English is always available

        # Get languages from enabled language packs
        language_packs = db.query(LanguagePack).filter(
            LanguagePack.is_active == True
        ).all()

        for pack in language_packs:
            if pack.code not in available_languages:
                available_languages.append(pack.code)

        # Get languages from enabled extensions that support locales
        extensions = db.query(Extension).filter(
            Extension.is_enabled == True,
            Extension.type.in_(["extension", "language"])
        ).all()

        for ext in extensions:
            if ext.manifest and isinstance(ext.manifest, dict):
                locales = ext.manifest.get("locales", {})
                supported = locales.get("supported", [])
                for lang in supported:
                    if lang not in available_languages:
                        available_languages.append(lang)

        return {
            "languages": available_languages,
            "default": "en"
        }

    except Exception as e:
        # Fallback to just English if there's an error
        return {
            "languages": ["en"],
            "default": "en"
        }


@router.get("/current-language")
async def get_current_language_info(db: Session = Depends(get_db)):
    """Get information about the current language"""
    try:
        current_lang = get_current_language()
        language_pack = db.query(LanguagePack).filter(
            LanguagePack.code == current_lang,
            LanguagePack.is_active == True
        ).first()

        if language_pack:
            return {
                "code": current_lang,
                "name": language_pack.name,
                "native_name": language_pack.native_name,
                "locale": language_pack.locale,
                "direction": language_pack.direction,
                "coverage": {
                    "frontend": language_pack.frontend_coverage,
                    "backend": language_pack.backend_coverage,
                    "extensions": language_pack.extensions_coverage
                }
            }
        else:
            # Default Bulgarian (if available) or English
            bg_pack = db.query(LanguagePack).filter(
                LanguagePack.code == "bg",
                LanguagePack.is_active == True
            ).first()

            if bg_pack:
                return {
                    "code": "bg",
                    "name": bg_pack.name,
                    "native_name": bg_pack.native_name,
                    "locale": bg_pack.locale,
                    "direction": bg_pack.direction,
                    "coverage": {
                        "frontend": bg_pack.frontend_coverage,
                        "backend": bg_pack.backend_coverage,
                        "extensions": bg_pack.extensions_coverage
                    }
                }
            else:
                # Fallback to English if Bulgarian not available
                return {
                    "code": "en",
                    "name": "English",
                    "native_name": "English",
                    "locale": "en-US",
                    "direction": "ltr",
                    "coverage": {
                        "frontend": 100,
                        "backend": 100,
                        "extensions": 100
                    }
                }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting current language: {str(e)}")