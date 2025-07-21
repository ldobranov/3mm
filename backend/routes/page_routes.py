from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.db.page import Page
from backend.database import get_db

router = APIRouter()

@router.get("/{slug}")
def get_page_by_slug(slug: str, db: Session = Depends(get_db)):
    page = Page.get_by_slug(db, slug)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return {"title": page.title, "content": page.content}
