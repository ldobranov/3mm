from fastapi import APIRouter
from pydantic import BaseModel
from .mqtt_client import connect_mqtt, send_mqtt_command, fetch_mqtt_status

router = APIRouter()

class MQTTConfig(BaseModel):
    broker: str
    port: int
    username: str
    password: str

class MQTTCommand(BaseModel):
    topic: str
    payload: str

@router.post("/configure")
def configure_mqtt(config: MQTTConfig):
    connect_mqtt(config.broker, config.port, config.username, config.password)
    return {"message": "MQTT configured successfully"}

@router.post("/send")
def send_command(command: MQTTCommand):
    return send_mqtt_command(command.topic, command.payload)

@router.get("/status")
def fetch_status():
    return fetch_mqtt_status()
