import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy import Table, Column, Integer, String, Date, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
import typing
from datetime import datetime, date
TcmakerBase = declarative_base()

logger = logging.getLogger("fob_db")

class FobDb(TcmakerBase):
    __tablename__ = 'fobs'

    id = Column(Integer, primary_key=True)
    person = Column(String)
    code = Column(String)
    expiration = Column(Date)

class FobDatabase():
    def __init__(self, dbfile):
        self.engine = create_engine(f"sqlite:///{dbfile}")
        self.Session = sessionmaker(bind=self.engine)
        # session = Session()
        self.ScopedSession = scoped_session(self.Session)
        TcmakerBase.metadata.create_all(self.engine)

    def is_active(self, code: String) -> (bool, String, datetime): # yes/no, who, their expiration
        db = self.ScopedSession()
        try:
            user : list[FobDb] = db.query(FobDb).filter(FobDb.code == code).all()
            if len(user) == 0:
                return (False, None, None)
            if len(user) > 1:
                logger.warning(f"Unexpected duplicate users with same fob number: {code}")
            user : FobDb = user[0]
            active = user.expiration >= date.today()
            return (active,user.person,user.expiration)
        except Exception as e:
            logger.error(f"Unable to test code: {code}, e: {e}")
            return (False, None, None)
        finally:
            db.close()

    def remove_all(self):
        db = self.ScopedSession()
        try:
            db.query(FobDb).delete()
            db.commit()
        except Exception as e:
            logger.error(f"Unable to remove all entries! e: {e}")
            return 0
        finally:
            db.close()

    def remove(self, code):
        db = self.ScopedSession()
        try:
            user: list[FobDb] = db.query(FobDb).filter(FobDb.code == code).all()
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

    def add(self, code: String, person: String, expiration: date):
        db = self.ScopedSession()
        try:
            user: list[FobDb] = db.query(FobDb).filter(FobDb.code == code).all()
            if len(user) == 0:
                # new entry
                newCode = FobDb(person=person, code=code,expiration=expiration)
                db.add(newCode)
            elif len(user) > 1:
                logger.warning(f"Unexpected duplicate users with same fob number: {code}")
            for fobuser in user:
                fobuser = user[0]
                if fobuser.person != person:
                    logger.warning(f"Duplicate fob being written! {code} already exists for {fobuser.person}, new owner is {person}")
                    fobuser.person = person
                fobuser.code = code
                fobuser.expiration = expiration
            db.commit()
            return True
        except Exception as e:
            logger.error(f"Unable to add user: {person} w/ {code}, e: {e}")
            return False
        finally:
            db.close()

if __name__ == "__main__":
    db = FobDatabase("test.db")
    db.add("F:15598498","person",datetime.max)
    db.add("F:15598497","other_person",datetime.min)
    print(f"{db.is_active('f:15598498')} should be true")
    print(f"{db.is_active('f:15598497')} should be false")
    print(f"{db.is_active('f:15698498')} should be false")
    #db.remove("f:0015598498")
    #print(f"{db.is_active('f:0015598498')} should be false")
