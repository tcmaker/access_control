import paho.mqtt.client as mqtt
import time
from datetime import datetime,date
from json import dumps

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
    client.connect(broker,14443)# 1883)

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
    if False:
        client.publish("esp-rfid", dumps({
                                    "type":"access",
                                    "time":1605991375,
                                    "isKnown":"false",
                                    "access":"Denied",
                                    "username":"Unknown",
                                    "uid":"token UID",
                                    "hostname":"front-door"
}))
    if True:
        client.publish("esp-rfid", dumps({'cmd': 'opendoor',
                                          'doorip': 'front_door'
                                          }))
    #client.publish("Scan", "f:432345432")
    #client.publish("Scan", "f:9549483949")
    client.disconnect()