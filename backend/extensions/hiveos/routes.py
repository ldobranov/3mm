from fastapi import APIRouter, HTTPException, Header, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from .models import HiveOSKey
from backend.database import get_db
from fastapi.responses import JSONResponse
import jwt
from .hiveos_api import HiveOSAPI

router = APIRouter()

SECRET_KEY = "your_secret_key"  # Replace with a secure key

class AuthenticateRequest(BaseModel):
    api_key: str

@router.post("/authenticate", operation_id="hiveos_authenticate")
def authenticate(request: AuthenticateRequest):
    """Generate a backend token and store HiveOS API key."""
    backend_token = jwt.encode({"api_key": request.api_key}, SECRET_KEY, algorithm="HS256")

    response = JSONResponse(content={"message": "Authentication successful"})
    response.headers["Authorization-Token"] = backend_token
    return response

@router.post("/save-api-key")
def save_api_key(api_key: str = Query(...), db: Session = Depends(get_db)):
    hiveos_key = db.query(HiveOSKey).filter(HiveOSKey.user_id == 1).first()  # Replace with actual user ID
    if hiveos_key:
        hiveos_key.api_key = api_key
    else:
        hiveos_key = HiveOSKey(user_id=1, api_key=api_key)  # Replace with actual user ID
        db.add(hiveos_key)
    db.commit()
    return {"message": "API Key saved successfully"}

@router.post("/revoke-api-key")
def revoke_api_key(db: Session = Depends(get_db)):
    hiveos_key = db.query(HiveOSKey).filter(HiveOSKey.user_id == 1).first()  # Replace with actual user ID
    if hiveos_key:
        db.delete(hiveos_key)
        db.commit()
    return {"message": "API Key revoked successfully"}

@router.post("/save-selected-farm")
def save_selected_farm(farm_id: str, db: Session = Depends(get_db)):
    hiveos_key = db.query(HiveOSKey).filter(HiveOSKey.user_id == 1).first()  # Replace with actual user ID
    if hiveos_key:
        hiveos_key.selected_farm_id = farm_id
        db.commit()
    return {"message": "Selected farm saved successfully"}

@router.get("/farms", operation_id="hiveos_fetch_farms")
def fetch_farms(backend_token: str = Header(..., alias="Authorization")):
    """Retrieve the list of farms."""
    try:
        payload = jwt.decode(backend_token.split(" ")[1], SECRET_KEY, algorithms=["HS256"])
        hiveos_api_key = payload.get("api_key")
        if not hiveos_api_key:
            raise HTTPException(status_code=401, detail="HiveOS API key missing in backend token payload")

        api = HiveOSAPI(hiveos_api_key)
        response = api.get("https://api2.hiveos.farm/api/v2/farms")
        return response.json().get("data", [])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Backend token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid backend token")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch farms: {str(e)}")

@router.get("/farms/{farm_id}/workers", operation_id="hiveos_fetch_workers")
def fetch_workers(farm_id: int, backend_token: str = Header(..., alias="Authorization")):
    """Retrieve the list of workers for a specific farm."""
    try:
        payload = jwt.decode(backend_token.split(" ")[1], SECRET_KEY, algorithms=["HS256"])
        hiveos_api_key = payload.get("api_key")
        if not hiveos_api_key:
            raise HTTPException(status_code=401, detail="HiveOS API key missing in backend token payload")

        api = HiveOSAPI(hiveos_api_key)
        response = api.get(f"https://api2.hiveos.farm/api/v2/farms/{farm_id}/workers")
        return response.json().get("data", [])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Backend token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid backend token")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch workers: {str(e)}")

@router.post("/farms/{farm_id}/workers/command", operation_id="hiveos_send_command")
def send_command(farm_id: int, payload: dict, backend_token: str = Header(..., alias="Authorization")):
    """Send a command to a specific worker."""
    try:
        # Decode the backend token to extract the HiveOS API key
        payload_decoded = jwt.decode(backend_token.split(" ")[1], SECRET_KEY, algorithms=["HS256"])
        hiveos_api_key = payload_decoded.get("api_key")
        if not hiveos_api_key:
            raise HTTPException(status_code=401, detail="HiveOS API key missing in backend token payload")

        api = HiveOSAPI(hiveos_api_key)
        worker_ids = payload.get("worker_ids", [])
        action = payload.get("action")
        results = []

        # Validate the action in the payload
        if not action:
            raise HTTPException(status_code=422, detail="Missing 'action' field in the payload.")
        if action not in ["start", "stop", "reboot", "shutdown"]:
            raise HTTPException(status_code=400, detail=f"Invalid action: {action}. Allowed actions are 'start', 'stop', 'reboot', and 'shutdown'.")

        for worker_id in worker_ids:
            if action in ["reboot", "shutdown"]:
                url = f"https://api2.hiveos.farm/api/v2/farms/{farm_id}/workers/{worker_id}/command"
                command_payload = {"command": action}
            else:
                url = f"https://api2.hiveos.farm/api/v2/farms/{farm_id}/workers/{worker_id}/command"
                command_payload = {
                    "command": "miner",
                    "data": {"action": action}
                }

            try:
                response = api.post(url, json=command_payload)
                if response.status_code == 200:
                    results.append({"worker_id": worker_id, "status": "ok"})
                elif response.status_code != 521:
                    results.append({"worker_id": worker_id, "status": "error", "error": response.text})
            except Exception as e:
                results.append({"worker_id": worker_id, "status": "error", "error": str(e)})

        return {"results": results}

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Backend token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid backend token")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
