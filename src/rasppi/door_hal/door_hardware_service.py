import datetime
import logging
import select
import selectors
import signal
import sys
import termios
import threading
from typing import List, Dict
from time import perf_counter

from jsonrpc import Dispatcher

import error_codes
from server_interface import AuthServerInterface
from rpc_server import RpcServer, RpcClient, RpcClientException
from reader_board import start_devices, ReaderBoard

VERSION='1.0'
# Methods

# Actions
#  Lock, Unlock

# Diagnostics
#  Hardware Info

logger = logging.getLogger(__name__)

def process_args(sysargs):
    import argparse

    parser = argparse.ArgumentParser(
        description="""Access control hardware server""", epilog="I'll put my name in here at some point")

    parser.add_argument('-c', '--config', action='store', dest='config', default=None,
                        help="specify non-default configuration file")
    parser.add_argument('-d', '--detect', action='store_true', dest='detect',
                        help="probe for compatible devices and exit")
    parser.add_argument('-l', '--listen', action='store', dest='address', help="override listening address")
    parser.add_argument('-t', '--test', action='store_true', dest='test',
                        help="test configuration settings for validity and exit")
    parser.add_argument('-v', '--version', action='store_true', dest='version', help="show version and exit")
    parser.add_argument('-k', '--key', action='store', dest='key', help='specify network key to use',metavar='KEYFILE')
    parser.add_argument('-q', '--quiet', action='store_true', dest='quiet', help="suppress non-error messages")

    args = parser.parse_args(sysargs)
    return args

def main(args, hardware_finder = start_devices):

    if args.version:
        print(f"{sys.argv[0]} {VERSION}")
        exit(0)

    logging.basicConfig(level=logging.ERROR if args.quiet else logging.DEBUG)

    # load our config
    from config import Configuration, ConfigurationException

    try:
        c = Configuration(args)
    except ConfigurationException as ce:
        print(ce.message)
        exit(ce.code)
    except:
        # TODO: format config error message
        logger.exception("Failed to initialize configuration")
        exit(error_codes.INVALID_CONFIG)

    # Further test /validate configuration here
    # try connecting to auth server
    try:
        c.test(args.quiet)
    except ConfigurationException as ce:
        print(ce.message)
        exit(ce.code)

    if args.test:
        exit(0)

    try:
        with RpcClient(c) as client:
            if client.ping() == "pong": # there is already an instance running?
                if args.detect:
                    device_ids = client.list_devices()
                    print(device_ids)
                    exit(0)
                else:
                    print("Service is already running!")
                    exit(error_codes.INSTANCE_ALREADY_RUNNING)
    except RpcClientException:
        # don't actually do anything here. We'll assume whatever was
        # occupying the port is something else, and we'll complain about
        # the port being occupied later
        pass
    except ConnectionRefusedError:
        pass #This is ok, another instance isn't currently running

    # detect and interrogate our hardware
    devices: Dict[str, ReaderBoard] = hardware_finder()

    try:
        if args.detect:

            print(devices)
            exit(0)

        c.map_aliases(devices)
        print(c.devices)
        # OK, we're ready to start up our actual server.
        jd = Dispatcher()
        startup_time = datetime.datetime.now()

        @jd.add_method
        def unlock(device, relay, duration, token):
            s = perf_counter()
            devices[device].Unlock(relay, duration, token)
            print(f"Took {perf_counter() - s} seconds to unlock!")
            return 0;

        @jd.add_method
        def lock(device, relay, token):
            devices[device].Lock(relay,token)
            return 0

        @jd.add_method
        def list_devices():
            return {d[0] : d[1].json() for d in c.devices.items()}

        # DIAGNOSTIC METHODS
        @jd.add_method
        def uptime():
            return (datetime.datetime.now() - startup_time).total_seconds()

        @jd.add_method
        def ping():
            return "pong"

        si = AuthServerInterface(c)

        def on_scan(first_char: str, body: str, device_id: str):
            if first_char == 'F' or first_char == 'P':  # keyfob
                (code, scanner_index) = body.split(',')
                scanner_index = int(scanner_index)
                credential_type = 'fob' if first_char == 'F' else 'passcode'
                credential_value = code
                credential_ref = f'{credential_type}:{credential_value}'
                si.scan(c.get_alias_from_device_id(device_id), scanner_index, credential_ref)

        for d in devices.values():
            d.packetCallback = on_scan

        rpcserver = RpcServer(c, jd)
        def close_it_up(sig, frame):
            if sig == signal.SIGINT:
                logger.info("CTRL+C raised, terminating")
            elif sig == signal.SIGTERM:
                logger.info("Termination signaled, closing")
            rpcserver.shutdown()

        signal.signal(signal.SIGINT, close_it_up)
        signal.signal(signal.SIGTERM, close_it_up)

        rpcserver.run()  # never returns
    finally:
        for d in devices.values():
            d.shutdown()

if __name__ == "__main__":
    args = process_args(sys.argv[1:])
    main(args)