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



@welcome_screen.route('/')
def hello_world():  # put application's code here
    return 'Hello World!'

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
            return Response("Nothing")
    finally:
        with event_lock:
            longPollEvents.remove(lpe)

@welcome_screen.route("/doordisplay")
def door_display():
    return render_template('container.html')

def on_mqtt_message(client: mqtt.Client, userdata, message: mqtt.MQTTMessage):
    try:
        #print(f"Got a message @ {message.topic}, from: {message.info} userdata: {userdata}, payload: {str(message.payload.decode('utf-8'))}")
        topic = message.topic
        payload = loads(str(message.payload.decode('utf-8')))
        if topic == 'activity':
            if payload['name'] == 'front_door':
                global scan_result
                scan_result = "GRANTED!" if payload['result'] else "GO AWAY"
                print(f"Setting {len(longPollEvents)} events!")
                with event_lock:
                    for ev in longPollEvents:
                        ev.set()
    except:
        pass

if __name__ == '__main__':
    broker = "localhost"
    client = mqtt.Client("WelcomeScreen")
    client.connect(broker, 1883)

    client.on_message = on_mqtt_message
    #client.on_subscribe = on_subscribe

    client.subscribe("activity")
    client.loop_start()
    welcome_screen.run()
    client.loop_stop()
    print("Blah")
