import paho.mqtt.client as mqtt
import time

def on_scan(client, userdata, message: mqtt.MQTTMessage):
    print(f"Got a message @ {message.topic}, from: {message.info} userdata: {userdata}, payload: {str(message.payload.decode('utf-8'))}")

def on_subscribe(client, userdata, mid, granted_qos):
    print("Subscribed", client, userdata, mid, granted_qos)

if __name__ == "__main__":
    #broker = "test.mosquitto.org"
    broker = "localhost"
    client = mqtt.Client("Thing1")
    client.connect(broker, 1883)



    client.on_message = on_scan
    client.on_subscribe = on_subscribe

    client.subscribe("activity")

    client.loop_forever()


    #time.sleep(30)
    #client.loop_stop()

