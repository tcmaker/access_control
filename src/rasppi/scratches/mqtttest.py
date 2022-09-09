import paho.mqtt.client as mqtt
import time

#broker = "test.mosquitto.org"
broker = 'localhost'


def asdf(client, userdata, flags, rc):
    print("Connection returned: " + mqtt.connack_string(rc))

def onpublish(client, userdata, mid):
    print( "Published!")

if __name__ == "__main__":
    client = mqtt.Client()
    client.on_connect = asdf
    client.on_publish = onpublish
    client.connect(broker,1883)

    client.publish("scan", "f:123456789")
    #client.publish("Scan", "f:432345432")
    #client.publish("Scan", "f:9549483949")
    client.disconnect()