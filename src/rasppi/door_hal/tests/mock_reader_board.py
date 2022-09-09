
class MockReaderBoard:

    def __init__(self, device_id, **kwargs):
        #num relays

        self.device_id = device_id
        self.version = kwargs.get('version',"0.00")
        self.model = kwargs.get('model',"unknown")

        self.scanner_names = []
        self.relay_names = []

        self.packetCallback = None
        self.errorCallback = None

        self.numScanners = kwargs.get('numScanners',0)
        self.numRelays = kwargs.get('numRelays',0)
        self.relaystatus = {}



    def shutdown(self):
        pass

    def background(self):
        pass

    def Unlock(self):
        pass

    def Lock(self,):
        pass