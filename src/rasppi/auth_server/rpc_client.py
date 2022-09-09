import contextlib
from urllib.parse import urlparse
from base64 import b64encode
from json import loads, dumps
from socket import socket, AF_INET, AF_UNIX, SOCK_STREAM

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class RpcClient:

    class RpcConnection:
        def __init__(self, address, fernet):
            if address.scheme == 'tcp':
                address = ('127.0.0.1', address.port)  # this will only connect to localhost!
                self._socket = socket(AF_INET, SOCK_STREAM)
                self._destination = address
            elif address.scheme == 'unix':
                self._socket = socket(AF_UNIX, SOCK_STREAM)
                self._destination = address.path
            self._fernet = fernet
            self._rpc_id = 1

        def list_devices(self):
            message = self._make_message("list_devices")
            return self._exchange(message)

        def unlock(self,device, relay, duration, token):
            message = self._make_message("unlock",device=device,relay=relay,duration=duration,token=token)
            return self._exchange(message)

        def ping(self):
            return self._exchange(self._make_message("ping") )

        def _exchange(self, message): # This is a simple application. Messages should never be larger than 4k each
            payload = self._fernet.encrypt(dumps(message).encode("utf-8")) + b"\n"
            self._socket.sendall(payload)
            received = self._socket.recv(4096)
            decoded = self._fernet.decrypt(received).decode('utf-8')
            if decoded == "":
                raise Exception("Received garbage response")
            json = loads(decoded)
            if 'result' in json:
                return json['result']  # assume it's always valid
            if 'error' in json:
                raise Exception(json['error'])

        def _make_message(self, func, **kwargs):
            id = self._rpc_id
            self._rpc_id += 1
            return {"jsonrpc": "2.0", "method": func, "params": kwargs, "id": id}

        def __enter__(self):
            self._socket.settimeout(2.0)
            self._socket.connect(self._destination)
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            self._socket.close()


    # We'll attempt to connect to a the server on the local machine, if it's running
    def __init__(self, address, passcode: str):

        self.address = urlparse(address)

        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(),
                         length=32, salt=b'', iterations=640000)
        self._key = b64encode(kdf.derive(passcode.encode('utf-8')))
        self._fernet = Fernet(self._key)

    def connect(self):
        return self.RpcConnection(self.address,self._fernet)


