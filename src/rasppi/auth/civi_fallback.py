from auth.auth_plugin import AuthPlugin
import mariadb
from datetime import date, datetime
from threading import Lock, Thread
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy import Table, Column, Integer, String, Date, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
import logging
from aws_wrapper import read_queue as read_aws_queue
CiviBase = declarative_base()

logger = logging.getLogger("civi_fallback")

class CiviBridge(CiviBase):
    __tablename__ = 'civibridge'

    id = Column(Integer, primary_key=True)
    contact_id = Column(Integer)
    fob = Column(String)
    expiration = Column(Date)
    member_active = Column(Boolean)
    timeslot_active = Column(Boolean)

class CiviMember():
    def __init__(self, contact_id, status_id, fob_code, expiration_date, is_active):
        self.contact_id = contact_id
        self.status_id = status_id
        self.fob_code = fob_code
        self.expiration_date = expiration_date
        self.is_active = is_active

class CiviFallback(AuthPlugin):
    def get_configuration_schema(self) -> (str,dict,bool):
        """

        :return: (plugin name, config schema, config required)
        """
        return ("civi_fallback",{
            "type" : "object",
            "additionalProperties": False,
            "properties" : {
                "dbfile": {"type": "string"},
                "host" : {"type" : "string"},
                "user": {"type": "string"},
                "pass": {"type": "string"},
                "database": {"type": "string"},
                "refresh": {"type" : "integer"},
                "enforce_timeslots": {"type": "boolean"},
                "aws" : {"type": "object",
                 "additionalProperties": False,
                 "properties": {
                     "database": {"type": "string"},
                     "key_id": {"type": "string"},
                     "access_key": {"type": "string"},
                     "region": {"type": "string"},
                     "queue": {"type": "string"},
                     "__line__": {},
                 }},
                "__line__": {},
            },
            "required" : ["dbfile","host","user","pass","database","aws"]
        },True)

    def read_configuration(self, config):
        self.DatabaseFile = config['dbfile']
        self.Refresh = config['refresh'] * 60
        self.Host = config['host']
        self.User = config['user']
        self.Pass = config['pass']
        self.Database = config['database']
        self.EnforceTimeslots = config['enforce_timeslots'] if 'enforce_timeslots' in config else False
        aws = config['aws']
        self.AwsKeyId = aws['key_id']
        self.AwsAccessKey = aws['access_key']
        self.AwsQueue = aws['queue']
        self.AwsRegion = aws['region']



    def on_load(self):
        #global logger

        engine = create_engine(f"sqlite:///{self.DatabaseFile}")
        Session = sessionmaker(bind=engine)
        # session = Session()
        self.ScopedSession = scoped_session(Session)
        CiviBase.metadata.create_all(engine)
        logger.info("Loaded Civi Fallback Plugin")
        self.LastSQLRefresh = datetime.min
        self.awslock = Lock()
        self._awsFailure = False
        self._mysqlFailure = False
        self.refresh_lock = Lock()


    def refresh_database(self):
        now = datetime.now()
        if (now - self.LastSQLRefresh).total_seconds() >= self.Refresh:
            if not self.refresh_lock.locked():
                self.LastSQLRefresh = now
                #launch the database resync on its own thread because internet timeouts make this take awhile
                t = Thread(target=self.do_database_refresh)
                t.start()

        #do our AWS checks every time
        #self.refresh_aws() #or don't, because we aren't actually using it

    def do_database_refresh(self):
        try:
            self.refresh_lock.acquire(True,timeout=3)
            self.refresh_civisql()
            self._mysqlFailure = False
        except Exception as e:
            if not self._mysqlFailure:
                logger.error("Unable to refresh civi database!")
                self._mysqlFailure = True
        finally:
            self.refresh_lock.release()

    def refresh_civisql(self):
        logger.debug("Refreshing civi db")
        query = "select civicrm_membership.contact_id,civicrm_membership.status_id,civicrm_keyfob.code,civicrm_membership.end_date from civicrm_keyfob join civicrm_membership on civicrm_keyfob.contact_id=civicrm_membership.contact_id order by civicrm_membership.contact_id"
        conn = mariadb.connect(user=self.User, password=self.Pass,
                               host=self.Host, database=self.Database,
                               connect_timeout=5)
        cur = conn.cursor()
        cur.execute(query)
        members = {}
        member_details = ()
        memberId = None
        now = date.today()
        for contact_id, status_id, fob, end_date in cur:
            try:
                sid = int(status_id)
                fob = str(int(fob)) #eliminate leading zeros
                is_active = True if sid <= 2 else \
                    False if end_date == None \
                            else sid == 3 and (now - end_date).days < 31
                cid = int(contact_id)
                #if cid == 3870:
                #    print("It's me!")
                if cid == memberId:
                    # we've got a duplicate, take the highest priority level

                    if sid < member_details.status_id:
                        member_details = CiviMember(cid,sid,fob,end_date,is_active)
                else:
                    # new entry
                    # push the last read row to the dict
                    if memberId is not None:
                        members[memberId] = member_details

                    memberId = cid
                    member_details = CiviMember(cid,sid,fob,end_date,is_active)
            except Exception as sqle:
                logger.warning(f"Failed to import {contact_id}, sid: {status_id}, fob: {fob}, ed:{end_date}: {sqle}")

        if memberId is not None:
            members[memberId] = member_details

        db = self.ScopedSession()
        # print(f'Member: {m[0]}, status: {m[1][0]}, fob: {m[1][1]}')
        try:
            num_deleted = 0
            num_modified = 0
            #this could all be done a lot more efficiently, but future me can deal with that
            bridge_members : list[CiviBridge] = db.query(CiviBridge).order_by(CiviBridge.contact_id).all()
            for bm in bridge_members:
                if bm.contact_id in members:
                    # update the item
                    civi_member = members[bm.contact_id]
                    if (bm.member_active != civi_member.is_active) or (bm.fob != civi_member.fob_code):
                        bm.member_active = civi_member.is_active
                        bm.fob = civi_member.fob_code
                        num_modified += 1
                    members.pop(bm.contact_id)
                else:
                    #we have a bridge member that has been deleted from civi. Delete it I guess
                    db.delete(bm)
                    num_deleted += 1
            db.commit()
            logger.debug(f"Modified {num_modified} bridge entries, deleted {num_deleted}")
            #add new entries for any remaining
            v: CiviMember
            for (k,v) in members.items():
                try:
                    cb = CiviBridge(contact_id = v.contact_id,fob=f"{str(int(v.fob_code))}",expiration=v.expiration_date,member_active=v.is_active,
                                timeslot_active=False)
                    db.add(cb)
                except: 
                    logger.warning(f"bad fob value {v.fob_code} for user {v.contact_id}")
            db.commit()
            logger.debug(f"Added {len(members)} new civi db entries")
        except Exception as e:
            logger.error(f"Unable to refresh civi database: {e}")
        finally:
            db.close()

    def refresh_aws(self):
        self.awslock.acquire()
        db: Session = self.ScopedSession()
        try:
            # get any new messages
            try:
                awscredentials = {
                    'key_id' : self.AwsKeyId,
                    'access_key':self.AwsAccessKey,
                    'incoming' : self.AwsQueue,
                    'region' : self.AwsRegion
                }
                read_aws_queue(awscredentials,callback=self.process_incoming_message)
                self._awsFailure = False
            except Exception as e:
                if not self._awsFailure:
                    logger.fatal(f"AWS Communication problem: {e}")
                self._awsFailure = True
        finally:
            self.awslock.release()
            db.close()

    def process_incoming_message(self, message):
        logger.info(f"Got a message: {message}")
        code = message['keybob_code']
        member = message['member_identifier']
        action = message['action']
        db: Session = self.ScopedSession()
        try:
            user = db.query(CiviBridge).filter(CiviBridge.fob == code).all()
            if len(user) > 1:
                logger.warning("Unexpected multiple users with same fob!")
            if len(user) == 0:
                logger.warning("Got fob unlock code for unknown user!")
            if len(user) == 1:
                user : CiviBridge = user[0]
                user.timeslot_active = action == "enable"
                db.commit()
        finally:
            db.close()
        return False

    #:rtype: (bool: grant or not, str: the member id, str: the authorization guid)
    def on_scan(self, credential_type, credential_value, scanner, facility) -> (bool, str, str):
        if credential_type != "fob":
            return (False, None, None)

        db = self.ScopedSession()
        try:
            bridge_user : list[CiviBridge] = db.query(CiviBridge).filter(CiviBridge.fob == credential_value).all()
            if len(bridge_user) == 0:
                return (False, None, None)
            if len(bridge_user) > 1:
                logger.warning(f"Unexpected duplicate users with same fob number: {credential_value}")
            bridge_user : CiviBridge = bridge_user[0]
            if self.EnforceTimeslots:
                return (bridge_user.member_active and bridge_user.timeslot_active, bridge_user.contact_id,"cividb")
            else:
                return (bridge_user.member_active, bridge_user.contact_id,"cividb-notimeslot" if not bridge_user.timeslot_active else "cividb")
        except Exception as e:
            logger.error(f"Unable to test fob: {credential_value}, e: {e}")
        finally:
            db.close()

