import argparse
from threading import Event

import paho.mqtt.client as mqtt
import time
from datetime import datetime,date
from json import dumps
def asdf(client, userdata, flags, rc):
    print("Connection returned: ") # + mqtt.connack_string(rc))

def onpublish(client, userdata, mid):
    print( "Published!")


def on_connect (client, userdata, flags, rc):
    print("connected!")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument('-r','--result', default='Always')
    p.add_argument('-f','--fob', default="F:11432345")
    p.add_argument('-b', '--broker', default='10.30.30.7')
    p.add_argument('-p', '--port',  default='1883')
    p.add_argument('-t', '--topic', default='what')
    p.add_argument('-u', '--username', default='testuser')

    options = p.parse_args()

    client = mqtt.Client()
    client.on_connect = on_connect
    client.connect(options.broker,int(options.port)) #14443)# 1883)
    client.on_publish = onpublish
    #client.publish("esp-rfid", dumps({'cmdf':'opendoor','doorip':'front_door'}))

    if True:
        client.publish(options.topic, dumps({
                                    "type":"access",
                                    "time":datetime.now().timestamp(),
                                    "isKnown":"false",
                                    "access":options.result,
                                    "username":options.username if options.result != "Denied" else None,
                                    "uid":options.fob,
                                    "hostname":"frontdoor"
}))
    client.disconnect()