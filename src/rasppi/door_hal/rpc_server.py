from collections import deque
from socket import socket, timeout, AF_UNIX, AF_INET, SOCK_STREAM
from threading import Thread
from urllib.parse import ParseResult
import os
import socketserver
from time import perf_counter

from cryptography.fernet import Fernet, InvalidToken
from jsonrpc import JSONRPCResponseManager
from json import dumps, loads

from config import Configuration
import logging
logger = logging.getLogger(__name__)

class RpcServer:
    def __init__(self, config: Configuration, dispatcher):
        self.jsonrpc = JSONRPCResponseManager()
        self.fernet = Fernet(config.key)
        self.dispatcher = dispatcher
        self.server = self.make_socket_server(config.address)
        self._unixsocket = None
        self.is_shutdown = False

    def make_socket_server(self, listen: ParseResult) -> socketserver.BaseServer:
        if listen.scheme == 'tcp':
            address = (listen.hostname, listen.port)
            server = socketserver.ThreadingTCPServer(address, self.handler.Creator(self.dispatcher, self.fernet, self.jsonrpc))
            return server
        elif listen.scheme == 'unix':
            try:
                os.unlink(listen.path)
            except FileNotFoundError:
                pass # this is OK
            except OSError:
                # can't unlink, in use?
                raise
            self._unixsocket = listen.path
            server = socketserver.ThreadingUnixStreamServer(listen.path, self.handler.Creator(self.dispatcher, self.fernet, self.jsonrpc))
            return server

    class handler(socketserver.BaseRequestHandler):
        queue = deque(maxlen=2048)

        @classmethod
        def Creator(cls, *args, **kwargs):
            def _hc(request, client_address, server):
                cls(request, client_address, server, *args, **kwargs)

            return _hc

        def __init__(self, request, client_adddress, server, dispatcher, fernet, rpcmanager):
            self.json_dispatcher = dispatcher
            self.fernet = fernet
            self.jsonrpc = rpcmanager

            super().__init__(request, client_adddress, server)

        def handle(self):
            print("Got a connection!")
            req: socket = self.request
            req.settimeout(0.25)

            try:
                while True:
                    try:
                        data = req.recv(1024)
                        if len(data) == 0:  # disconnected
                            return
                        for d in data:
                            if d == 10:  # 10 == '\n'
                                contents = bytes(self.queue)
                                #decrypted = self.fernet.decrypt(contents)
                                js = self.fernet.decrypt(contents).decode('utf-8')
                                s = perf_counter()
                                response = self.jsonrpc.handle(js, self.json_dispatcher)
                                logger.info(f"Handled a message: {perf_counter() - s} seconds.")
                                self.queue.clear()
                                response_encrypted = self.fernet.encrypt(response.json.encode("utf-8")) + b"\n"
                                req.send(response_encrypted)
                            else:
                                self.queue.append(d)
                    except timeout:
                        pass
            except BrokenPipeError:  # client has disconnected
                print("Client disconnected, BPE")
                return
            except ConnectionResetError:  # client has disconnected
                print("Client disconnected, CRE")
                return
            except InvalidToken:
                print("Invalid signature. Should do rate limiting")
                return
            except Exception as e:
                logger.exception("Something exceptional")
                return
            finally:
                req.close()
                print("Disconnecting")

    def run(self):
        self.is_shutdown = False
        self.server.serve_forever()

    def shutdown(self):
        t = Thread(target=self.server.shutdown)
        t.start()
        self.server.server_close()
        if self._unixsocket is not None:
            os.unlink(self._unixsocket)
        self.is_shutdown = True

class RpcClientException(Exception):
    pass

class RpcClient:

    # We'll attempt to connect to a the server on the local machine, if it's running
    def __init__(self, config: Configuration):
        if config.address.scheme == 'tcp':
            address = ('127.0.0.1', config.address.port) # this will only connect to localhost!
            self.socket = socket(AF_INET, SOCK_STREAM)
            self.destination = address
        elif config.address.scheme == 'unix':
            self.socket = socket(AF_UNIX, SOCK_STREAM)
            self.destination = config.address.path

        self.key = config.key
        self.fernet = Fernet(config.key)
        self.rpc_id = 1

    def list_devices(self):
        message = {"jsonrpc": "2.0", "method": "list_devices", "params": {}, "id": self.rpc_id}
        self.rpc_id += 1

        return self.exchange(message)

    def ping(self):
        message = {"jsonrpc": "2.0", "method": "ping", "params": {}, "id": self.rpc_id}
        self.rpc_id += 1

        return self.exchange(message)

    def exchange(self, message):
        payload = self.fernet.encrypt(dumps(message).encode("utf-8")) + b"\n"
        self.socket.sendall(payload)
        received = self.socket.recv(1024)
        decoded = self.fernet.decrypt(received).decode('utf-8')
        if decoded == "":
            raise RpcClientException("Received garbage response")
        json = loads(decoded)
        return json['result'] # assume it's always valid

    def __enter__(self):
        self.socket.settimeout(1.0)
        self.socket.connect(self.destination)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.socket.close()


