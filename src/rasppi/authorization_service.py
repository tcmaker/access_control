from configuration import Config, Facility, Scanner
from models import DoorControllerBase, Activity#, Credential, Activity, AccessRequirement
from hardware import ReaderBoard, query_devices
import plugins
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy import create_engine
import paho.mqtt.client as mqtt
from json import dumps

from typing import Dict, Iterable
import logging

from threading import Thread, Lock
from multiprocessing import Queue
from queue import Empty

from datetime import datetime

logger = logging.getLogger("auth")
try:
    from datadog_logger import get_datadog_logger
    dd_logger = get_datadog_logger("frontdoor", "front_door_access")
    auth_service_logger = get_datadog_logger("authorization_service", "authorization_service")
    dd_logger.setLevel(logging.INFO)
    auth_service_logger.setLevel(logging.INFO)
except:
    pass

class AuthorizationService:
    boards: Dict[str, ReaderBoard]


    def __init__(self, input_queue: Queue, output_queue: Queue):
        engine = create_engine(f"sqlite:///{Config.ActivityDb}")
        Session = sessionmaker(bind=engine)
        # session = Session()
        self.ScopedSession = scoped_session(Session)
        DoorControllerBase.metadata.create_all(engine)

        self._run = True
        self.boards = {}
        self.boardLock = Lock()
        self._inqueue = input_queue
        self._outqueue = output_queue
        self.authModules = self.load_authorizations()
        self.curfew_start = datetime(2020,4,13,22,0,0)
        self.curfew_end = datetime(2020,4,13,6,0,0)

        self.run()

    def load_authorizations(self):
        auth_plugins = plugins.load_plugins("auth")
        for ap in auth_plugins:
            try:
                plugin_schema_name = ap.get_configuration_schema()[0]
                ap.read_configuration(Config.RawConfig["auth"][plugin_schema_name])
                ap.on_load()
            except Exception as ee:
                logger.error(f"failed to configure {ap}, exception: {ee}")
        try:
            auth_service_logger.info("Authorization service started up")
        except:
            pass
        return sorted(auth_plugins, key=lambda ap: ap.priority(), reverse=True)

    def reload_boards(self):
        self.boardLock.acquire()
        for bn, bv in self.boards.items():
            logger.debug(f"Shutting down board: {bn}")
            bv.shutdown()
        self.boards.clear()

        all_boards = []
        try:
            for f in Config.getDevices():
                try:
                    if f not in all_boards:
                        logger.debug(f"Staring up board: {f}")
                        new_reader = ReaderBoard(f)
                        new_reader.packetCallback = self.on_scan
                        self.boards[f] = new_reader
                        all_boards.append(f)
                except Exception as e:
                    logger.fatal(f"Unable to startup hardware {f}: {e}")
        finally:
            self.boardLock.release()

    def run(self):
        self.reload_boards()
        for api in self.authModules:
            try:
                api.refresh_database()
            except Exception as e:
                logger.error(f"Failed to refresh database, module: {api.__module__}, e: {e}")
        while self._run:
            try:
                r = self._inqueue.get(block=True, timeout=60)
            except Empty:
                #  Do our AWS checks
                for api in self.authModules:
                    try:
                        api.refresh_database()
                    except Exception as e:
                        logger.error(f"Failed to refresh database, module: {api.__module__}, e: {e}")
                continue

            if type(r) == tuple:
                if r[0] == 'unlock':
                    (c, board, relay, duration, credential) = r
                    self.boards[board].Unlock(relay, duration, credential)
                elif r[0] == "lock":
                    (a, board, relay, credential) = r
                    self.boards[board].Lock(relay, credential)
                elif r[0] == 'aws':
                    for api in self.authModules:
                        api.refresh_database()
                elif r[0] == "status":
                    fv: Facility
                    # def facilityStatus(f : Facility):
                    #    return self.boards[f.board].relaystatus[f.relay]
                    try:
                        status = dict((f.name,
                                       self.boards[f.board].relaystatus[f.relay]) for f in Config.Facilities.values())
                    # status = list(map(facilityStatus,Config.Facilities.values()))
                        self._outqueue.put(status)
                    except:
                        self._outqueue.put({})
                elif r[0] == "query":
                    response = []
                    bv: ReaderBoard
                    for bn, bv in self.boards.items():
                        response.append(bv.__repr__())
                    for bv in query_devices(ignored_devices=self.boards.values()):
                        response.append(bv)
                    self._outqueue.put(response)
                elif r[0] == 'checkfob':
                    (a, fob) = r
                    logger.info(f"Got check fob for {fob}")
                    self._outqueue.put(self.check_fob_status(fob))
                elif r[0] == "reload":
                    # We have to do this here, even though it's also done in the webpanel, because
                    # Config is different here vs webpanel due to multiprocessing
                    Config.Reload()
                    self.reload_boards()
                    for api in self.authModules:
                        api.on_close()
                    self.authModules = self.load_authorizations()
                    self._outqueue.put("OK")

    def lock(self, board, relay, credential):
        self._inqueue.put(('lock', board, relay, credential))

    def unlock(self, board, relay, duration, credential):
        self._inqueue.put(('unlock', board, relay, duration, credential))

    def trigger_notify(self, activity):
        if activity is not None:
            t = Thread(target=self.notify_mqtt, args=[activity])
            t.start()

    @staticmethod
    def find_facility(board, scanner_index):
        target: Scanner or None = None
        for sb, si in Config.getScanners().items():
            if si.board == board and si.scannerIndex == scanner_index:
                target = si
                break
        if target is not None:
            for fn, fv in Config.getFacilities().items():
                if fv.scanner == target or fv.outscanner == target:
                    return fv, fv.scanner if fv.scanner == target else fv.outscanner
        else:
            return None, None

    def on_scan(self, first_char: str, body: str, device_id: str):
        db: Session = self.ScopedSession()
        activity = None
        try:
            if first_char == 'F' or first_char == 'P':  # keyfob
                (code, scanner_index) = body.split(',')
                scanner_index = int(scanner_index)
                credential_type = 'fob' if first_char == 'F' else 'passcode'
                credential_value = code
                credential_ref = f'{credential_type}:{credential_value}'
                (facility, scanner) = self.find_facility(device_id, scanner_index)
                auth_results = {}
                if facility is not None:
                    now = datetime.now()
                    #attempt to find an authorization for the user
                    for am in self.authModules:
                        try:
                            (grant, member, auth, expiration, last_update) = am.on_scan(credential_type,credential_value,scanner,facility, now)
                            auth_results[am.__module__] = (grant, member, auth, expiration, last_update)
                            if grant:
                                #CURFEW ENFORCING HACKJOB, REMOVE ME
                                if (now > self.curfew_start and now < self.curfew_end):
                                    activity = Activity(memberid=member,authorization="curfew",
                                                    result="denied",
                                                    timestamp=now,
                                                    credentialref=credential_ref,
                                                    facility=facility.name,
                                                    notified=False)
                                else:
                                    activity = Activity(memberid=member, authorization=auth,
                                                    result="granted" if grant else "denied",
                                                    timestamp=datetime.now(),
                                                    credentialref=credential_ref,
                                                    facility=facility.name,
                                                    notified=False)                            
                                    self.unlock(facility.board, facility.relay, facility.unlockduration, credential_value)
                                db.add(activity)
                                db.commit()
                                return
                        except Exception as ame:
                            logger.error(f"Failed to call auth module {am.__module__}:  {ame}")
                # no credential matched, or no valid facility, user is denied
                wauth = auth_results.get('auth.wildapricot',None)
                if wauth:
                    activity = Activity(memberid=wauth[1], authorization=wauth[2], credentialref=credential_ref,
                                    result="denied", timestamp=datetime.now(),
                                    facility=facility.name if facility is not None else None,
                                    notified=False)
                    db.add(activity)
                    db.commit()
        finally:
            try:
                if activity is not None:
                    mqtt_payload = self.make_mqtt_payload(activity)
                    self.trigger_notify(mqtt_payload)
            except Exception as mq:
                logger.error("Failed to dispatch mqtt message: {mq}",exc_info=True)
            db.close()

    def check_fob_status(self, fob):
        try:
            auth_service_logger.info(f"Testing fob {fob} via diagnostic utility")
        except:
            pass

        try:
            return {am.__module__ : am.on_scan("fob", fob, None, None, datetime.now()) for am in self.authModules}
        except:
            return None

    def make_mqtt_payload(self, activity):
        access = "Denied"  # unknown fobs end up with this default value
        log_user = activity.memberid if activity.memberid is not None else "None"
        
        auth_source = "unknown"
        if '-' in log_user:
            log_user = f'https://members.tcmaker.org/api/v1/persons/{activity.memberid}/' 
            auth_source = "tcmembership"
        else:
            log_user = f"https://wa.tcmaker.org/admin/contacts/details/?contactId={activity.memberid}"
            auth_source = "wildapricot"


        if activity.result == "granted":
            access = "Always"
            log_access = "granted"
        else:
            if activity.authorization.startswith("wildapricot"):
                reason = activity.authorization.split(":")[1]
                log_access = reason
                if reason == "expired":
                    access = "Expired"
                elif reason == "not_enabled" or reason == "not_active":
                    access = "Disabled"
            if activity.authorization.startswith("tcmembership"):
                reason = activity.authorization.split(":")[1]
                log_access = reason
                if reason == "expired":
                    access = "Expired"

        payload = {
            "type": "access",
            "time": activity.timestamp.isoformat(),
            "isKnown": "True" if access != "Denied" else "False",
            "access": access,
            "wa_access": log_access,
            "username": activity.memberid,
            "uid": activity.credentialref,
            "hostname": activity.facility,
            "auth_source" : auth_source
        }

        pl = dumps(payload)

        payload['username'] = log_user

        try:
            func = dd_logger.info if log_access == "granted" else dd_logger.warning
            func(f"{payload['uid']} scanned - {activity.memberid}, result: {log_access}", extra={"authresult" : payload})
            pass
        except Exception as exx:
            logger.warning(f"Failed datadog message: {exx}", exc_info=True)

        return pl

    def notify_mqtt(self, payload):
        if Config.mqtt_broker is None or Config.mqtt_topic is None or Config.mqtt_port is None:
            return

        try:
            client = mqtt.Client()
            client.connect(Config.mqtt_broker, Config.mqtt_port)
            client.publish(Config.mqtt_topic,payload)
            client.disconnect()
        except Exception as e:
            logger.error(f"Failed to signal MQTT message:  {e}")
