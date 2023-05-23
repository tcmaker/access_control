from enum import Enum
import logging
from typing import Dict, List, Tuple

import pyftdi
from pyftdi.usbtools import UsbDeviceDescriptor
from threading import Thread, Lock, Event, get_ident
from time import sleep, time
from pyftdi.ftdi import Ftdi

logger = logging.getLogger("Hardware")
#logger.setLevel(logging.DEBUG)
from datadog_logger import get_datadog_logger
dd_logger = get_datadog_logger("hardware", "hardware")


def list_devices():
    Ftdi.show_devices()

class LockTimeout():
    timeout: float
    credential: str

    def __init__(self, timeout: float, credential: str):
        self.timeout = timeout
        self.credential = credential

class ParserState(Enum):
    BEGIN = 1
    FOUND_FIRST = 2
    FOUND_CARRIAGE = 3
    FOUND_NEWLINE = 4


def query_devices(ignored_devices):
    if ignored_devices is not None and not hasattr(ignored_devices, '__iter__'):
        raise ValueError("Invalid ignored devices variable")

    ignored_ids = list(map(lambda d: d.device_id, ignored_devices))
    def map_url(dev):
        usb: UsbDeviceDescriptor = dev[0]
        vid = usb.vid
        pid = usb.pid
        if vid == 0x0403:
            vid = "ftdi"
        if pid == 0x6001:
            pid = "232"
        interface = dev[1]
        return f"ftdi://{vid}:{pid}:{usb.sn}/{interface}"

    all_devices = list(map(map_url, Ftdi.list_devices()))

    def not_ignored(dev):
        return dev not in ignored_ids

    if ignored_devices is None:
        to_query = all_devices
    else:
        to_query = list(filter(not_ignored, all_devices))

    discovered_boards = []
    for t in to_query:
        try:
            qb = ReaderBoard(deviceid=t)
            discovered_boards.append(qb.__repr__())
            qb.shutdown()
        except:
            pass
    return discovered_boards


class ReaderBoard:
    _unlockTimeouts: Dict[int, List[LockTimeout]]

    def __init__(self, deviceid):
        """

        :rtype: object
        """
        # self.input = queue.Queue(20)
        self.packetCallback = None
        self.errorCallback = None
        self.loop_crashed_callback = None

        self._commandLock = Lock()
        self._packetReadEvent = Event()
        self._startedEvent = Event()
        self._stoppedEvent = Event()
        self._run = True
        self.device_id = deviceid
        self._ftdi = Ftdi()
        self.numScanners = 0
        self.numRelays = 0
        self.relaystatus = {}
        self.version = "0.00"
        self.model = "unknown"
        self._unlockTimeouts = {}

        self._parserState = ParserState.BEGIN
        self._firstChar = ' '
        self._body = bytearray()

        # self.ftdi.open(vendor=0x0403,product=0x6001, serial=self.device)
        self._ftdi.open_from_url(self.device_id)
        self._ftdi.set_baudrate(57600)

        self._backgroundThread = Thread(target=self.background)
        self._backgroundThread.start()
        self._otherThread = Thread(target=self.lock_watch_loop)
        self._otherThread.start()

        if not self._startedEvent.wait(3.0):
            raise RuntimeError("Unable to startup board!")
        else:
            logger.log(logging.DEBUG, "Started up, disabling echo")
            self.send_command('e', '0')

            def get_device_info(fc, b, me):
                if fc == 'I':
                    info = {i.split(':')[0]: i.split(':')[1] for i in b.split(',')}
                    self.model = info['m']
                    self.version = info['v']
                    self.numRelays = int(info['r'])
                    self.numScanners = int(info['s'])
                    for a in range(self.numRelays):
                        self._unlockTimeouts[a] = []
                        self.relaystatus[a] = False

            self.packetCallback = get_device_info
            logger.info("calling getting device info")
            self.send_command('i', '')
            logger.info("done interrogating")

            self.packetCallback = None

    def shutdown(self):
        self._run = False
        self._commandLock.acquire()
        if not self._stoppedEvent.wait(3.0):
            raise TimeoutError("Failed to shut down board in a timely manner")
        self._backgroundThread.join()

    def background(self):
        self._ftdi.set_dtr(False)
        sleep(0.1)
        self._ftdi.set_dtr(True)  # Reset the device
        totaltime = 0
        ready_bytes = bytearray()
        started_up = False
        while totaltime < 5:
            sleep(0.1)
            totaltime += 0.1
            in_bytes = self._ftdi.read_data_bytes(50)
            if len(in_bytes) > 0:
                ready_bytes.extend(in_bytes)
                s = ready_bytes.decode(encoding="utf-8")
                if '? for help' in s:
                    totaltime = 1000
                    started_up = True
                    self._startedEvent.set()
                    try:
                        self.parse_loop()
                    except pyftdi.ftdi.FtdiError as error:
                        logger.fatal(f"USB ERROR! {error}")
                        if self.errorCallback is not None:
                            self.errorCallback(error)

        if not started_up:
            print("Failed to startup device!")
        logger.log(logging.DEBUG, "Shutting down FTDI device...")
        self._ftdi.close()
        self._commandLock.release()
        logger.log(logging.DEBUG, "Done shutting down hardware interface")

    def lock_watch_loop(self):
        try:
            if not self._startedEvent.wait(5000):
                logger.fatal("Didn't start up!")
            else:
                while self._run:
                    now = time()
                    tos: List[LockTimeout]
                    for (r, tos) in self._unlockTimeouts.items():
                        if any(tos):
                            for t in tos:
                                if now >= t.timeout:
                                    tos.remove(t)
                                    if len(tos) == 0:
                                        # close the door
                                        self.send_command('o', str(r))
                                        self.relaystatus[r] = False
                        elif self.relaystatus[r]:
                            self.send_command('o', str(r))
                            self.relaystatus[r] = False
                    sleep(0.25)
        except:
            dd_logger.critical("Unlock timeout loop crashed!", exc_info=True)
            if self.loop_crashed_callback:
                self.loop_crashed_callback()

    def parse_loop(self):
        totaltime = 0
        while self._run:
            sleep(0.1)
            totaltime += 0.1
            in_bytes = self._ftdi.read_data_bytes(50)
            self.parse(in_bytes)

            # Check out open/close queue
        self._stoppedEvent.set()

    def parse(self, in_bytes):
        if len(in_bytes) > 0:
            for b in in_bytes:
                c = chr(b)

                if self._parserState == ParserState.BEGIN or self._parserState == ParserState.FOUND_NEWLINE:
                    self._body.clear()
                    self._firstChar = c
                    self._parserState = ParserState.FOUND_FIRST
                elif self._parserState == ParserState.FOUND_FIRST:
                    if b != 0x0D:  # '\r'
                        self._body.append(b)
                    else:
                        self._parserState = ParserState.FOUND_CARRIAGE
                elif self._parserState == ParserState.FOUND_CARRIAGE:
                    if b != 0x0A:  # \n
                        # RAISE PARSING ERROR
                        self._parserState = ParserState.BEGIN
                    else:
                        self._parserState = ParserState.FOUND_NEWLINE
                        logger.log(logging.DEBUG, f"Read a packet: {self._firstChar}, {self._body}")
                        if self.packetCallback is not None:
                            try:
                                self.packetCallback(self._firstChar, self._body.decode("utf-8"), self.device_id)
                            except Exception as e:
                                logger.log(logging.FATAL, f"Failed calling packet callback: {e}")
                        if not (self._firstChar == 'e' and len(self._body) == 1 and self._body[0] == ord('0')):
                            self._packetReadEvent.set()

    def send_command(self, c: str, data: str):
        if len(c) != 1 or not c.isalpha():
            raise ValueError("c must be a single character!")

        message = f"{c}{data}\r"  # we won't add a \n, serial comms don't do that normally
        self._packetReadEvent.clear()
        d = message.encode("utf-8")
        if self._commandLock.acquire(timeout=1.0):
            if self._run:
                self._ftdi.write_data(d)
                if self._packetReadEvent.wait(3.0):
                    self._commandLock.release()
                    return self._body
                else:
                    logger.log(logging.ERROR, f"Failure to get response from board, it's down? Command: {c}:{data}")
                    # raise RuntimeError()
                    self._commandLock.release()
            else:
                self._commandLock.release()
        else:
            if self._run:
                raise SystemError("Sync Error")

    def __repr__(self):
        return f"{self.device_id} - {self.model} v{self.version}: {self.numScanners} scanners, {self.numRelays} relays"

    def Unlock(self, relay, duration, credential=None):
        if relay > self.numRelays:
            logger.error(f"Attempt to activate a relay board {self.device_id} doesn't have. {relay}")
            return
        now = time()
        self._unlockTimeouts[relay].append(LockTimeout(now + duration, credential))
        self.send_command('c', str(relay))
        self.relaystatus[relay] = True

    def Lock(self, relay, credential=None):
        if relay > self.numRelays:
            logger.error(f"Attempt to activate a relay board {self.device_id} doesn't have. {relay}")
            return
        if credential is None: #This only is raised by the webpanel, clear our all entries, and the relay
            # will be relocked by the loop
            self._unlockTimeouts[relay].clear()
        else:
            for tos in self._unlockTimeouts[relay]:
                if tos.credential == credential: # Clear all pending timeouts for the credential
                    self._unlockTimeouts[relay].remove(tos)
                    # At this point the timeout should be cleared
                    # during the watch loop


if __name__ == '__main__':
    '''This is here to support testing'''
    import argparse
    import signal

    logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser(description="Testing interface for the hardware layer")
    parser.add_argument('-d', '--device', help='connect to device', action='store', dest='target')
    parser.add_argument('-l', help='list devices', dest='list', action='store_true')

    args = parser.parse_args()

    if args.list:
        list_devices()
    elif args.target is not None:
        print("using device %s" % args.target)
        reader = ReaderBoard(args.target)


        def signal_handler(sig, frame):
            print("Shutting down...")
            reader.shutdown()
            # sys.exit()


        signal.signal(signal.SIGINT, signal_handler)


        def callback(firstchar, body, me):
            if firstchar == 'F':
                if body == "15408774,1":
                    print("Authorized!")
                    Thread(target=lambda: reader.Unlock(1, 3,"fob:15408774")).start()
                else:
                    print("Unauthorized!")


        reader.packetCallback = callback

        # for i in range(3):
        #    reader.sendCommand('c','1')
        #    sleep(0.5)
        #    reader.sendCommand('o', '1')
        #    sleep(0.5)
    else:
        parser.print_help()
