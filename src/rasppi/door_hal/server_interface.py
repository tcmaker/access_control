import urllib.parse

from config import Configuration
import requests
import logging
logging.getLogger('urllib3').setLevel(logging.FATAL)
logger = logging.getLogger(__name__)

class AuthServerInterface:

    def __init__(self, config: Configuration):
        self._config = config

    def ping(self):
        response = requests.get(self._config.auth_service_url + "/ping")
        return response.text

    def scan(self,device, scanner, credential):
        try:
            response = requests.post(self._config.auth_service_url + f'/scan?{urllib.parse.urlencode({"device":device,"scanner": scanner,"credential": credential})}')
            return response.json
        except:
            logger.warning("Failed to reach auth_service")

    def announce(self,device_id):
        pass



