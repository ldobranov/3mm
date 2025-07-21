import uuid
import hashlib
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session, joinedload
from backend.db.base import Base
from backend.utils.db_utils import get_db
from typing import Any, Type, List, Union
from pydantic import BaseModel
import logging
from pydantic import ValidationError
from typing_extensions import Annotated
from backend.db.page import Page

def create_crud_routes(model: Any, model_name: str, input_model: Type[BaseModel], update_model: Type[BaseModel] = None, output_model: Type[BaseModel] = None):
    router = APIRouter()
    output_model = output_model or input_model
    update_model = update_model or input_model

    def generate_operation_id(route_type: str, model_name: str, path: str):
        unique_string = f"{route_type}_{model_name}_{path}_{id(model)}"
        unique_hash = hashlib.md5(unique_string.encode()).hexdigest()[:8]  # Shorten hash for readability
        return f"{route_type}_{model_name}_{unique_hash}"

    @router.post(f"/{model_name}/create", operation_id=generate_operation_id("create", model_name, "create"))
    def create_item(item = Body(...), db: Session = Depends(get_db)):
        try:
            # Validate and convert item to pydantic_model instance
            validated_item = input_model(**item.model_dump()) if hasattr(item, "model_dump") else input_model(**item)
            db_item = model(**validated_item.model_dump())
            db.add(db_item)
            db.commit()
            db.refresh(db_item)
            return db_item
        except ValidationError as ve:
            logging.error(f"Validation error for {model_name}: {ve.json()}")
            raise HTTPException(status_code=422, detail=ve.errors())
        except Exception as e:
            logging.error(f"Error creating {model_name}: {e}")
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error creating {model_name}: {e}")

    @router.get(f"/{model_name}/read", operation_id=generate_operation_id("read", model_name, "read"))
    def read_items(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
        try:
            items = db.query(model).offset(skip).limit(limit).all()
            return [
                {
                    column.name: getattr(item, column.name)
                    for column in item.__table__.columns
                }
                for item in items
            ]
        except Exception as e:
            logging.error(f"Error reading {model_name}: {e}")
            raise HTTPException(status_code=500, detail=f"Error reading {model_name}: {e}")

    @router.put(f"/{model_name}/update", operation_id=generate_operation_id("update", model_name, "update"))
    def update_items(payload: Union[dict, List[dict]], db: Session = Depends(get_db)):
        if isinstance(payload, dict):
            payload = [payload]

        for item_data in payload:
            try:
                item = update_model(**item_data)
            except Exception as e:
                logging.error(f"Validation error for item: {item_data}, error: {e}")
                raise HTTPException(status_code=422, detail=f"Invalid payload: {e}")

            try:
                db_item = db.query(model).filter(model.id == item.id).first()
                if not db_item:
                    raise HTTPException(status_code=404, detail=f"{model_name.capitalize()} with id {item.id} not found")

                for key, value in item_data.items():
                    setattr(db_item, key, value)

                db.commit()
                db.refresh(db_item)
            except Exception as e:
                logging.error(f"Error updating {model_name}: {e}")
                db.rollback()
                raise HTTPException(status_code=500, detail=f"Error updating {model_name}: {e}")

        return {"message": f"{model_name.capitalize()} updated successfully"}

    @router.delete(f"/{model_name}/delete/{{item_id}}", operation_id=generate_operation_id("delete", model_name, "delete"))
    def delete_item(item_id: int, db: Session = Depends(get_db)):
        db_item = db.query(model).filter(model.id == item_id).first()
        if not db_item:
            raise HTTPException(status_code=404, detail=f"{model_name} not found")
        db.delete(db_item)
        db.commit()
        return {"message": f"{model_name} deleted successfully"}

    return router

class PageOutputModel(BaseModel):
    title: str
    slug: str

page_router = create_crud_routes(Page, "pages", PageOutputModel)
