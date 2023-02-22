import base64
import time
import traceback

from auth.auth_plugin import AuthPlugin
from datetime import date, datetime
from threading import Lock, Thread, Event
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy import Table, Column, Integer, String, Date, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
import logging
import requests

WildApricotBase = declarative_base()

logger = logging.getLogger("wildapricot")

class WildApricotDb(WildApricotBase):
    __tablename__ = 'members'

    id = Column(Integer, primary_key=True)
    person = Column(String)
    person_url = Column(String) # not actually used
    code = Column(String)
    member_enabled = Column(Boolean)
    member_status = Column(String)
    is_banned = Column(Boolean)
    expiration = Column(DateTime)
    last_updated = Column(DateTime)

    def should_grant(self, now_time):
        if not self.member_enabled:
            return (False, self.person, "wildapricot:not_enabled", self.expiration, self.last_updated)
        if self.is_banned:
            return (False, self.person, "wildapricot:banned", self.expiration, self.last_updated)
        if self.member_status != "Active":
            return (False, self.person, "wildapricot:not_active", self.expiration, self.last_updated)
        if self.expiration < now_time:
            return (False, self.person, "wildapricot:expired",self.expiration, self.last_updated)
        return (True, self.person, "wildapricot:granted", self.expiration, self.last_updated)

    @staticmethod
    def from_json(json):
        return WildApricotDb(person=str(json['person']), code=json['fob'], member_enabled=json['enabled'], expiration=json['renewal_due'],
                            member_status=json['status'], is_banned=json['banned'],
                                last_updated=datetime.now())

class WildApricotAuth(AuthPlugin):
    def __init__(self):
        self._mysqlFailure = False
        self.refresh_done_event = Event()
        self.on_demand_auth_event = Event()
        self.on_demand_result = None
    

    def priority(self):
        return 2

    def get_configuration_schema(self) -> (str,dict,bool):
        """

        :return: (plugin name, config schema, config required)
        """
        return ("wildapricot",{
            "type" : "object",
            "additionalProperties": False,
            "properties" : {
                "dbfile": {"type": "string"},
                "api_key": {"type": "string"},
                "refresh": {"type" : "integer"},
                "__line__": {},
            },
            "required" : ["dbfile","api_key"]
        },True)

    def read_configuration(self, config):
        self.DatabaseFile = config['dbfile']
        self.Refresh = config['refresh'] * 60 if 'refresh' in config else 20 * 60
        self.ApiKey = base64.b64encode(f"APIKEY:{config['api_key']}".encode("UTF-8")).decode("ascii")

        self.RequestHeaders = {
            # Generate an API token from the admin panel
            #
            'Authorization': 'Basic %s' % self.ApiKey,
            'Content-type': 'application/x-www-form-urlencoded',
            'User-Agent': 'WildApricotAuth'
        }

    def on_load(self):
        #global logger

        engine = create_engine(f"sqlite:///{self.DatabaseFile}")
        Session = sessionmaker(bind=engine)
        # session = Session()
        self.ScopedSession = scoped_session(Session)
        WildApricotBase.metadata.create_all(engine)
        logger.info("Loaded Wild Apricot Membership Plugin")
        self.LastSQLRefresh = datetime.min
        self.refresh_lock = Lock()

    def refresh_database(self):
        now = datetime.now()
        if (now - self.LastSQLRefresh).total_seconds() >= self.Refresh:
            if not self.refresh_lock.locked():
                self.LastSQLRefresh = now
                #launch the database resync on its own thread because internet timeouts make this take awhile
                self.refresh_done_event.clear()
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
            self.refresh_done_event.set()

    def getFieldValue(self, js, fv, default=None):
        match = [a['Value'] for a in js['FieldValues'] if a['FieldName'] == fv]
        if match:
            return match[0]
        return default

    def get_access_token(self):
        refresh_url = 'https://oauth.wildapricot.org/auth/token/'
        response = requests.post(refresh_url, data={'grant_type': 'client_credentials', 'scope': 'auto'},
                                 headers=self.RequestHeaders)
        response.raise_for_status()
        oauth = response.json()
        access_token = oauth['access_token']
        return access_token

    def list_wa_accounts(self):
        access_token = self.get_access_token()

        responseContacts = requests.get('https://api.wildapricot.org/v2.2/accounts/409807/contacts',
                                        headers={'Accept': 'application/json',
                                                 'Authorization': f'Bearer {access_token}',
                                                 },
                                        params={'$async': 'false',
                                                '$filter': "'Key Fob' ne 'NULL' AND 'Key Fob' ne 0",
                                                '$select': "'Key Fob','Key Fob is','MembershipEnabled','Renewal due','Status'"
                                                }
                                        )
        # Raise an exception on HTTP error
        responseContacts.raise_for_status()
        cc = responseContacts.json()

        for c in cc['Contacts']:
            contact = self.wa_to_contact(c)
            if contact:
                yield contact

    def get_single_contact(self, account_id, account_fob):
        access_token = self.get_access_token()

        responseContacts = requests.get('https://api.wildapricot.org/v2.2/accounts/409807/contacts',
                                        headers={'Accept': 'application/json',
                                                 'Authorization': f'Bearer {access_token}',
                                                 },
                                        params={'$async': 'false',
                                                f'$filter': f"'Key Fob' eq '{account_fob}' and 'User Id' eq '{account_id}'", # Filtering on this to reduce surprised
                                                '$select': "'Key Fob','Key Fob is','MembershipEnabled','Renewal due','Status'"
                                                }
                                        )
        # Raise an exception on HTTP error
        responseContacts.raise_for_status()
        cc = responseContacts.json()
        if cc and 'Contacts' in cc and cc['Contacts']:
            return self.wa_to_contact(cc['Contacts'][0])
        else:
            return None

    def wa_to_contact(self, json):
        try:
            person_id = str(json['Id'])

            fob = self.getFieldValue(json, "Key Fob")
            if fob:
                fob = fob if len(fob.rstrip()) > 0 else "0000000"
            else:  #  if there is no fob, we don't care
                return None
            if "MembershipEnabled" in json:
                enabled = bool(json["MembershipEnabled"])
            else:
                enabled = False
            banned = self.getFieldValue(json, "is_banned", False)

            fob_value = f"f:{int(fob)}"
        except:
            return None
        try:
            rd = str(self.getFieldValue(json,"Renewal due"))
            renewal = datetime.fromisoformat(rd)
        except:
            renewal = datetime.min



        contact = {
            "person": person_id,
            #"person_url": json['Url'],
            'fob': fob_value,
            'enabled': enabled,
            "status": json['Status'] if 'Status' in json else 'Lapsed',
            "renewal_due": renewal,
            "banned" : banned,
        }
        return contact

    def attempt_on_demand_auth(self, account, fob, now):
        try:
            contact = self.get_single_contact(account, fob)
            if contact:
                self.on_demand_result = WildApricotDb.from_json(contact).should_grant(now)
            else:
                self.on_demand_result = None
        finally:
            self.on_demand_auth_event.set()

    def refresh_membership(self):
        logger.debug("Refreshing Wild Apricot Membership db")

        #fobs = list(self.list_keyfobs(self.Url))
        #print(f"fobs: {len(fobs)}")

        db = self.ScopedSession()
        num_deleted = 0
        num_modified = 0
        num_added = 0
        # this could all be done a lot more efficiently, but future me can deal with that
        m: WildApricotDb
        members: dict = {(m.person, m.code): m for m in db.query(WildApricotDb).order_by(WildApricotDb.person).all() }
        #members: list[TcmakerMembershipDb] =
        current_fob = "None"
        try:
            for contact in self.list_wa_accounts():
                person_id = contact['person']
                code = contact['fob']
                #person_url = contact['url']
                enabled = contact['enabled']
                status = contact['status']
                banned = contact['banned']
                expiration = contact['renewal_due']

                idpair = (person_id, code)
                if idpair in members:
                    mem: WildApricotDb = members[idpair]
                    members.pop(idpair)
                    #see if we should update this one
                    if mem.member_enabled != enabled or mem.code != code or mem.expiration != expiration or\
                            mem.member_status != status or mem.is_banned != banned:
                        mem.member_enabled = enabled
                        mem.is_banned = banned
                        mem.code = code
                        mem.expiration = expiration
                        mem.member_status = status
                        num_modified += 1
                        mem.last_updated = datetime.now()
                else: #they're new!
                    newMember = WildApricotDb.from_json(contact)
                    db.add(newMember)
                    num_added += 1
            for m in members.values():
                current_fob = m
                db.delete(m)
                num_deleted += 1
                pass
            db.commit()
        except Exception as e:
            logger.error(f"Unable to refresh wildapricot database: {e}, failed on {current_fob}. {traceback.format_exc()}")
        finally:
            db.close()
            logger.debug(f"Added {num_added}, modified {num_modified}, deleted {num_deleted}")

    # denial types
    # Fob Not Recognized
    # Membership Not Enabled
    # Membership Lapsed (according to WA)
    # Membership Expired (according to me)

    #:rtype: (bool: grant or not, str: the member id, str: the authorization type)
    def on_scan(self, credential_type, credential_value, scanner, facility, now_time) -> (bool, str, str, datetime, datetime):
        if credential_type != "fob": #maybe
            return (False, None, "wildapricot:unknown_fob", None, None)

        credential_string = f"f:{int(credential_value)}"
        db = self.ScopedSession()
        try:
            user : list[WildApricotDb] = db.query(WildApricotDb).filter(WildApricotDb.code == credential_string).all()
            if len(user) == 0:
                return (False, None, "wildapricot:unknown_fob", None, None)
            if len(user) > 1:
                logger.warning(f"Unexpected duplicate users with same fob number: {credential_string}")
            user : WildApricotDb = user[0]
            first_pass = user.should_grant(now_time)
            if first_pass[0]:
                return first_pass
            # Attempt on-demand
            Thread(target=self.attempt_on_demand_auth,args=(user.person,int(credential_value),now_time)).start()
            if self.on_demand_auth_event.wait(2000):
                second_pass = self.on_demand_result
                if second_pass and second_pass[1] == user.person:
                    #  If the on-demand was successful, we're not going to actually store it in the DB, we'll
                    #  let the refresh deal with that
                    return second_pass
            return first_pass
        except Exception as e:
            logger.error(f"Unable to test fob: {credential_value}, e: {e}")
        finally:
            db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    from os import environ
    auth = WildApricotAuth()
    if not environ.get("WA_KEY",False):
        print("You need to set the WA Key!")
        exit(1)

    auth.read_configuration({"dbfile": "testwildapricot.db",
                             "url":"https://members.tcmaker.org/api/v1/keyfobs/",
                             "api_key": environ.get("WA_KEY")})
    auth.on_load()
    now = datetime.now()
    auth.refresh_database()
    auth.refresh_done_event.wait(60000)
    print(auth.on_scan("fob", "11123412", "frontdoor", "building", now))

