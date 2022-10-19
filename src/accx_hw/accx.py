import logging
import paho.mqtt.client as mqtt
from yaml import load, safe_load
from yaml.loader import SafeLoader
from reader_board import ReaderBoard
from fob_db import FobDatabase
from json import dumps, loads, JSONDecodeError
from datetime import date, datetime

DELETE_ALL = "deleteusers"
DELETE_UID = "deleteuid"
ADD_USER = "adduser"
GET_USER_LIST = "getuserlist"
OPEN_DOOR = "opendoor"

logger = logging.getLogger("accx")

def run_accx_fob_scanner(**kwargs):
    broker = kwargs['broker']
    fob_db = kwargs['fob_database']
    board_id = kwargs['board']
    name = kwargs['name']
    esp_topic = kwargs['topicname']

    logging.basicConfig(level=logging.DEBUG)

    #Initialize our hardware first.
    import signal
    try:
        hardware = ReaderBoard(board_id)
    except:
        pass #todo handle errors starting up

    fob_db = FobDatabase(fob_db)

    def on_subscribe(client, userdata, mid, granted_qos):
        print("Subscribed", client, userdata, mid, granted_qos)

    def on_esp_message(payload):
        command = payload['cmd']
        if command == OPEN_DOOR:
                print("Unlocking....")
                hardware.Unlock(1, 3)
        if command == DELETE_ALL:
            fob_db.remove_all()
        if command == DELETE_UID:
            fob_db.remove(payload['uid'])
        if command == ADD_USER:
            expiration = datetime.fromtimestamp(payload['validuntil']).date()
            fob_db.add(payload['uid'], payload['user'], expiration)

    def on_message(client, userdata, message: mqtt.MQTTMessage):
        try:
            payload = loads(str(message.payload.decode('utf-8')))
            if 'doorip' not in payload or payload['doorip'] != name:
                return
            topic = message.topic
            #print(
            #    f"Got a message @ {message.topic}, from: {message.info} userdata: {userdata}, payload: {payload}")
            if(topic == esp_topic):
                on_esp_message(payload)
        except (KeyError, JSONDecodeError) as ee:
            # garbage data came in, do nothing
            return
        except Exception as e:
            logger.debug("Problem processing mqtt event:",exc_info=e)

    def on_connect(client, userdata, flags, rc):
        print("Connected!")
        client.subscribe(esp_topic)

    client = mqtt.Client("accx_client")
    client.on_connect = on_connect
    client.connect(broker, 1883)
    client.on_message = on_message

    def log_activity(result, code, person, expiration : date):
        payload = {'name':name,
                   'result': result,
                   'code': code,
                   'person': person,
                   'when': datetime.now().isoformat(),
                   'expiration': expiration.isoformat()}
        client.publish("activity",dumps(payload))

    def on_scan(first_char: str, body: str, device_id: str):
        if first_char == 'F' or first_char == 'P':  # keyfob
            (code, scanner_index) = body.split(',')
            print(f"Got a scan! body: {body}, fc: {first_char}")
            credential_string = f"{first_char}:{code}"
            (result,who,expiration) = fob_db.is_active(credential_string)
            if result:

                hardware.Unlock(1,3)
            log_activity(result, credential_string, who if who is not None else "None", expiration if expiration is not None else date.min)


    def signal_handler(sig, frame):
        print("Shutting down...")
        client.disconnect()
        hardware.shutdown()

    signal.signal(signal.SIGINT, signal_handler)
    hardware.packetCallback = on_scan
    client.loop_forever()

if __name__ == "__main__":
    #from reader_board import list_devices
    #list_devices()

    #load the configuration
    with open("config_template.yaml") as stream:
        config = load(stream, Loader=SafeLoader)

    run_accx_fob_scanner(**config['accx_hw'])