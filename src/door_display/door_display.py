import contextlib
import logging
import random
import string
import time
from json import loads
from threading import Event, Lock, Thread

import paho.mqtt.client as mqtt
from flask import Flask, render_template, jsonify

welcome_screen = Flask(__name__)
event_lock = Lock()
long_poll_events = []
scan_result = ""
mqtt_topic = ""
monitored_facility = ""
last_scan_time = time.time()
timeout_time = 60
dwell_time = 20

logging.getLogger('sqlalchemy.engine').setLevel(logging.FATAL)
logging.getLogger('sqlalchemy.pool').setLevel(logging.FATAL)
logging.getLogger('sqlalchemy.orm').setLevel(logging.FATAL)
logging.getLogger('werkzeug').setLevel(logging.FATAL)

@welcome_screen.after_request
def disable_cache(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    r.headers['Cache-Control'] = 'public, max-age=0'
    return r

@welcome_screen.route('/')
def door_display():
    return render_template('container.html')


@welcome_screen.route("/poll")
def longpoll():
    global scan_result
    with event_lock:
        lpe = Event()
        long_poll_events.append(lpe)
    try:
        wait_time = timeout_time if scan_result == "#idlecontent" else dwell_time
        if time.time() - last_scan_time > wait_time:
            scan_result = {'content': "#idlecontent"}
        if lpe.wait(wait_time):
            return jsonify(scan_result)
        else:
            return jsonify({"content": "#idlecontent"})
    finally:
        with event_lock:
            long_poll_events.remove(lpe)


def on_mqtt_message(_: mqtt.Client, __, message: mqtt.MQTTMessage):
    global mqtt_topic, monitored_facility
    print("Mqtt message came in!")
    with contextlib.suppress(Exception):
        topic = message.topic
        payload = loads(str(message.payload.decode('utf-8')))
        if topic == mqtt_topic:
            if payload['hostname'] == monitored_facility:
                global scan_result
                access_result = payload['access']
                if access_result == 'Always':
                    scan_result = {'content': "#welcomecontent", 'fob': ''}
                elif access_result == 'Expired' or access_result == "Disabled":
                    scan_result = {'content': "#expiredcontent", 'fob': ''}
                elif access_result == 'Denied':
                    scan_result = {'content': "#unrecognizedcontent", 'fob': payload['uid']}
                with event_lock:
                    for ev in long_poll_events:
                        ev.set()


def on_connect(client, _, __, ___):
    global mqtt_topic
    client.subscribe(mqtt_topic)


def on_disconnect(___, _, __):
    pass


if __name__ == '__main__':
    import configargparse

    p = configargparse.ArgumentParser(default_config_files=['display.ini'])
    p.add_argument('-c', '--config', is_config_file=True, help='config file path')
    p.add_argument('-b', '--broker', help="MQTT to use", env_var="MQTT_BROKER", dest='mqtt_broker', required=True)
    p.add_argument('-t', '--topic', '--mqtt-topic', help="MQTT topic", env_var="MQTT_TOPIC", dest='mqtt_topic', required=True)
    p.add_argument('-f', '--facility', help='facility this display monitors', env_var='MONITORED_FACILITY', dest='monitored_facility', required=True)
    p.add_argument('-m', '--mqtt-port', help='MQTT broker port', env_var="MQTT_PORT", dest='mqtt_port', default=1883)
    p.add_argument('-p', '--http-port', help='HTTP server port', env_var="HTTP_PORT", dest='http_port', default=8888)
    p.add_argument('-l', '--listen-address', help='HTTP listen_address', env_var="HTTP_ADDRESS", dest='http_address',
                   default='0.0.0.0')
    p.add_argument('-d', '--dwell-time', help="How long in seconds to show message after scan", env_var="DWELL_TIME",
                   dest='dwell_time', default=20)

    options = p.parse_args()
    mqtt_topic = options.mqtt_topic
    dwell_time = float(options.dwell_time)
    mqtt_client = mqtt.Client("welcome_display-" + "".join([random.choice(string.ascii_letters) for r in range(5)]))
    mqtt_client.on_message = on_mqtt_message
    mqtt_client.on_disconnect = on_disconnect
    mqtt_client.on_connect = on_connect
    mqtt_client.connect(options.mqtt_broker, int(options.mqtt_port))

    monitored_facility = options.monitored_facility

    import signal


    def handler(_, __):
        print("Handled CTRL+C")
        mqtt_client.disconnect()
        exit(0)


    signal.signal(signal.SIGINT, handler)

    print("Starting up!")
    print(f"MQTT topic {options.mqtt_topic} via {options.mqtt_broker}:{options.mqtt_port}")
    welcome_screen.jinja_env.auto_reload = True
    welcome_screen.config['TEMPLATES_AUTO_RELOAD'] = True

    t = Thread(target=welcome_screen.run, kwargs={'use_reloader': False, 'host': options.http_address,
                                                  "port": options.http_port})
    t.daemon = True
    t.start()
    mqtt_client.loop_forever()
