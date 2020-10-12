from icalendar import Calendar
from datetime import datetime, timedelta
import pytz
import recurring_ical_events

def ValidateTimeSpec(timespec:str):
    try:
        cal = Calendar.from_ical(timespec)
        return len(cal.walk('VEVENT')) == 1 #todo: is this necessary? Should we permit multiple events?
    except:
        try:
            times = timespec.split(";")
            start = datetime.fromisoformat(times[0])
            end = datetime.fromisoformat(times[1])
        except:
            pass
    return False

def IsTimeInEvent(timespec : str, now=datetime.now(pytz.utc)):
    if timespec == None or timespec == "" or timespec.lower() == "always":
        return True

    if now.tzinfo == None:
        raise ValueError("Now time must have timezone!")

    try:
        cal = Calendar.from_ical(timespec)
        events = recurring_ical_events.of(cal).at(now)
        return any(events)
    except:
        pass

    times = timespec.split(";")
    start = datetime.fromisoformat(times[0]).replace(tzinfo=pytz.utc)
    end = datetime.fromisoformat(times[1]).replace(tzinfo=pytz.utc)

    return start <= now and end >= now



def NextEvent(timespec: str, now=datetime.now(pytz.utc)):
    if timespec == None or timespec == "" or timespec.lower() == "always":
        return None

    if now.tzinfo == None:
        raise ValueError("Now time must have timezone!")

    try:
        oneyear = now + timedelta(days=366)
        cal = Calendar.from_ical(timespec)
        events = recurring_ical_events.of(cal).between(now,oneyear)
        if any:
            return events[0]['DTSTART'].dt.strftime("%c")
        else:
            return "Never"
    except:
        times = timespec.split(";")
        start = datetime.fromisoformat(times[0]).replace(tzinfo=pytz.utc)

        return start.strftime("%c")




