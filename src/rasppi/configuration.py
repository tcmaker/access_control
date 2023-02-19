#load the config file
from typing import Dict, Any, List, Tuple
from hashids import Hashids
import jsonschema
import logging
import logging.config
import logging.handlers

import os
import plugins

from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy import create_engine
from models import DoorControllerBase

from yaml import load, safe_load
from yaml.loader import  SafeLoader

class SafeLineLoader(SafeLoader):
    def construct_mapping(self, node, deep=False):
        mapping = super(SafeLineLoader, self).construct_mapping(node, deep=deep)
        # Add 1 so line numbering starts at 1
        mapping['__line__'] = node.start_mark.line + 1
        return mapping

class Facility():  # controls a single relay
    def __init__(self, name, board, scanner, relay, duration, outscanner=None):
        self.name = name
        self.board = board
        self.scanner = scanner
        self.outscanner = outscanner
        self.relay = relay
        self.unlockduration = duration

    def __repr__(self):
        return f"<Facility: {self.name}@:{self.board}.{self.relay}>"

class Scanner():  # represents a scanner on a board
    def __init__(self, name, board, scannerIndex):
        self.name = name
        self.board = board
        self.scannerIndex = scannerIndex

class ConfigurationException(Exception):
    pass

def validatePluginSchema(s):
    if type(s) is not tuple:
        return False
    if len(s) != 3:
        return False
    if type(s[0]) is not str or type(s[1]) is not dict or type(s[2]) is not bool:
        return False
    return True

class Configuration():
    authModules = plugins.load_plugins("auth")

    schemas = [mod.get_configuration_schema() for mod in authModules]
    for s in schemas:
        if not validatePluginSchema(s):
            print(f"FATAL: invalid plugin schema: {s}")
    requiredconfigs = [n[0] for n in (filter(lambda s: s[2],schemas))]
    #for r in requiredconfigs:
    #   required.append(r)

    props = {}
    for s in schemas:
        props[s[0]] = s[1]
    authSchema = { "type" : "object",
                   "properties" :
                       props,
                   "required" : requiredconfigs
                   }

    config_schema = { "type" : "object",
                      "properties" : {
                          "system" : { "type" : "object",
                                       "additionalProperties": False,
                                       "properties" : {
                                           "logfile" : { "type" : "string"},
                                           "activitydb": {"type": "string"},
                                           "email_alerts" : {"type" : "object",
                                                     "additionalProperties": False,
                                                     "properties" : {
                                                         "host": {"type": "string"},
                                                         "port": {"type": "integer"},
                                                         "from_addr": {"type": "string", "format" : "idn-email"},
                                                         "to_addrs": {"type": "array", "items" : {"type":"string", "format" : "idn-email"}},
                                                         "subject": {"type": "string"},
                                                         "smtp_user": {"type": "string"},
                                                         "smtp_pass": {"type": "string"},
                                                         "level": {"type": "string",
                                                                    "enum": ["critical", "fatal", "error", "warning"]},
                                                         "__line__": {},
                                                           },
                                                        "required" : ["host","port","from_addr","to_addrs","subject","smtp_user","smtp_pass"]
                                                      },
                                           "mqtt_broker": {"type": "string"},
                                           "mqtt_topic": {"type": "string"},
                                           "mqtt_port": {"type": "integer"},
                                           "__line__" : { },
                                       },
                                       "required" : ['activitydb','logfile']},
                          "webpanel": {"type": "object",
                                       "additionalProperties": False,
                                     "properties": {
                                         "secretkey": {"type": "string"},
                                         "username": {"type": "string"},
                                         "password": {"type": "string"},
                                         "__line__": {},
                                     },
                                     "required": ['secretkey', 'username','password']},
                          "auth" : authSchema,
                          "scanners": {"type" : ["object","null"],
                                       "properties" : {
                                           "__line__": {},
                                       },
                                       "patternProperties" : {
                                           "^[A-Za-z][A-Za-z0-9]*$" : {"type" : "object",
                                                                         "properties" : {
                                                                             "__line__": {},
                                                                             "board" : {"type" : "string"},
                                                                             "scanner": {"type": "integer"}
                                                                             },
                                                                            "required" : ['board',"scanner",],
                                                                            "additionalProperties": False,
                                                                         },

                                       },
                                       },
                          "facilities": {"type": ["object","null"],
                                       "properties": {
                                           "__line__": {},
                                       },
                                       "patternProperties": {
                                           "^[A-Za-z][A-Za-z0-9]*$": {"type": "object",
                                                                      "properties": {
                                                                          "__line__" : {},
                                                                          "board": {"type": "string"},
                                                                          "scanner": {"type": "string"},
                                                                          "outscanner": {"type": "string"},
                                                                          "duration" : {"type": "number"},
                                                                          "relay" : {"type" : "integer"}
                                                                      },
                                                                      "additionalProperties" : False,
                                                                      "required": ['board', "scanner","relay"],
                                                                      },

                                       },
                                       }

                      },
                      "required" : ["system", "webpanel", "auth", "scanners", "facilities"]}



    FileName = os.path.abspath('door_config.yaml')


    def Reload(self,stringInput = None):
        try:
            if type(stringInput) is not str:
                with open(self.FileName) as stream:
                    config = load(stream, Loader=SafeLineLoader)
            else:
                config = load(stringInput, Loader=SafeLineLoader)

            try:
                jsonschema.validate(config,self.config_schema)
            except jsonschema.SchemaError as se:
                raise ConfigurationException(str(se))
            except jsonschema.ValidationError as ve:
                if 'error_msg' in ve.schema:
                    raise ConfigurationException(ve.schema['error_msg'])
                else:
                    raise ConfigurationException(str(ve))

            self.LogFile = config['system']['logfile']
            self.ActivityDb = config['system']['activitydb']
            #attempt to write to that file
            #try:
            #    with open(self.LogFile, 'r+') as writer:
            #        pass
            #except:
            #    raise ConfigurationException(f'Unable to open log file "{self.LogFile}" for writing!' )

            self.WebpanelLogin = {
                config['webpanel']['username']: config['webpanel']['password']
            }

            self.WebpanelSecretKey = config['webpanel']['secretkey']

            self.HashId = Hashids(salt=self.WebpanelSecretKey, min_length=5)

            # Now we'll load our facility and hardware mapping schema
            claimedscanners : Dict[Scanner, Facility] = {}
            mappedrelays : List[Tuple[str, int]] = []  # tuples (board, relay)

            self.Devices : List[str] = []
            self.Scanners: Dict[str, Scanner] = {}
            self.Facilities: Dict[str, Facility] = {}

            if config['scanners'] is not None:
                for sn, sv in config['scanners'].items():
                    if sn == '__line__':
                        continue
                    #TODO: should we disallow numbered scanners
                    dev = sv['board']
                    s = Scanner(name=sn,board=dev,scannerIndex=sv['scanner'])
                    self.Scanners[sn] = s
                    if dev not in self.Devices:
                        self.Devices.append(dev)

            if config['facilities'] is not None:
                for fn, fv in config['facilities'].items():
                    if fn == '__line__':
                        continue
                    b = fv['board']
                    s = fv['scanner']
                    r = fv['relay']

                    relaymap = (b, r)
                    scanners = [s]
                    os = None
                    if 'outscanner' in fv:
                        os = fv['outscanner']
                        scanners.append(os)

                    for ss in scanners:
                        if ss not in self.Scanners:
                            raise ConfigurationException(f"Scanner {ss} is not defined!")

                    for ss in scanners:
                        if ss in claimedscanners:
                            facil = claimedscanners[ss]
                            raise ConfigurationException(f"Scanner {ss} already claimed by facility '{facil.name}'")

                    inScanner = self.Scanners[s]
                    outScanner = self.Scanners[os] if 'outscanner' in fv else None

                    if relaymap in mappedrelays:
                        match = list(filter(lambda f: f.board == b and f.relay == r, self.Facilities.values()))

                        raise ConfigurationException(f"Facility {fn}: relay {r} on board {b} already claimed by facility {match[0].name}'")

                    duration = fv['unlockduration'] if 'unlockduration' in fv else 2.0
                    newfacility = Facility(fn, b, inScanner, r, duration, outscanner=outScanner )

                    self.Facilities[fn] = newfacility
                    for ss in scanners:
                        claimedscanners[ss] = newfacility
                    mappedrelays.append(relaymap)
                    if newfacility.outscanner is not None:
                        claimedscanners[newfacility.outscanner] = newfacility



            self.RawConfig = config

            engine = create_engine(f"sqlite:///{self.ActivityDb}")
            Session = sessionmaker(bind=engine)
            # session = Session()
            self.ScopedSession = scoped_session(Session)
            DoorControllerBase.metadata.create_all(engine)

        except Exception as e:
            raise ConfigurationException(e)

        FORMAT = "%(levelname)s:%(asctime)s:%(name)s - %(message)s"

        #TODO: bring back force=true for a 3.7 version install
        logging.basicConfig(filename=self.LogFile, level=logging.INFO, format=FORMAT)
        try:
            if "email_alerts" in config["system"]:
                self.HasEmail = True
                email = config["system"]["email_alerts"]
                smtp_handler = logging.handlers.SMTPHandler(mailhost=(email["host"], email["port"]),
                                                             fromaddr=email["from_addr"],
                                                             toaddrs=email["to_addrs"],
                                                             subject=email["subject"],
                                                             credentials=(email["smtp_user"],email["smtp_pass"]),
                                                             secure=(),timeout=3
                                                            )
                email_level = logging.CRITICAL if "level" not in email else \
                                        logging.CRITICAL if email["level"] == "critial" else \
                                        logging.CRITICAL if email["level"] == "fatal" else \
                                        logging.ERROR if email["level"] == "error" else \
                                        logging.WARNING
                smtp_handler.setLevel(email_level)
                smtp_handler.setFormatter(logging.Formatter(FORMAT))
                logging.root.addHandler(smtp_handler)
        except:
            pass


        try:
            self.mqtt_broker = config['system']['mqtt_broker'] if 'mqtt_broker' in config['system'] else None
            self.mqtt_topic = config['system']['mqtt_topic'] if 'mqtt_topic' in config['system'] else None
            self.mqtt_port = config['system']['mqtt_port'] if 'mqtt_port' in config['system'] else None
            logging.debug(f"MQTT setup to {self.mqtt_topic} via {self.mqtt_broker}:{self.mqtt_port}")
        except:
            pass

    def __init__(self, stringInput = None):
        self.Reload(stringInput)

    def getFacilities(self):
        return self.Facilities

    def getScanners(self):
        return self.Scanners

    def getDevices(self):
        return self.Devices

Config = Configuration()

#logging.basicConfig(level=logging.DEBUG)


#def SetConfig(config):
#    Config = config

#logging.basicConfig(level=logging.DEBUG,format=FORMAT)
# logging.basicConfig(filename=Config.LogFile, level=logging.INFO, format=FORMAT )




