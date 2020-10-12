from sqlalchemy import Table, Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
from pytz import utc
from icalwrapper import IsTimeInEvent, NextEvent, ValidateTimeSpec

Base = declarative_base()

class Credential(Base):
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

class AccessRequirement(Base):
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

class Activity(Base):
    __tablename__  = 'activity'

    id = Column(Integer, primary_key=True)
    facility = Column(String, nullable=False)
    memberid = Column(String)
    authorization = Column(String)
    credentialref = Column(String) #convenience
    timestamp = Column(DateTime, nullable=False)
    result = Column(String, nullable=False)
    notified = Column(Boolean, nullable=False)

# class Board(Base): # a Hardware device
#     __tablename__ = 'boards'
#
#     id = Column(Integer, primary_key=True)
#     resource = Column(String)
#     friendlyname = Column(String)
#     numrelays = Column(Integer)
#     numscanners = Column(Integer)
#     location = Column(String)
#     scanners = relationship("Scanner", lazy='joined')
#     facilities = relationship("Facility", lazy='joined')
#
#     def HtmlName(self):
#         return self.friendlyname if self.friendlyname else self.resource
#
#     def __repr__(self):
#         return f"<Board: {self.resource}, {self.friendlyname}@{self.location}>"
#
# # Since board relays are always on the board, I think I won't have a relay
# # model.
#
# class Scanner(Base): #A scanner on a board
#     __tablename__ = 'scanners'
#
#     id = Column(Integer, primary_key=True)
#     board_id = Column(Integer, ForeignKey("boards.id")) #This is the board the SCANNER is on
#     index = Column(Integer)
#     friendlyname = Column(String)
#     location = Column(String)
#     facility = relationship("Facility", lazy='joined')
#
#     board = relationship("Board", backref="boards")
#
#     def HtmlName(self):
#         return self.friendlyname if self.friendlyname else f"{self.board.HtmlName()}:{self.index}"
#
#     def __repr__(self):
#         return f"<Scanner: {self.board_id}:{self.index}, {self.friendlyname}@{self.location}>"
#

