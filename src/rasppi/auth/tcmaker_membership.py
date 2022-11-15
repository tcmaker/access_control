from auth.auth_plugin import AuthPlugin
from datetime import date, datetime
from threading import Lock, Thread
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy import Table, Column, Integer, String, Date, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
import logging
import requests
from aws_wrapper import read_queue as read_aws_queue
TcmakerBase = declarative_base()

logger = logging.getLogger("tcmaker_membership")

class TcmakerMembershipDb(TcmakerBase):
    __tablename__ = 'members'

    id = Column(Integer, primary_key=True)
    person = Column(String)
    code = Column(String)
    member_active = Column(Boolean)
    expiration = Column(Date)
    fobuuid = Column(String)

class TcmakerMemberRest():
    def __init__(self, person, fob_code, expiration_date, is_active):
        self.person = person
        self.fob_code = fob_code
        self.expiration_date = expiration_date
        self.is_active = is_active

class TcmakerMembership(AuthPlugin):
    def __init__(self):
        self._mysqlFailure = False
    
    def get_configuration_schema(self) -> (str,dict,bool):
        """

        :return: (plugin name, config schema, config required)
        """
        return ("tcmaker",{
            "type" : "object",
            "additionalProperties": False,
            "properties" : {
                "dbfile": {"type": "string"},
                "url" : {"type" : "string"},
                "api_key": {"type": "string"},
                "refresh": {"type" : "integer"},
                "__line__": {},
            },
            "required" : ["dbfile","url","api_key"]
        },True)

    def read_configuration(self, config):
        self.DatabaseFile = config['dbfile']
        self.Refresh = config['refresh'] * 60 if 'refresh' in config else 20 * 60
        self.Url = config['url']
        self.ApiKey = config['api_key']

        self.RequestHeaders = {
            # Generate an API token from the admin panel
            #
            'Authorization': 'Bearer %s' % self.ApiKey
        }

    def on_load(self):
        #global logger

        engine = create_engine(f"sqlite:///{self.DatabaseFile}")
        Session = sessionmaker(bind=engine)
        # session = Session()
        self.ScopedSession = scoped_session(Session)
        TcmakerBase.metadata.create_all(engine)
        logger.info("Loaded TCMaker Membership Plugin")
        self.LastSQLRefresh = datetime.min
        self.refresh_lock = Lock()

    def refresh_database(self):
        now = datetime.now()
        if (now - self.LastSQLRefresh).total_seconds() >= self.Refresh:
            if not self.refresh_lock.locked():
                self.LastSQLRefresh = now
                #launch the database resync on its own thread because internet timeouts make this take awhile
                t = Thread(target=self.do_database_refresh)
                t.start()

    def do_database_refresh(self):
        try:
            self.refresh_lock.acquire(True,timeout=30) #todo: this could be a problem, needs better sync
            self.refresh_membership()
            self._mysqlFailure = False
        except Exception as e:
            if not self._mysqlFailure:
                logger.error(f"Unable to refresh membership database: {e}")
                self._mysqlFailure = True
        finally:
            self.refresh_lock.release()

    def list_keyfobs(self, start_url):
        url = start_url
        while url is not None:
            # Fetch the first page
            response = requests.get(url, headers=self.RequestHeaders)
            # Raise an exception on HTTP error
            response.raise_for_status()
            # Parse the JSON in the response into Python data structures
            body = response.json()
            # Update the loop for the next page
            url = body['next']
            # Loop over this page of results
            for result in body['results']:
                yield result

    def refresh_membership(self):
        logger.debug("Refreshing membership db")

        #fobs = list(self.list_keyfobs(self.Url))
        #print(f"fobs: {len(fobs)}")

        db = self.ScopedSession()
        num_deleted = 0
        num_modified = 0
        num_added = 0
        # this could all be done a lot more efficiently, but future me can deal with that
        m: TcmakerMembershipDb
        members: dict = {(m.person, m.fobuuid): m for m in db.query(TcmakerMembershipDb).order_by(TcmakerMembershipDb.person).all() }
        #members: list[TcmakerMembershipDb] =
        current_fob = "None"
        try:
            for f in self.list_keyfobs(self.Url):
                current_fob = f
                personuuid = f['person'].split('/')[-2]
                fobuuid = f['url'].split('/')[-2]
                is_valid = bool(f['is_active'])
                try:
                    code = f"f:{int(f['code'])}"
                except:
                    code = "0000000"
                mvt = f['membership_valid_through']
                expiration = datetime.fromisoformat(str(mvt)) if type(mvt) == str else datetime.min
                #member_fobs[personuuid] = TcmakerMemberRest(personuuid,code,expiration,is_valid)
                idpair = (personuuid, fobuuid)
                if idpair in members:
                    mem: TcmakerMembershipDb = members[idpair]
                    members.pop(idpair)
                    #see if we should update this one
                    if mem.member_active != is_valid or mem.code != code or mem.expiration != expiration:
                        mem.member_active = is_valid
                        mem.code = code
                        mem.expiration = expiration
                        num_modified += 1
                else: #they're new!
                    newMember = TcmakerMembershipDb(person=personuuid,code=code,member_active=is_valid,expiration=expiration, fobuuid=fobuuid)
                    db.add(newMember)
                    num_added += 1
            for m in members.values():
                current_fob = m
                db.delete(m)
                num_deleted += 1
                pass
            db.commit()

        except Exception as e:
            logger.error(f"Unable to refresh tcmaker database: {e}, failed on {current_fob}")
        finally:
            db.close()
            logger.debug(f"Added {num_added}, modified {num_modified}, deleted {num_deleted}")

    #:rtype: (bool: grant or not, str: the member id, str: the authorization type)
    def on_scan(self, credential_type, credential_value, scanner, facility) -> (bool, str, str):
        if credential_type != "fob": #maybe
            return (False, None, None)

        credential_string = f"f:{credential_value}"
        db = self.ScopedSession()
        try:
            user : list[TcmakerMembershipDb] = db.query(TcmakerMembershipDb).filter(TcmakerMembershipDb.code == credential_string).all()
            if len(user) == 0:
                return (False, None, None)
            if len(user) > 1:
                logger.warning(f"Unexpected duplicate users with same fob number: {credential_string}")
            user : TcmakerMembershipDb = user[0]
            return (user.member_active,user.person,"tcmembership")
        except Exception as e:
            logger.error(f"Unable to test fob: {credential_value}, e: {e}")
        finally:
            db.close()

if __name__ == "__main__":
    auth = TcmakerMembership()
    auth.read_configuration({"dbfile": "testtcmembership.db",
                             "url":"https://members.tcmaker.org/api/v1/keyfobs/",
                             "api_key": "blah"})
    auth.on_load()
    auth.refresh_database()

    auth.on_scan("fob","0010671635","frontdoor","building")
