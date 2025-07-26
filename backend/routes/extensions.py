# filepath: /home/laz/3mm/backend/routes/extensions.py
from fastapi import APIRouter, UploadFile, HTTPException, Depends
from sqlalchemy.orm import Session
from backend.db.extension import Extension, ExtensionBase
from backend.utils.db_utils import get_db
import zipfile
import os
import logging
from paho.mqtt import client as mqtt_client
import requests
from backend.extensions.hiveos.routes import router as hiveos_router
import importlib.util
from sqlalchemy import MetaData
from backend.db.base import Base

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("route_debug")

router = APIRouter()

# Include the HiveOS router dynamically
router.include_router(hiveos_router, prefix="/extensions/hiveos")

mqtt_client_instance = None

def connect_mqtt(broker, port, username, password):
    global mqtt_client_instance
    mqtt_client_instance = mqtt_client.Client()
    mqtt_client_instance.username_pw_set(username, password)
    mqtt_client_instance.connect(broker, port)

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
        if os.path.exists(backend_path):
            models_file = os.path.join(backend_path, "models.py")
            routes_file = os.path.join(backend_path, "routes.py")

            # Dynamically load models
            if os.path.exists(models_file):
                spec = importlib.util.spec_from_file_location("models", models_file)
                models_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(models_module)

                if hasattr(models_module, "Base"):
                    models_module.Base.metadata.create_all(bind=db.get_bind())

            # Dynamically load routes
            if os.path.exists(routes_file):
                spec = importlib.util.spec_from_file_location("routes", routes_file)
                routes_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(routes_module)

                if hasattr(routes_module, "router"):
                    router.include_router(routes_module.router, prefix=f"/extensions/{os.path.basename(backend_path)}")

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

@router.post("/extensions/mqtt/configure")
def configure_mqtt(broker: str, port: int, username: str, password: str):
    connect_mqtt(broker, port, username, password)
    return {"message": "MQTT configured successfully"}

@router.post("/extensions/mqtt/send")
def send_command(topic: str, payload: str):
    if mqtt_client_instance:
        mqtt_client_instance.publish(topic, payload)
        return {"message": "Command sent successfully"}
    return {"error": "MQTT client not configured"}

@router.get("/extensions/mqtt/status")
def fetch_status():
    # Implement logic to fetch status updates
    return {"status": "OK"}