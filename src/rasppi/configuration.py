#load the config file
from typing import Dict, Any, List, Tuple
from hashids import Hashids
import jsonschema
import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from models import Base

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

class Configuration():
    config_schema = { "type" : "object",
                      "properties" : {
                          "system" : { "type" : "object",
                                       "additionalProperties": False,
                                       "properties" : {
                                           "logfile" : { "type" : "string"},
                                           "database": {"type": "string"},
                                           "__line__" : { },
                                       },
                                       "required" : ['logfile','database']},
                          "webpanel": {"type": "object",
                                       "additionalProperties": False,
                                     "properties": {
                                         "secretkey": {"type": "string"},
                                         "username": {"type": "string"},
                                         "password": {"type": "string"},
                                         "__line__": {},
                                     },
                                     "required": ['secretkey', 'username','password']},
                          "aws": {
                              "oneOf" : [
                              {"type": "object",
                                        "additionalProperties" : False,
                                       "properties": {
                                           "key_id": {"type": "string"},
                                           "access_key": {"type": "string"},
                                           "region": {"type": "string"},
                                           "incoming": {"type": "string"},
                                           "outgoing": {"type": "string"},
                                           "use_system_credentials": { "const" : False},
                                           "__line__": {},
                                       },
                                       "required": ['key_id', 'access_key', 'region','incoming','outgoing']},
                              {"type" : "object",
                                "additionalProperties" : False,
                                "properties" : {
                                    "use_system_credentials": {"const" : True},
                                    "__line__": {},
                                },
                                  "required" : ['use_system_credentials']}
                            ]},
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
                      "required" : ["system","webpanel","aws","scanners","facilities"]}

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
            except jsonschema.ValidationError as ve:
                if 'error_msg' in ve.schema:
                    raise ConfigurationException(ve.schema['error_msg'])
                else:
                    raise ConfigurationException(str(ve))

            if 'use_system_credentials' not in config['aws']:
                config['aws']['use_system_credentials'] = False

            self.DatabaseFile = config['system']['database']
            self.LogFile = config['system']['logfile']

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

            for sn, sv in config['scanners'].items():
                if sn == '__line__':
                    continue
                #TODO: should we disallow numbered scanners
                dev = sv['board']
                s = Scanner(name=sn,board=dev,scannerIndex=sv['scanner'])
                self.Scanners[sn] = s
                if dev not in self.Devices:
                    self.Devices.append(dev)

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

            engine = create_engine(f"sqlite:///{self.DatabaseFile}")
            Session = sessionmaker(bind=engine)
            session = Session()
            self.ScopedSession = scoped_session(Session)

            Base.metadata.create_all(engine)

            self.RawConfig = config
        except Exception as e:
            raise ConfigurationException(e)

        FORMAT = "%(levelname)s:%(asctime)s:%(name)s - %(message)s"
        logging.basicConfig(filename=self.LogFile, level=logging.INFO, format=FORMAT)

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




