from threading import Event

import paho.mqtt.client as mqtt
import time
from datetime import datetime,date
from json import dumps

#broker = "test.mosquitto.org"
broker = '10.30.30.7'

def asdf(client, userdata, flags, rc):
    print("Connection returned: ") # + mqtt.connack_string(rc))

def onpublish(client, userdata, mid):
    print( "Published!")

sentEvent = Event()

def blah(client, userdata, flags, rc):
    print("connected!")
    sentEvent.set()

if __name__ == "__main__":
    client = mqtt.Client()

    client.on_connect = blah
    client.connect(broker,1883) #14443)# 1883)
    client.on_publish = onpublish
    #client.publish("esp-rfid", dumps({'cmdf':'opendoor','doorip':'front_door'}))
    if False:
        client.publish("esp-rfid", dumps({'cmd': 'adduser',
                                      'doorip': 'front_door',
                                      'uid':'F:15598498',
                                      'user':'person27',
                                        'validuntil':datetime.now().timestamp() + 2*24*3600,
                                      'acctype':"1"}))
    if False:
        client.publish("esp-rfid", dumps({'cmd': 'adduser',
                                          'doorip': 'front_door',
                                          'uid': 'F:1234567',
                                          'user': 'banned_user',
                                          'validuntil': datetime.now().timestamp() + 2 * 24 * 3600,
                                          'acctype': "1"}))
    if False:
        client.publish("esp-rfid", dumps({'cmd':'deleteuid',
                                          'doorip' : 'front_door',
                                          'uid':'F:15598498'}))
    if False:
            client.publish("esp-rfid", dumps({'cmd': 'deleteusers',
                                              'doorip': 'front_door'
                                              }))
    if False:
        client.publish("esp-rfid", dumps({'cmd': 'getuserlist',
                                          'doorip': 'front_door'
                                          }))
    if True:
        client.publish("what", dumps({
                                    "type":"access",
                                    "time":1605991375,
                                    "isKnown":"false",
                                    "access":"Always",
                                    "username":"Unknown",
                                    "uid":"token UID",
                                    "hostname":"frontdoor"
}))
    if False:
        client.publish("esp-rfid", dumps({'cmd': 'opendoor',
                                          'doorip': 'front_door'
                                          }))
    if False:
            client.publish("what", dumps({'command': 'whatthe','qrsgp':'1',
                                                "result" : 0, "error":"success"
                                              }))
    #client.publish("Scan", "f:432345432")
    #client.publish("Scan", "f:9549483949")
    client.loop_start()
    sentEvent.wait(1)
    client.loop_stop()
    client.disconnect()