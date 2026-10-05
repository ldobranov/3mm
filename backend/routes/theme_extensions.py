"""Administrator-only lifecycle; theme appearance loading is a separate boundary."""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.user import User
from backend.services.theme_extensions import (
    delete_theme,
    disable_theme,
    enable_theme,
    select_theme,
    theme_appearance,
    theme_catalog,
    theme_package,
    selected_theme_asset,
)
from backend.utils.auth_dep import require_admin
from backend.utils.db_utils import get_db


router = APIRouter(prefix="/themes", tags=["themes"])


class ThemeSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sha256: str | None = Field(..., pattern=r"^[0-9a-f]{64}$")


@router.get("/appearance")
def appearance(response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return theme_appearance(db)


@router.get("/packages/{sha256}/assets/{asset_id}")
def appearance_asset(sha256: str, asset_id: str, db: Session = Depends(get_db)):
    contents, media_type = selected_theme_asset(db, sha256, asset_id)
    return Response(contents, media_type=media_type, headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    })


@router.post("/selection")
def selection(
    request: ThemeSelection,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        return select_theme(db, request.sha256, admin)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Theme selection changed; refresh and retry") from exc


@router.get("/catalog")
def catalog(_admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return theme_catalog(db)


@router.post("/packages/{sha256}/enable")
def enable(
    sha256: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    package = theme_package(db, sha256)
    try:
        return enable_theme(db, package, admin)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Theme lifecycle changed; refresh and retry") from exc


@router.post("/packages/{sha256}/disable")
def disable(
    sha256: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    return disable_theme(db, theme_package(db, sha256), admin)


@router.delete("/packages/{sha256}")
def delete(
    sha256: str, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    return delete_theme(db, theme_package(db, sha256), admin)
