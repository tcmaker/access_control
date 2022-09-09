import datetime
import signal
import threading
from random import choice
from time import perf_counter

import getkey
from jsonrpc import Dispatcher

from config import Configuration
from rpc_server import RpcServer
from server_interface import AuthServerInterface
import logging
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    try:
        tt: threading.Thread = None

        jd = Dispatcher()
        startup_time = datetime.datetime.now()

        @jd.add_method
        def unlock(device, relay, duration, token):
            s = perf_counter()
            print(f"Unlocking {device} relay {relay}, at {token}, for {duration} seconds!")
            return 0;

        @jd.add_method
        def lock(device, relay, token):
            print(f"Locking {device} relay {relay}, at {token}!")
            return 0

        @jd.add_method
        def list_devices():
            return {d[0]: d[1] for d in devices.items()}


        # DIAGNOSTIC METHODS
        @jd.add_method
        def uptime():
            return (datetime.datetime.now() - startup_time).total_seconds()


        @jd.add_method
        def ping():
            return "pong"


        devices = {'sim_id': {'model': 'sim_device', 'device_id': 'sim_id', 'scanners': 1, 'relays': 1}}
        fobs = ['12345678']
        c = Configuration(auth='http://127.0.0.1:8443',listen='tcp://0.0.0.0:3119',devices={'myalias' : 'sim_id'})
        c.map_aliases(devices)
        si = AuthServerInterface(c)


        def on_scan(first_char: str, body: str, device_id: str):
            alias = c.get_alias_from_device_id(device_id)
            si.scan(alias,0,f"{first_char}:{body}")

        rpcserver = RpcServer(c, jd)

        def close_it_up(sig, frame):
            if sig == signal.SIGINT:
                logger.info("CTRL+C raised, terminating")
            elif sig == signal.SIGTERM:
                logger.info("Termination signaled, closing")
            rpcserver.shutdown()


        def thingy():
            while not rpcserver.is_shutdown:
                try:
                    c = getkey.getkey(blocking=False)
                    if c == 's':
                        fob = choice(fobs)
                        print(f"Simulating scan of {fob}!")
                        on_scan('f',fob,'sim_id')
                except TimeoutError:
                    pass


        signal.signal(signal.SIGINT, close_it_up)
        signal.signal(signal.SIGTERM, close_it_up)
        print(list_devices())
        tt = threading.Thread(target=thingy)
        tt.start()
        rpcserver.run()  # never returns
    finally:
        if tt is not None:
            tt.join()