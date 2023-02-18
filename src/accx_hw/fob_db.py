import logging
import pathlib

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy import Table, Column, Integer, String, Date, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
import typing
from datetime import datetime, date
TcmakerBase = declarative_base()

logger = logging.getLogger("fob_db")

ADMIN = "Admin"
ALWAYS = "Always"
DISABLED = "Disabled"
EXPIRED = "Expired"
DENIED = "Denied" # Means the fob is unrecognized


class __FobDb__(TcmakerBase):
    __tablename__ = 'fobs'

    id = Column(Integer, primary_key=True)
    person = Column(String)
    code = Column(String)
    expiration = Column(Date)
    access_type = Column(Integer)

class FobDatabase():
    def __init__(self, dbfile):
        absfile = str(dbfile) if dbfile is pathlib.Path else dbfile
        self.engine = create_engine(f"sqlite:///{absfile}")
        self.Session = sessionmaker(bind=self.engine)
        # session = Session()
        self.ScopedSession = scoped_session(self.Session)
        TcmakerBase.metadata.create_all(self.engine)

    def is_active(self, code: str) -> (bool, str, datetime): # yes/no, who, their expiration
        db = self.ScopedSession()
        try:
            user : list[__FobDb__] = db.query(__FobDb__).filter(__FobDb__.code == code).all()
            if len(user) == 0:
                return (DENIED, None)
            if len(user) > 1:
                logger.warning(f"Unexpected duplicate users with same fob number: {code}")
            user : __FobDb__ = user[0]
            if user.access_type == 99:
                result = ADMIN
            elif user.access_type == 0:
                result = DISABLED
            else:
                result = ALWAYS if user.expiration >= date.today() else EXPIRED
            return (result, user.person)
        except Exception as e:
            logger.error(f"Unable to test code: {code}, e: {e}")
            return (False, None)
        finally:
            db.close()

    def get(self, code: str) -> __FobDb__: # yes/no, who, their expiration
        db = self.ScopedSession()
        try:
            user : list[__FobDb__] = db.query(__FobDb__).filter(__FobDb__.code == code).all()
            if len(user) == 0:
                return None
            if len(user) > 1:
                logger.warning(f"Unexpected duplicate users with same fob number: {code}")
            user : __FobDb__ = user[0]
            return user
        except Exception as e:
            logger.error(f"Unable to test code: {code}, e: {e}")
            return None
        finally:
            db.close()

    def remove_all(self):
        db = self.ScopedSession()
        try:
            db.query(__FobDb__).delete()
            db.commit()
        except Exception as e:
            logger.error(f"Unable to remove all entries! e: {e}")
            return 0
        finally:
            db.close()

    def remove(self, code):
        db = self.ScopedSession()
        try:
            user: list[__FobDb__] = db.query(__FobDb__).filter(__FobDb__.code == code).all()
            num_to_delete = len(user)
            for u in user:
                db.delete(u)
            db.commit()
            return num_to_delete
        except Exception as e:
            logger.error(f"Unable to remove cod: {code}, e: {e}")
            return 0
        finally:
            db.close()

    def all(self) -> list[__FobDb__]:
        db = self.ScopedSession()
        try:
            users: list[__FobDb__] = db.query(__FobDb__).order_by(__FobDb__.person).all()
            return users
        finally:
            db.close()

    def add(self, code: String, person: String, expiration: date, access_type: int):
        db = self.ScopedSession()
        try:
            user: list[__FobDb__] = db.query(__FobDb__).filter(__FobDb__.code == code).all()
            if len(user) == 0:
                # new entry
                newCode = __FobDb__(person=person, code=code,expiration=expiration, access_type=access_type)
                db.add(newCode)
            elif len(user) > 1:
                logger.warning(f"Unexpected duplicate users with same fob number: {code}")
            for fobuser in user:
                if fobuser.person != person:
                    logger.warning(f"Duplicate fob being written! {code} already exists for {fobuser.person}, new owner is {person}")
                    fobuser.person = person
                fobuser.code = code
                fobuser.expiration = expiration
                fobuser.access_type = access_type
            db.commit()
            return True
        except Exception as e:
            logger.error(f"Unable to add user: {person} w/ {code}, e: {e}")
            return False
        finally:
            db.close()