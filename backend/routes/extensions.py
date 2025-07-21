# filepath: /home/laz/3mm/backend/routes/extensions.py
from fastapi import APIRouter, UploadFile, HTTPException, Depends
from sqlalchemy.orm import Session
from backend.db.extension import Extension, ExtensionBase
from backend.utils.db_utils import get_db
import zipfile
import os
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("route_debug")

router = APIRouter()

@router.post("/upload", operation_id="extensions_upload_extension")
def upload_extension(file: UploadFile, db: Session = Depends(get_db)):
    try:
        if not file.filename.endswith(".zip"):
            raise HTTPException(status_code=400, detail="Only .zip files are allowed")

        temp_path = f"/tmp/{file.filename}"
        with open(temp_path, "wb") as temp_file:
            temp_file.write(file.file.read())

        if not zipfile.is_zipfile(temp_path):
            os.remove(temp_path)
            raise HTTPException(status_code=400, detail="Invalid .zip file")

        with zipfile.ZipFile(temp_path, "r") as zip_ref:
            zip_ref.extractall("/tmp/extracted_extension")

        os.remove(temp_path)

        backend_path = "/tmp/extracted_extension/backend"
        frontend_path = "/tmp/extracted_extension/frontend"

        if os.path.exists(backend_path):
            os.makedirs("extensions/backend", exist_ok=True)
            os.system(f"mv {backend_path}/* extensions/backend/")

        if os.path.exists(frontend_path):
            os.makedirs("extensions/frontend", exist_ok=True)
            os.system(f"mv {frontend_path}/* extensions/frontend/")

        return {"message": "Extension uploaded and registered successfully"}
    except Exception as e:
        logger.error(f"Error during extension upload: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/generate", operation_id="extensions_generate_extension")
def generate_extension(description: str, db: Session = Depends(get_db)):
    try:
        if not description:
            raise HTTPException(status_code=422, detail="Missing required fields")

        generated_extension = {
            "name": "AI Generated Extension",
            "description": description,
            "version": "1.0.0",
        }

        # Save the generated extension metadata to the database
        new_extension = Extension(
            name=generated_extension["name"],
            description=generated_extension["description"],
            version=generated_extension["version"],
        )
        db.add(new_extension)
        db.commit()

        return generated_extension
    except Exception as e:
        logger.error(f"Error during extension generation: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")