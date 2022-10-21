import paho.mqtt.client as mqtt
from threading import Event, current_thread, Lock
from flask import Flask, render_template, jsonify, request, redirect, g, stream_with_context, Response, abort
from json import loads, JSONDecodeError
import time

welcome_screen = Flask(__name__)
welcome_screen.config['SECRET_KEY'] = "ASDFASDFASDFADS" #Config.WebpanelSecretKey
event_lock = Lock()
longPollEvents = []
scan_result = ""
last_scan_time = time.time()

import logging

logging.getLogger('sqlalchemy.engine').setLevel(logging.FATAL)
logging.getLogger('sqlalchemy.pool').setLevel(logging.FATAL)
logging.getLogger('sqlalchemy.orm').setLevel(logging.FATAL)
logging.getLogger('werkzeug').setLevel(logging.FATAL)



@welcome_screen.route('/')
def door_display():
    return render_template('container.html')

@welcome_screen.route("/poll")
def longpoll():
    global scan_result
    with event_lock:
        lpe = Event()
        longPollEvents.append(lpe)
    try:
        if time.time() - last_scan_time > 30:
            scan_result = ""
        if lpe.wait(30.0):
            print("Event was set")
            return Response(scan_result)
        else:
            print("Event timed out")
            return render_template("idle.html")
    finally:
        with event_lock:
            longPollEvents.remove(lpe)

def on_mqtt_message(client: mqtt.Client, userdata, message: mqtt.MQTTMessage):
    try:
        #print(f"Got a message @ {message.topic}, from: {message.info} userdata: {userdata}, payload: {str(message.payload.decode('utf-8'))}")
        topic = message.topic
        payload = loads(str(message.payload.decode('utf-8')))
        if topic == 'esp-rfid':
            if payload['hostname'] == 'front_door':
                global scan_result
                scan_result = "GRANTED!" if payload['access'] == 'Always' else "GO AWAY"
                print(f"Setting {len(longPollEvents)} events!")
                with event_lock:
                    for ev in longPollEvents:
                        ev.set()
    except:
        pass


def on_connect(client, userdata, flags, rc):
    print("connected!")
    client.subscribe("esp-rfid")

if __name__ == '__main__':
    broker = "localhost"
    client = mqtt.Client("WelcomeScreen")
    client.connect(broker, 1883)

    client.on_message = on_mqtt_message
    client.on_connect = on_connect
    #client.on_subscribe = on_subscribe

    client.loop_start()
    welcome_screen.jinja_env.auto_reload = True
    welcome_screen.config['TEMPLATES_AUTO_RELOAD'] = True
    welcome_screen.run(debug=True)
    client.loop_stop()
    print("Blah")
