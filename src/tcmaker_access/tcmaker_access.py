import logging

from esp_interface import EspRfid
from models import ClubhouseFob
import requests
import typing
import os
from yaml import load
from yaml.loader import SafeLoader

class TcMakerAccess:
    def __init__(self, config):
        self._apikey = config['auth']['api_key']
        self.RequestHeaders = {
            # Generate an API token from the admin panel
            'Authorization': 'Bearer %s' % self._apikey
        }

        self._start_url = config['auth']['url']

        self._topic = config['topicname']
        self._broker = config['broker']

    def list_keyfobs(self, start_url=None):
        url = start_url if start_url is not None else self._start_url
        while url is not None:
            # Fetch the first page
            response = requests.get(url, headers=self.RequestHeaders)
            # Raise an exception on HTTP error
            response.raise_for_status()
            # Parse the JSON in the response into Python data structures
            body = response.json()
            # Update the loop for the next page
            url = body['next']
            # Loop over this page of results
            for result in body['results']:
                print(f"{result['code']}")
                yield result

    def refresh(self):
        with EspRfid(self._broker, self._topic) as esp:
            for fob in self.list_keyfobs(self._start_url):
                esp.update("front_door",  ClubhouseFob(fob))

if __name__ == "__main__":
    # load the configuration
    with open("config_template.yaml") as stream:
        config = load(stream, Loader=SafeLoader)

    config = config['tcmaker_access']
    apikey : str = config['auth']['api_key']
    if apikey.startswith("$"):
        apikey = os.getenv(apikey[1:])
    if apikey is None:
        exit(0)
    config['auth']['api_key'] = apikey
    tcmaker = TcMakerAccess(config)
    tcmaker.refresh()
