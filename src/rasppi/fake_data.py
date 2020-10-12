from configuration import Config
from models import Credential, Activity, AccessRequirement
from random import randint, sample
from uuid import uuid4
from datetime import datetime, timedelta
from pytz import utc

def randomId(size=6):
    return "".join([str(randint(0,9)) for a in range(size)])

numUsers = 35
maxCredentialsPerUser=8
now = datetime.now(utc)

session = Config.ScopedSession()

def makeUsers(numUsers, maxCredentialsPerUser, priority):
    Users = {}
    for u in range(numUsers):
        memberId = memberid=randomId(4)
        Users[memberId] = []
        for un in range(1): #range(randint(0,maxCredentialsPerUser)):
            start = now - timedelta(days=randint(0,12))
            end = now + timedelta(days=randint(0, 36))
            c = Credential(facility="frontdoor",memberid=memberId,
                           credential=randomId(9),type="fob",effective=start,expiration=end,tag=str(uuid4()),priority=priority
                           )
            session.add(c)
            Users[memberId].append(c)

    session.commit()
    return Users

members = makeUsers(35,8,4)

cfob = Credential(facility="frontdoor",memberid="3870",
                           credential="16294934",type="fob",effective=now - timedelta(days=5),expiration=now + timedelta(days=360),tag=str(uuid4()),priority=4
                           )
ccode = Credential(facility="frontdoor",memberid="1337",
                           credential="4455661",type="passcode",effective=now - timedelta(days=5),expiration=now + timedelta(days=360),tag=str(uuid4()),priority=4
                           )
session.add(cfob)
session.add(ccode)
session.commit()

subjects = ['Welding',"Lathe","CNC","Laser","Electronics","Blacksmith","Sheet metal"]
events = ['Class',"Class","Workshop","Workshop","Group","Session"]

arNormal = AccessRequirement(requiredpriority=1,facility="frontdoor",tag=str(uuid4()),description="Door Normally Locked",timespec="always")
arcovid = AccessRequirement(requiredpriority=2,facility="frontdoor",tag=str(uuid4()),description="Covid Restrictions",timespec="always")

arexclusive = AccessRequirement(requiredpriority=5,facility="frontdoor",tag=str(uuid4()),description="Exclusive Event",timespec="""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//ical.marudot.com//iCal Event Maker
CALSCALE:GREGORIAN
BEGIN:VTIMEZONE
TZID:America/Chicago
TZURL:http://tzurl.org/zoneinfo-outlook/America/Chicago
X-LIC-LOCATION:America/Chicago
BEGIN:DAYLIGHT
TZOFFSETFROM:-0600
TZOFFSETTO:-0500
TZNAME:CDT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0500
TZOFFSETTO:-0600
TZNAME:CST
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
DTSTAMP:20201008T024427Z
UID:20201008T024427Z-1868816693@marudot.com
DTSTART;TZID=America/Chicago:20201012T120000
RRULE:FREQ=MONTHLY;BYDAY=2MO
DTEND;TZID=America/Chicago:20201012T150000
SUMMARY:Exclusive Event
END:VEVENT
END:VCALENDAR""")

session.add(arNormal)
session.add(arexclusive)
session.add(arcovid)
#for c in range(randint(3,14)):
#    thetime = 8+randint(0,11)
#    start = datetime(now.year, now.month, now.day, thetime,0,0)+timedelta(days=randint(-2,20))
#    end = start + timedelta(minutes=120)
#    description = f'{sample(subjects, 1)[0]} {sample(events, 1)[0]}'
#    event = AccessRequirement(requiredpriority=2,facility="frontdoor",tag=str(uuid4()),description=description,
#                              timespec=f"{start.isoformat()};{end.isoformat()}")
#    session.add(event)


#eventnow = AccessRequirement(requiredpriority=2,facility="frontdoor",tag=str(uuid4()),description="Awesome Demonstration",
#                              timespec=f"{(now - timedelta(minutes=30)).isoformat()};{(now + timedelta(minutes=60)).isoformat()}")
#session.add(eventnow)
session.commit()
