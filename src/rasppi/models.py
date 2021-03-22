from sqlalchemy import Table, Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
from pytz import utc
from icalwrapper import IsTimeInEvent, NextEvent, ValidateTimeSpec

DoorControllerBase = declarative_base()

class Activity(DoorControllerBase):
    __tablename__  = 'activity'

    id = Column(Integer, primary_key=True)
    facility = Column(String, nullable=False)
    memberid = Column(String)
    authorization = Column(String)
    credentialref = Column(String) #convenience
    timestamp = Column(DateTime, nullable=False)
    result = Column(String, nullable=False)
    notified = Column(Boolean, nullable=False)
