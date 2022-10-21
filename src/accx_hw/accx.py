__VERSION__='1.0'

import logging
import pathlib
import sys
import socket
from threading import Event, Thread

import paho.mqtt.client as mqtt
from yaml import load
from yaml.loader import SafeLoader
from reader_board import ReaderBoard
from fob_db import FobDatabase, ALWAYS, ADMIN
from json import dumps, loads, JSONDecodeError
from datetime import date, datetime
import typing

DELETE_ALL = "deleteusers"
DELETE_UID = "deleteuid"
ADD_USER = "adduser"
GET_USER_LIST = "getuserlist"
OPEN_DOOR = "opendoor"

logger = logging.getLogger("accx")

def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def run_accx_fob_scanner(broker, fob_database, board, name, mqtt_topic, **kwargs):
    #TODO parameter validation
    heartbeat = kwargs.get("heartbeat",180.0)
    my_ip = get_ip()
    booted = [False]
    start_time = datetime.now().timestamp()
    #Initialize our hardware first.
    import signal
    try:
        hardware = ReaderBoard(board)
    except:
        pass #TODO handle errors starting up

    fob_db = FobDatabase(fob_database)



    def on_subscribe(client, userdata, mid, granted_qos):
        print("Subscribed", client, userdata, mid, granted_qos)

    def acknowledge(type):
        client.publish(mqtt_topic, dumps({  # acknowledge the addition
            "type": type,
            "ip": my_ip,
            "hostname": name
        }))

    def on_esp_message(payload):
        command = payload['cmd']
        if command == OPEN_DOOR:
            log_activity(ALWAYS, "SYSTEM", "MQTT")
            hardware.Unlock(1, 3)
        if command == DELETE_ALL:
            fob_db.remove_all()
            acknowledge(DELETE_ALL)
        if command == DELETE_UID:
            fob_db.remove(payload['uid'])
            acknowledge(DELETE_UID)
        if command == ADD_USER:
            expiration = datetime.fromtimestamp(payload['validuntil']).date()
            fob_db.add(payload['uid'], payload['user'], expiration, payload['acctype'])
            acknowledge(ADD_USER)
        if command == GET_USER_LIST:
            for user in fob_db.all():
                payload = {'command': "userfile",
                           'uid': user.code,
                           'person': user.person,
                           'when': datetime.now().isoformat(),
                           'validuntil': datetime.fromisoformat(user.expiration.isoformat()).timestamp()}
                client.publish(mqtt_topic, dumps(payload))

    def on_message(client, userdata, message: mqtt.MQTTMessage):
        try:
            payload = loads(str(message.payload.decode('utf-8')))
            if 'doorip' not in payload or payload['doorip'] != name:
                return
            topic = message.topic
            #print(
            #    f"Got a message @ {message.topic}, from: {message.info} userdata: {userdata}, payload: {payload}")
            if topic == mqtt_topic:
                on_esp_message(payload)
        except (KeyError, JSONDecodeError) as ee:
            # garbage data came in, do nothing
            return
        except Exception as e:
            logger.debug("Problem processing mqtt event:",exc_info=e)

    disconnect_event = Event()

    heartbeat_thread = None
    def heart_beat():
        while not disconnect_event.wait(heartbeat):
            logger.debug("Sending heartbeat")
            hb_time = datetime.now().timestamp()
            client.publish(mqtt_topic, dumps({
                "type": "heartbeat",
                "time": hb_time,
                "uptime": hb_time - start_time,
                "ip": my_ip,
                "hostname": name
            }))
        print("heartbeat thread done")

    def on_connect(client : mqtt.Client, userdata, flags, rc):
        logger.debug(f"Connected to mqtt broker!")
        client.subscribe(mqtt_topic)
        if not booted[0]:
            logger.debug("Sending boot up message")
            nowtime = datetime.now().timestamp()
            client.publish(mqtt_topic, dumps({
                "type": "boot",
                "time": nowtime,
                "uptime": nowtime - start_time,
                "ip": my_ip,
                "hostname": name
            }))
            booted[0] = True
        disconnect_event.clear()
        t = Thread(target=heart_beat)
        t.start()

    def on_disconnect(client: mqtt.Client, userdata, rc):
        disconnect_event.set()

    client = mqtt.Client("accx_client")
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.connect(broker, 1883)
    client.on_message = on_message
    #TODO handle connection failures, what can we even do?
    def log_activity(result, code, person):
        payload = {"type":"access",
                   'time': datetime.now().timestamp(),
                   "isKnown":"true",
                   'access': result,
                   'username': person,
                   'uid': code,
                   'hostname': name}
        client.publish(mqtt_topic,dumps(payload))

    def on_scan(first_char: str, body: str, device_id: str):
        if first_char == 'F' or first_char == 'P':  # keyfob
            (code, scanner_index) = body.split(',')
            #print(f"Got a scan! body: {body}, fc: {first_char}")
            credential_string = f"{first_char}:{code}"
            (result,who) = fob_db.is_active(credential_string)
            if result == ALWAYS or result == ADMIN:
                hardware.Unlock(1,3)
            log_activity(result, credential_string, who if who is not None else "Unknown")

    def signal_handler(sig, frame):
        print("Shutting down...")
        disconnect_event.set()
        client.disconnect()
        hardware.shutdown()

    signal.signal(signal.SIGINT, signal_handler)
    hardware.packetCallback = on_scan
    client.loop_forever()
    # Send boot up message

def process_args(sysargs):
    import argparse

    parser = argparse.ArgumentParser(
        description="""Access control hardware server""", epilog="I'll put my name in here at some point")

    parser.add_argument('-c', '--config', action='store', dest='config', default=None,
                        help="specify non-default configuration file")
    parser.add_argument('-d', '--detect', action='store_true', dest='detect',
                        help="probe for compatible devices and exit")
    parser.add_argument('-v', '--version', action='store_true', dest='version', help="show version and exit")
    parser.add_argument('-q', '--quiet', action='store_true', dest='quiet', help="suppress non-error messages")
    parser.add_argument('-g', '--debug', action='store_true', dest='debug', help="show all log messages")

    args = parser.parse_args(sysargs)
    return args

if __name__ == "__main__":
    args = process_args(sys.argv[1:])

    if args.version:
        print(f"{sys.argv[0]} {__VERSION__}")
        exit(0)

    if args.detect:
        from reader_board import list_devices
        list_devices()
        exit(0)

    logging.basicConfig(level=logging.ERROR if args.quiet else logging.DEBUG if args.debug else logging.INFO )

    #load the configuration
    configfile = pathlib.Path('./config.yaml')
    if args.config is not None:
        configfile = pathlib.Path(args.config)

    with open(str(configfile.absolute())) as stream:
        config = load(stream, Loader=SafeLoader)

    run_accx_fob_scanner(**config['accx_hw'])