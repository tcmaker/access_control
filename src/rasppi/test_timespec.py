import unittest
from models import AccessRequirement
from datetime import datetime

class TestTimespecs(unittest.TestCase):


    def runTest(self):
        for tc in self.testCases:
            self.testTimeSpec(tc[0], tc[1], tc[2])

    def testTimeSpec(self, ical, now, expected):
        print("Testing Timespecs")
        AccessRequirement(timespec=ical)
        self.assertEqual(AccessRequirement.isActiveAt(datetime.fromisoformat(now)), expected)


    icalbase = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//ical.marudot.com//iCal Event Maker
X-WR-CALNAME:Blah
NAME:Blah
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
%S
END:VCALENDAR"""

    testCases = [(icalbase % ("""BEGIN:VEVENT
    DTSTAMP:20200921T184151Z
    UID:20200921T184151Z-184602322@marudot.com
    DTSTART;TZID=America/Chicago:20200923T190000
    RRULE:FREQ=WEEKLY;BYDAY=WE
    DTEND;TZID=America/Chicago:20200923T210000
    SUMMARY:Thing
    END:VEVENT"""), "2020-10-06T05:07:38.000865+00:00", True)]