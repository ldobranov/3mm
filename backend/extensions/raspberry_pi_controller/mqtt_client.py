import logging
from paho.mqtt import client as mqtt_client

# Enable detailed debugging for the MQTT client
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("paho.mqtt.client")

mqtt_client_instance = None

def connect_mqtt(broker, port, username, password):
    global mqtt_client_instance
    mqtt_client_instance = mqtt_client.Client()
    mqtt_client_instance.username_pw_set(username, password)
    mqtt_client_instance.on_log = lambda client, userdata, level, buf: logger.debug(f"MQTT Log: {buf}")
    try:
        mqtt_client_instance.connect(broker, port, keepalive=60)
        mqtt_client_instance.loop_start()
        logger.info(f"Successfully connected to MQTT broker at {broker}:{port}")
    except Exception as e:
        logger.error(f"Failed to connect to MQTT broker at {broker}:{port} with error: {e}")
        raise RuntimeError(f"Failed to connect to MQTT broker: {e}")

def send_mqtt_command(topic: str, payload: str):
    if mqtt_client_instance:
        mqtt_client_instance.publish(topic, payload)
        return {"message": "Command sent successfully"}
    return {"error": "MQTT client not configured"}

def fetch_mqtt_status():
    # Implement logic to fetch status updates
    return {"status": "OK"}
