from threading import Thread, Lock
from typing import Iterable

from auth.auth_plugin import AuthPlugin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, Session
#from models import Base
from aws_wrapper import read_queue, write_queue

from sqlalchemy import Table, Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from pytz import utc
from icalwrapper import IsTimeInEvent, NextEvent, ValidateTimeSpec
ClubhouseBase = declarative_base()
import logging

logger = logging.getLogger("clubhouse")

class Credential(ClubhouseBase):
    KEYFOB = 'fob'
    PASSCODE = 'passcode'

    __tablename__ = 'credentials'

    id = Column(Integer, primary_key=True)
    facility = Column(String, nullable=False)
    memberid = Column(String, nullable=False)
    credential = Column(String, nullable=False)
    type = Column(String, nullable=False)
    effective = Column(DateTime, nullable=False)
    expiration = Column(DateTime, nullable=False)
    tag = Column(String, nullable=False)
    priority = Column(Integer)

    def __repr__(self):
        return f"<Credential(facility={self.facility},member={self.memberid},cred={self.credential}, priority={self.priority})>"

class AccessRequirement(ClubhouseBase):
    __tablename__ = 'requirements'

    id = Column(Integer, primary_key=True)
    requiredpriority = Column(Integer, nullable=False)
    facility = Column(String, nullable=False)
    tag = Column(String, nullable=False)
    timespec = Column(String, nullable=False)
    description = Column(String)



    ## TODO: Upgrade the DB schema to have convenience methods for next event,
    ##  for efficiency in display. Also cull old events

    #nextEffective = Column(DateTime)
    #nextEndEffective = Column(DateTime)
    #ultimateExpiration = Column(DateTime)

    def is_active(self, datetime=datetime.now(utc)):
        return IsTimeInEvent(self.timespec, datetime)

    def always_active(self):
        return self.timespec == None or self.timespec == ""

    def next_active(self):
        return NextEvent(self.timespec)

    def validate(self):
        if self.timespec == None or self.timespec == "" or self.timespec == "always":
            return True
        #TODO: Support simple events?
        return ValidateTimeSpec(self.timespec)

    def __repr__(self):
        return f"<Requirement(facility={self.facility},active={self.is_active()},next_active={self.next_active()}, priority={self.requiredpriority})>"

class ClubhouseAuthentication(AuthPlugin):
    def __init__(self):
        self.DatabaseFile = ""
        self.ScopedSession = None

    def get_configuration_schema(self) -> (str,dict,bool):
        return ("clubhouse",

                       {"type": "object",
                 "additionalProperties": False,
                 "properties": {
                     "database": {"type": "string"},
                     "key_id": {"type": "string"},
                     "access_key": {"type": "string"},
                     "region": {"type": "string"},
                     "incoming": {"type": "string"},
                     "outgoing": {"type": "string"},
                     "use_system_credentials": {"const": False},
                     "__line__": {},
                 },
                 "required": ['database','key_id', 'access_key', 'region', 'incoming', 'outgoing']}
            , True)

    def read_configuration(self, config):
        self.DatabaseFile = config['database']
        if 'use_system_credentials' not in config:
            config['use_system_credentials'] = False
        pass

    def on_load(self):
        engine = create_engine(f"sqlite:///{self.DatabaseFile}")
        Session = sessionmaker(bind=engine)
        #session = Session()
        self.ScopedSession = scoped_session(Session)
        ClubhouseBase.metadata.create_all(engine)
        self.awslock = Lock()
        self._awsFailure = False

    def refresh_database(self):
        return
        daud = Thread(target=self._do_aws_upload_download)
        daud.start()

    def on_scan(self, credential_type, credential_value, scanner, facility) -> (bool, str, str):
        db: Session = self.ScopedSession()
        try:
            # OK, we've determined the facility that was scanned for
            credential: Credential = db.query(Credential).filter(Credential.credential == credential_value) \
                .filter(Credential.type == (Credential.KEYFOB if credential_type == 'fob' else Credential.PASSCODE)) \
                .filter(Credential.facility == facility.name) \
                .order_by(Credential.priority.desc()).first()
            if credential is not None:
                # TODO Bring back scanning out
                # if facility.outscanner == scanner:
                #     activity = Activity(memberid=credential.memberid, authorization="none",
                #                         result="exit",
                #                         timestamp=datetime.now(),
                #                         facility=facility.name,
                #                         credentialref=credential_value,
                #                         notified=False)
                #     self.lock(facility.board, facility.relay, credential_value)
                #     db.add(activity)
                #     db.commit()
                #     return

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
                    return (grant, credential.memberid, credential.tag)
            else:  # scan of a non-existent user
                if scanner == facility.outscanner:
                    logger.error("Exit scan of a non-existent user!")
                return (False, None, None)
        finally:
            db.close()


    def _do_aws_upload_download(self):
        self.awslock.acquire()
        db: Session = self.ScopedSession()
        try:
            # get any new messages
            try:
                read_queue(callback=self.process_incoming_message)
                self._awsFailure = False
            except Exception as e:
                if not self._awsFailure:
                    logger.fatal(f"AWS Communication problem: {e}")
                self._awsFailure = True

            # upload any new messages
            #TODO: move this out of the clubhouse into the main system
            # messages = db.query(Activity).filter(not Activity.notified).limit(20).all()
            #
            # def awsmap(a: Activity):
            #     return (a, {"action": "activity",
            #                 "result": a.result,
            #                 "facility": a.facility,
            #                 "memberid": a.memberid,
            #                 "authorization": a.memberid,
            #                 "credentialref": a.credentialref,
            #                 "timestamp": a.timestamp.isoformat()})
            #
            # if len(messages) > 0:
            #     try:
            #         (written, failed) = write_queue(map(awsmap, messages))
            #         w: Activity
            #         for w in written:
            #             w.notified = True
            #         db.commit()
            #         self._awsFailure = False
            #     except Exception as e:
            #         if not self._awsFailure:
            #             logger.fatal(f"AWS Communication problem: {e}")
            #         self._awsFailure = True
        finally:
            self.awslock.release()
            db.close()

    @staticmethod
    def process_incoming_message(message):
        if "action" not in message:
            raise Exception("Invalid message!")
        action = message['action']
        db: Session = Config.ScopedSession()
        try:
            if action == "activate":
                facility_name = message['facility']
                if facility_name not in Config.getFacilities():
                    return False
                credential = message['code']
                credtype = message['codetype']
                memberid = str(message['member'])
                if (nonmatch := db.query(Credential).filter(Credential.credential == credential).filter(
                        Credential.type == credtype).filter(Credential.memberid != memberid).first()) is not None:
                    # if nonmatch is not None:
                    raise Exception(
                        f"Got a duplicate credential with non-matching memberid. {nonmatch.credential} : {nonmatch.memberid}")

                cred = Credential(facility=facility_name,
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
                revoked = db.query(Credential).filter(Credential.tag == tag).filter(
                    Credential.facility == facility).first()
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
                credentials = db.query(Credential).filter(Credential.memberid == member).filter(
                    Credential.type == oldtype).filter(Credential.credential == oldcode).filter(
                    Credential.facility == facility).all()
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
                ar = AccessRequirement(requiredpriority=required, facility=facility, tag=tag, timespec=timespec,
                                       description=description)
                if ar.validate():
                    db.add(ar)
                    db.commit()
                else:
                    logger.fatal(f"Got an invalid timespec: {timespec}")
                    # we'll delete it anyway so as to not flood the log
                return True
            elif action == "revokerequirement":
                tag = message['tag']
                facility = message['facility']
                revoked = db.query(AccessRequirement).filter(AccessRequirement.tag == tag).filter(
                    AccessRequirement.facility == facility).all()
                if any(revoked):
                    for r in revoked:
                        db.delete(r)
                    db.commit()
                    return True
                else:
                    return False
        finally:
            db.close()