import os
import re
from base64 import b64encode
from os import stat as osstat
import stat
from operator import countOf

import requests.exceptions
import validators
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from yaml import load, SafeLoader
import logging
import error_codes
from urllib.parse import urlparse
from typing import Tuple, List, Dict, Optional, Any

logger = logging.getLogger(__name__)

class ConfigurationException(Exception):
    def __init__(self,message,code):
        self.message = message
        self.code = code
        super().__init__(self.message)


class Configuration():

    name: str

    #Order of values, kwargs, then cli, then file.
    # Only one file will be used, order of test: passed location, then default locations, in array order
    # empty or incomplete file is ok if cli and or kwargs provides all values
    def __init__(self, cli = None, defaultlocation=['./.doorconfig.yaml','/etc/doorconfig'], defaultkey='.networkkey',**kwargs):
        self.valid_device_alias_rex = re.compile('^[a-zA-Z][a-zA-Z0-9_]*$')
        self.devices = {} # maps aliases to devices
        self.aliases = {} # maps device_ids to aliases

        if hasattr(cli,'config') and cli.config is not None:
            defaultlocation = [cli.config]
        if 'config' in kwargs:
            defaultlocation = [kwargs['config']]

        yaml = None
        for dl in defaultlocation: #this will be default or overridden by cli
            try:
                with open(dl) as stream:
                    yaml = load(stream, Loader=SafeLoader)
                    break
            except FileNotFoundError:
                continue

        if yaml is None:
            raise ConfigurationException(f"Specified configuration file{'s' if len(defaultlocation) > 1 else ''} '{defaultlocation}' not found!", error_codes.CONFIG_NOT_FOUND)

        #we'll first attempt to get all the values, then validate them.

        self.name = self.getcliyamlkwargs("name", kwargs, cli, yaml, default="unnamed")
        self.listen = self.getcliyamlkwargs('listen', kwargs, cli, yaml, "Listen address not specified!", error_codes.NO_LISTEN_ADDRESS)
        self.auth_service_url = self.getcliyamlkwargs('auth', kwargs, cli, yaml,
                                                      "Authorization service url not specified!",
                                                      code=error_codes.NO_AUTH_URL)

        defaultkey = self.getcliyamlkwargs("key",kwargs,cli,yaml,"Network key not specified!",777, defaultkey)
        try:
            with open(defaultkey) as keyfile:
                keyvalue = keyfile.readline().strip()
                # TODO check permissions
                if not kwargs.get("ignore_key_permissions",False):
                    # TODO
                    pass
                if keyvalue == "":
                    raise ConfigurationException("Network key file '{defaultkey}' is empty!",error_codes.KEY_EMPTY)
                if not kwargs.get('skip_key_compute',False):
                    self.key = self.compute_key(keyvalue)
                else:
                    self.key = "SKIPPED"
        except FileNotFoundError:
            raise ConfigurationException(f"Network key file '{defaultkey}' is missing!",error_codes.KEY_MISSING)
        except Exception as e:
            if isinstance(e,ConfigurationException):
                raise
            else:
                raise ConfigurationException("Unexpected error",-1)


        if self.valid_device_alias_rex.match(self.name) == None:
            raise ConfigurationException(f"Invalid device name \"{self.name}\"!")

        # validate listening address
        p = urlparse(self.listen)
        if p.scheme not in ['tcp','unix']:
            raise ConfigurationException(f"Invalid address scheme '{p.scheme}'. Supported listen address formats are [tcp|unix]",code=error_codes.INVALID_LISTEN_ADDRESS)
        if p.scheme == 'tcp':
            # must be host:port
            try:
                pp = p.port
            except ValueError as ve:
                raise ConfigurationException(f"Invalid listen address: {ve.args[0]}",code=error_codes.INVALID_LISTEN_ADDRESS)
        elif p.scheme == 'unix':
            # test that the path is either free or occupied by a socket
            try:
                mode = osstat(p.path).st_mode
                if not stat.S_ISSOCK(mode):
                    raise ConfigurationException(f"Specified socket '{p.path}' is occupied!",
                                                 error_codes.SOCKET_PATH_NOT_A_SOCKET)
            except FileNotFoundError:
                # this is OK.
                pass
        self.address = p


        #validate names
        self.devices =  self.getcliyamlkwargs('devices',kwargs,cli,yaml,"Missing device alias definition",code=1111)
            # validate device alias list
        for k in self.devices.keys():
            if self.valid_device_alias_rex.match(k) == None:
                raise ConfigurationException(f"Alias {k} is an invalid alias.",code=111)
        counts = [(countOf(self.devices.values(), v),v) for v in set(self.devices.values())]
        for c in counts:
            if c[0] > 1:
                raise ConfigurationException(f"Board {c[1]} has multiple aliases!")
        self.aliases = {v: k for k, v in self.devices.items()}

        logger.debug(f"Aliases: {self.aliases}")
        logger.debug(f"Devices: {self.devices}")
        with open('/var/lib/dbus/machine-id') as machine:
            self.machine_id = machine.readline()


    def getcliyamlkwargs(self, key, kwargs, cli, yaml, message=None, code=None, default=None):
        # priority is first kwargs, then cli, then config file
        if key in kwargs:
            g = kwargs[key]
        else:
            g = getattr(cli,key) if hasattr(cli,key) else None
            if g is None:
                if 'hardware_service' not in yaml:
                    raise ConfigurationException("Required section 'hardware_service' missing from config file.",
                                                 code=error_codes.CONFIG_SECTION_MISSING)
                hs = yaml['hardware_service']
                if key not in hs:
                    if default is None:
                        raise ConfigurationException(message,code=code)
                    return default
                else:
                    g = hs[key]
        return g

    def get_alias_from_device_id(self,device):
        return self.aliases[device]

    def get_device_id_from_alias(self,alias):
        return self.devices[alias]

    def map_aliases(self, devices):
        self.devices = {self.aliases[name]: devices[name] for name in devices.keys()}

    def test(self,quiet):
        from server_interface import AuthServerInterface
        """Do extended validity checks. These are skipped during normal startup"""

        #check auth server
        si = AuthServerInterface(self)
        try:
            if si.ping() != "pong":
                raise ConfigurationException("Unexpected response from authentication server",code=22123)
        except requests.exceptions.ConnectionError:
            #raise ConfigurationException("Authentication server is down or misconfigured", code=222)
            logger.warning("Authentication server is down or misconfigured")
        except requests.exceptions.RequestException:
            logger.warning("Authentication server is down or misconfigured")
            #raise ConfigurationException("Unable to communicate with auth server!",code=2222)

    def compute_key(self,config_key):
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(),
                         length = 32, salt = b'', iterations = 640000)
        return b64encode(kdf.derive(config_key.encode('utf-8')))

