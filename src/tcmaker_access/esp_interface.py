import logging
import paho.mqtt.client as mqtt
from json import dumps
from models import Fob

class EspRfid:
    def __init__(self, broker, topic, clientname="coordinator"):
        self._broker = broker
        self._topic = topic
        self._clientname = clientname

    def __enter__(self):
        self._client = mqtt.Client(self._clientname)
        self._client.on_connect = self.on_connect
        self._client.connect(self._broker, 1883)
        print("Done with __enter__")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._client.loop()
        self._client.disconnect()

    def update(self, target, fob:Fob):
        self._client.loop()
        payload = {"cmd":"adduser",
                   "doorip": target,
                   # todo: handle this more elegantly in some manner
                   "uid" : f"F:{fob.code}",
                   "user" : fob.user,
                   "acctype":fob.esp_access(),
                   "validuntil" : fob.expiration_timestamp()}
        self._client.publish(self._topic, dumps(payload))

    def on_connect(self, client: mqtt.Client, userdata, flags, rc):
        pass
        #for fob in self.list_keyfobs(self._start_url):
        #client.disconnect()