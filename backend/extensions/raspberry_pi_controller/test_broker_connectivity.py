import logging
from paho.mqtt import client as mqtt_client

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT Broker!")
    else:
        print(f"Failed to connect, return code {rc}")

def on_log(client, userdata, level, buf):
    print(f"Log: {buf}")

def test_broker_connectivity(broker, port, username, password):
    logging.basicConfig(level=logging.DEBUG)
    client = mqtt_client.Client(protocol=mqtt_client.MQTTv311)  # Explicitly set protocol
    client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.on_log = on_log

    try:
        print(f"Attempting to connect to MQTT broker at {broker}:{port}...")
        client.connect(broker, port, keepalive=60)
        client.loop_start()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    broker = "10.10.0.100"  # Updated broker IP
    port = 1883
    username = "your_username"
    password = "your_password"

    test_broker_connectivity(broker, port, username, password)
