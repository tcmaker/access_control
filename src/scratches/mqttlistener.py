import paho.mqtt.client as mqtt
import time

def on_scan(client, userdata, message: mqtt.MQTTMessage):
    print(f"Got a message @ {message.topic}, from: {message.info} userdata: {userdata}, payload: {str(message.payload.decode('utf-8'))}")

def on_subscribe(client, userdata, mid, granted_qos):
    print("Subscribed", client, userdata, mid, granted_qos)

def on_connect(client : mqtt.Client, userdata, flags, rc):
    print("connected!")
    client.subscribe("hfac")
    #client.subscribe("esp-rfid")

if __name__ == "__main__":
    #broker = "test.mosquitto.org"
    broker = "10.30.30.7"
    client = mqtt.Client("Thing1")
    client.on_connect = on_connect
    client.connect(broker, 1883)# 14443)# 1883)
    client.on_message = on_scan
    client.on_subscribe = on_subscribe


    client.loop_forever()

