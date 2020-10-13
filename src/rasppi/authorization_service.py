from typing import List, Any, Dict, Optional, Iterable
from hardware import ReaderBoard
import logging
logger = logging.getLogger("auth")
from threading import Thread, Lock
from multiprocessing import Queue
from queue import Empty
from configuration import Config, Facility, Scanner
from models import Credential, Activity, AccessRequirement
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from uuid import uuid4
from aws_wrapper import read_queue, write_queue

class AuthorizationService():
    boards: Dict[str, ReaderBoard]

    def __init__(self, inputQueue: Queue, outputQueue : Queue):
        self._run = True
        self.boards = {}
        self.boardLock = Lock()
        self.awslock = Lock()
        self._inqueue = inputQueue
        self._outqueue = outputQueue
        self.run()


    def reloadBoards(self):
        self.boardLock.acquire()
        for bn,bv in self.boards.items():
            logger.debug(f"Shutting down board: {bn}")
            bv.shutdown()
        self.boards.clear()

        allBoards = []
        try:
            for f in Config.getDevices():
                try:
                    if f not in allBoards:
                        logger.debug(f"Staring up board: {f}")
                        newReader = ReaderBoard(f)
                        newReader.packetCallback = self.onScan
                        self.boards[f] = newReader
                        allBoards.append(f)
                except Exception as e:
                    logger.fatal(f"Unable to startup hardware {f}: {e}")
        finally:
            self.boardLock.release()

    def run(self):
        self.reloadBoards()
        self.DoAwsUploadDownload()
        while self._run:
            try:
                r = self._inqueue.get(block=True,timeout=60)
            except Empty:
                #Do our AWS checks
                self.DoAwsUploadDownload()
                continue

            if type(r) == tuple:
                if r[0] == 'unlock':
                    (c,board,relay,duration,credential) = r
                    self.boards[board].Unlock(relay, duration,credential)
                elif r[0] == "lock":
                    (a, board, relay, credential) = r
                    self.boards[board].Lock(relay,credential)
                elif r[0] == 'aws':
                    self.DoAwsUploadDownload()
                elif r[0] == "status":
                    fv: Facility
                    #def facilityStatus(f : Facility):
                    #    return self.boards[f.board].relaystatus[f.relay]
                    status = dict((f.name,self.boards[f.board].relaystatus[f.relay]) for f in Config.Facilities.values())
                    #status = list(map(facilityStatus,Config.Facilities.values()))
                    self._outqueue.put(status)
                elif r[0] == "query":
                    response = []
                    for bn,bv in self.boards.items():
                        response.append(f"{bn} - {bv.model} v{bv.version}: {bv.numScanners} scanners, {bv.numRelays} relays")
                    self._outqueue.put(response)
                elif r[0] == "reload":
                    # We have to do this here, even though it's also done in the webpanel, because
                    # Config is different here vs webpanel due to multiprocessing
                    Config.Reload()
                    self.reloadBoards()
                    self._outqueue.put("OK")

    def lock(self, board, relay, credential):
        self._inqueue.put(('lock',board,relay,credential))

    def unlock(self, board, relay, duration, credential):
        self._inqueue.put(('unlock',board,relay,duration,credential))

    def trigger_notify(self):
        self._inqueue.put(('aws',))

    def findFacility(self, board, scannerIndex):
        target : Scanner = None
        for sb,si in Config.getScanners().items():
            if si.board == board and si.scannerIndex == scannerIndex:
                target = si
                break
        if target is not None:
            for fn, fv in Config.getFacilities().items():
                if fv.scanner == target or fv.outscanner == target:
                    return (fv, fv.scanner if fv.scanner == target else fv.outscanner)
        else:
            return (None,None)

    def onScan(self, firstChar : str, body : str, deviceId : str):
        db: Session = Config.ScopedSession()
        try:
            if firstChar == 'F' or firstChar == 'P': #keyfob
                (code, scannerIndex) = body.split(',')
                scannerIndex = int(scannerIndex)
                credential_value = f"{'fob' if firstChar == 'F' else 'passcode'}:{code}"
                (facility,scanner) = self.findFacility(deviceId, scannerIndex)
                if facility is not None:
                    # OK, we've determined the facility that was scanned for
                    credential: Credential = db.query(Credential).filter(Credential.credential == code) \
                        .filter(Credential.type == (Credential.KEYFOB if firstChar == 'F' else Credential.PASSCODE))  \
                        .filter(Credential.facility == facility.name) \
                        .order_by(Credential.priority.desc()).first()
                    if credential is not None:
                        if facility.outscanner == scanner:
                            activity = Activity(memberid=credential.memberid, authorization="none",
                                                result="exit",
                                                timestamp=datetime.now(),
                                                facility=facility.name,
                                                credentialref=credential_value,
                                                notified=False)
                            self.lock(facility.board, facility.relay, credential_value)
                            db.add(activity)
                            db.commit()
                            return

                        # check against access restrictions
                        required: Iterable[AccessRequirement] = db.query(AccessRequirement).filter(
                            AccessRequirement.facility == facility.name).order_by(
                            AccessRequirement.requiredpriority.desc()).all()
                        grant = False
                        if any(required):
                            requirement: AccessRequirement
                            for requirement in required:
                                if requirement.is_active():
                                    grant = credential.priority >= requirement.requiredpriority
                            activity = Activity(memberid=credential.memberid, authorization=credential.tag,
                                                result="granted" if grant else "denied",
                                                timestamp=datetime.now(),
                                                credentialref=credential_value,
                                                facility=facility.name,
                                                notified=False)
                            db.add(activity)
                            db.commit()
                            # activate hardware
                            if grant:
                                self.unlock(facility.board, facility.relay, facility.unlockduration,credential_value)
                            return
                    else: #scan of a non-existent user
                        if(scanner == facility.outscanner):
                            logger.error("Exit scan of a non-existent user!")
                        activity = Activity(memberid="unknown", authorization="none",
                                            result="exit" if scanner == facility.outscanner else "denied",
                                            timestamp=datetime.now(),
                                            credentialref=credential_value,
                                            facility=facility.name,
                                            notified=False)
                        db.add(activity)
                        db.commit()
                        return
                #unknown scanner/facility
                activity = Activity(memberid="",authorization="",credentialref=credential_value,result="denied",timestamp=datetime.now(),facility =facility.name if facility is not None else None,notified=False)
                db.add(activity)
                db.commit()
        finally:
            db.close()
            self.trigger_notify()
        pass

########################################
# AWS Integration Parts
########################################
    def DoAwsUploadDownload(self):
        daud = Thread(target=self._DoAwsUploadDownload)
        daud.start()

    def _DoAwsUploadDownload(self):
        self.awslock.acquire()
        try:
            db: Session = Config.ScopedSession()
        #get any new messages
            read_queue(callback=self.processIncomingMessage)


        #upload any new messages
            messages = db.query(Activity).filter(Activity.notified == False).limit(20).all()
            def awsmap(a : Activity):
                return (a, { "action" : "activity",
                                   "result" : a.result,
                                "facility" : a.facility,
                                "memberid" : a.memberid,
                                "authorization" : a.memberid,
                                "credentialref" : a.credentialref,
                                "timestamp" : a.timestamp.isoformat()})
            if len(messages) > 0:
                (written,failed) = write_queue(map(awsmap,messages))
                w: Activity
                for w in written:
                    w.notified = True
                db.commit()

        finally:
            self.awslock.release()
            db.close()


    def processIncomingMessage(self, message):

        if "action" not in message:
            raise Exception("Invalid message!")
        action = message['action']
        db: Session = Config.ScopedSession()
        try:
            if action == "activate":
                facilityName = message['facility']
                if facilityName not in Config.getFacilities():
                    return False
                credential = message['code']
                credtype = message['codetype']
                memberid = str(message['member'])
                if (nonmatch := db.query(Credential).filter(Credential.credential == credential).filter(Credential.type == credtype).filter(Credential.memberid != memberid).first()) is not None:
                #if nonmatch is not None:
                    raise Exception(f"Got a duplicate credential with non-matching memberid. {nonmatch.credential} : {nonmatch.memberid}")

                cred = Credential(facility=facilityName,
                                  memberid=memberid,
                                  credential=credential,
                                  type=credtype,
                                  effective=datetime.fromisoformat(message['effective']),
                                  expiration=datetime.fromisoformat(message['expiration']),
                                  tag=message['tag'],
                                  priority=message['priority'])
                db.add(cred)
                db.commit()
                return True
            elif action == "revoke":
                tag = message['tag']
                facility = message['facility']
                revoked = db.query(Credential).filter(Credential.tag == tag).filter(Credential.facility == facility).first()
                if revoked is not None:
                    db.delete(revoked)
                    db.commit()
                    return True
                else:
                    return False

            elif action == "modify":
                member = str(message["member"])
                oldcode = message["oldcode"],
                oldtype = message["oldtype"]
                newtype = message["newtype"]
                newcode = message["newcode"]
                facility = message["facility"]
                credentials = db.query(Credential).filter(Credential.memberid == member).filter(Credential.type == oldtype).filter(Credential.credential == oldcode).filter(Credential.facility == facility).all()
                c: Credential
                for c in credentials:
                    c.type = newtype
                    c.credential = newcode
                db.commit()
            elif action == "set-requirement":
                facility = message["facility"]
                if facility not in Config.getFacilities():
                    return False
                tag = message["tag"]
                required = message["requiredpriority"]
                timespec = message["timespec"]
                description = message["description"] if "description" in message else ""
                ar = AccessRequirement(requiredpriority=required, facility=facility,tag=tag, timespec=timespec, description=description)
                if ar.validate():
                    db.add(ar)
                    db.commit()
                else:
                    logger.fatal(f"Got an invalid timespec: {timespec}")
                    #we'll delete it anyway so as to not flood the log
                return True
            elif action == "revokerequirement":
                tag = message['tag']
                facility = message['facility']
                revoked = db.query(AccessRequirement).filter(AccessRequirement.tag == tag).filter(
                    AccessRequirement.facility == facility).all()
                if any(revoked):
                    for r in revoked:
                        db.delete(revoked)
                    db.commit()
                    return True
                else:
                    return False
        finally:
            db.close()

