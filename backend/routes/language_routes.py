"""Current data-only language package lifecycle and public translations."""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from backend.db.user import User
from backend.services.language_extensions import available_languages, catalog, delete_package, language_package, set_enabled, translations
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db

router = APIRouter()

@router.get("/translations/{language_code}")
def read_translations(language_code: str, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return translations(db, language_code)

@router.get("/v1/modules/languages/catalog")
def language_catalog(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return catalog(db)

@router.post("/v1/modules/languages/packages/{sha256}/{action}")
def lifecycle(sha256: str, action: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from fastapi import HTTPException
    if action not in {"enable", "disable"}:
        raise HTTPException(404, "Language action was not found")
    package = language_package(db, sha256)
    try:
        return set_enabled(db, package, action == "enable", admin)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Language selection changed; refresh and retry") from exc

@router.delete("/v1/modules/languages/packages/{sha256}")
def delete(sha256: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return delete_package(db, language_package(db, sha256), admin)
