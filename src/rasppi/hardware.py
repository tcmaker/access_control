from enum import Enum
import logging
import pyftdi
from pyftdi.usbtools import UsbDeviceDescriptor
from threading import Thread, Lock, Event, get_ident
import queue
from time import sleep, time
from pyftdi.ftdi import  Ftdi

logger = logging.getLogger("Hardware")
logger.setLevel(logging.DEBUG)

def list_devices():
    Ftdi.show_devices()

class ParserState(Enum):
    BEGIN = 1
    FOUND_FIRST = 2
    FOUND_CARRIAGE = 3
    FOUND_NEWLINE = 4

def QueryDevices(ignoredDevices):
    if ignoredDevices != None and not hasattr(ignoredDevices,'__iter__'):
        raise ValueError("Invalid ignored devices variable")
    def mapUrl(dev):
        usb: UsbDeviceDescriptor = dev[0]
        vid = usb.vid
        pid = usb.pid
        if vid == 0x0403:
            vid = "ftdi"
        if pid == 0x6001:
            pid = "232"
        interface = dev[1]
        return f"ftdi://{vid}:{pid}:{usb.sn}/{interface}"
    allDevices = list(map(mapUrl, Ftdi.list_devices()))
    if(ignoredDevices == None):
        return allDevices

    def notIgnored(dev):
        return dev not in ignoredDevices
    return list(filter(notIgnored, allDevices))



class ReaderBoard():
    def __init__(self, deviceid):
        """

        :rtype: object
        """
        #self.input = queue.Queue(20)
        self.packetCallback = None
        self.errorCallback = None

        self._commandLock = Lock()
        self._packetReadEvent = Event()
        self._startedEvent = Event()
        self._stoppedEvent = Event()
        self._run = True
        self._deviceId = deviceid
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



        #self.ftdi.open(vendor=0x0403,product=0x6001, serial=self.device)
        self._ftdi.open_from_url(self._deviceId)
        self._ftdi.set_baudrate(57600)

        self._backgroundThread = Thread(target=self.background)
        self._backgroundThread.start()
        self._otherThread = Thread(target=self.lockWatchLoop)
        self._otherThread.start()

        if not self._startedEvent.wait(3.0):
            raise RuntimeError("Unable to startup board!")
        else:
            logger.log(logging.DEBUG,"Started up, disabling echo")
            self.sendCommand('e','0')

            def getDeviceInfo(fc, b, me):
                if fc == 'I':
                    info = {i.split(':')[0]: i.split(':')[1] for i in b.split(',')}
                    self.model =info['m']
                    self.version = info['v']
                    self.numRelays = int(info['r'])
                    self.numScanners = int(info['s'])
                    for a in range(self.numRelays):
                        self._unlockTimeouts[a] = []
                        self.relaystatus[a] = False

            self.packetCallback = getDeviceInfo
            logger.info("calling getting device info")
            self.sendCommand('i','')
            logger.info("done interrogating")

            self.packetCallback = None



    def shutdown(self):
        self._run = False
        self._commandLock.acquire()
        if not self._stoppedEvent.wait(3.0):
            raise TimeoutError("Failed to shut down board in a timely manner")
        self._backgroundThread.join()

    def background(self):
        self._ftdi.set_dtr(0)
        sleep(0.1)
        self._ftdi.set_dtr(1) #Reset the device
        totaltime = 0
        readyBytes = bytearray()
        startedUp = False
        while totaltime < 5:
            sleep(0.1)
            totaltime += 0.1
            bytes = self._ftdi.read_data_bytes(50)
            if len(bytes) > 0:
                readyBytes.extend(bytes)
                s = readyBytes.decode(encoding="utf-8")
                if '? for help' in s:
                    totaltime = 1000
                    startedUp = True
                    self._startedEvent.set()
                    try:
                        self.parseLoop()
                    except pyftdi.ftdi.FtdiError as error:
                        logger.fatal(f"USB ERROR! {error}")
                        if self.errorCallback is not None:
                            self.errorCallback(error)


        if not startedUp:
            print("Failed to startup device!")
        logger.log(logging.DEBUG,"Shutting down FTDI device...")
        self._ftdi.close()
        self._commandLock.release()
        logger.log(logging.DEBUG,"Done shutting down hardware interface")

    def lockWatchLoop(self):
        if not self._startedEvent.wait(5000):
            logger.fatal("Didn't start up!")
        else:
            while self._run:
                now = time()
                for (r,tos) in self._unlockTimeouts.items():
                        for t in tos:
                            if now >= t:
                                tos.remove(t)
                                if len(tos) == 0:
                                    #close the door
                                    self.sendCommand('o',str(r))
                                    self.relaystatus[r] = False
                sleep(0.25)

    def parseLoop(self):
        totaltime = 0
        while self._run:
            sleep(0.1)
            totaltime += 0.1
            bytes = self._ftdi.read_data_bytes(50)
            self.parse(bytes)

            #Check out open/close queue
        self._stoppedEvent.set()

    def parse(self, bytes):
        if len(bytes) > 0:
            for b in bytes:
                c = chr(b)

                if self._parserState == ParserState.BEGIN or self._parserState == ParserState.FOUND_NEWLINE:
                    self._body.clear()
                    self._firstChar = c
                    self._parserState = ParserState.FOUND_FIRST
                elif self._parserState == ParserState.FOUND_FIRST:
                    if(b != 0x0D): # '\r'
                        self._body.append(b)
                    else:
                        self._parserState = ParserState.FOUND_CARRIAGE
                elif self._parserState == ParserState.FOUND_CARRIAGE:
                    if(b != 0x0A): # \n
                        #RAISE PARSING ERROR
                        self._parserState = ParserState.BEGIN
                    else:
                        self._parserState = ParserState.FOUND_NEWLINE
                        logger.log(logging.DEBUG,f"Read a packet: {self._firstChar}, {self._body}")
                        if self.packetCallback != None:
                            try:
                                self.packetCallback(self._firstChar, self._body.decode("utf-8"), self._deviceId)
                            except Exception as e:
                                logger.log(logging.FATAL,f"Failed calling packet callback: {e}")
                        if not (self._firstChar == 'e' and len(self._body) == 1 and self._body[0] == ord('0')):
                            self._packetReadEvent.set()


    def sendCommand(self, c : str, data: str):
        if(len(c) != 1 or not c.isalpha()):
            raise ValueError("c must be a single character!")
        expectedResult = c.upper()
        message = f"{c}{data}\r" # we won't add a \n, serial comms don't do that normally
        self._packetReadEvent.clear()
        d = message.encode("utf-8")
        if self._commandLock.acquire(timeout=1.0):
            if self._run:
                self._ftdi.write_data(d)
                if self._packetReadEvent.wait(3.0):
                    self._commandLock.release()
                    return self._body
                else:
                    logger.log(logging.ERROR,"Failure to get response from board, it's down?")
                    #raise RuntimeError()
                    self._commandLock.release()
            else:
                self._commandLock.release()
        else:
            if self._run:
                raise SystemError("Sync Error")

    def Unlock(self, relay, duration):
        if relay > self.numRelays:
            logger.error(f"Attempt to activate a relay board {self._deviceId} doesn't have. {relay}")
            return
        now = time()
        self._unlockTimeouts[relay].append(now + duration)
        self.sendCommand('c',str(relay))
        self.relaystatus[relay] = True

    def Lock(self,relay):
        if relay > self.numRelays:
            logger.error(f"Attempt to activate a relay board {self._deviceId} doesn't have. {relay}")
            return
        self._unlockTimeouts[relay].clear()
        self._unlockTimeouts[relay].append(0)
        self.relaystatus[relay] = False


if __name__ == '__main__':
    '''This is here to support testing'''
    import argparse
    import signal, sys

    logging.basicConfig(level=logging.DEBUG)

    parser = argparse.ArgumentParser(description="Testing interface for the hardware layer")
    parser.add_argument('-d','--device', help='connect to device', action='store', dest='target')
    parser.add_argument('-l',help='list devices',dest='list', action='store_true')

    args = parser.parse_args()

    if args.list:
        list_devices()
    elif args.target != None:
        print("using device %s" % (args.target) )
        reader = ReaderBoard(args.target)
        def signal_handler(sig, frame):
            print("Shutting down...")
            reader.shutdown()
            #sys.exit()
        signal.signal(signal.SIGINT, signal_handler)

        def callback(firstchar, body, me):
            if(firstchar == 'F'):
                if(body == "15408774,1"):
                    print("Authorized!")
                    Thread(target=lambda : reader.Unlock(1,3)).start()
                else:
                    print("Unauthorized!")


        reader.packetCallback = callback

        #for i in range(3):
        #    reader.sendCommand('c','1')
        #    sleep(0.5)
        #    reader.sendCommand('o', '1')
        #    sleep(0.5)
    else:
        parser.print_help()