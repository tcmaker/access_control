import sqlite3
import typing
from datetime import datetime

dayNames = {0:"Sunday", 1:"Monday",2:"Tuesday",3:"Wednesday",4:"Thursday",5:"Friday",6:"Saturday"}

def formatColor(b, m):
    hex = 255 - int(255 * float(b) / m)
    return "#{:02x}{:02x}{:02x}".format(hex,hex,hex)

def formatTextColor(h):
    value = int(h[1:3],16)
    return "#aaaaaa" if value < 80 else "#000000"

buckets = {}
for day in range(0,7):
    buckets[day] = {}
    for hour in range(0,24):
        buckets[day][hour] = 0

con = sqlite3.connect("dooractivity.db",detect_types=sqlite3.PARSE_COLNAMES)

cur = con.cursor()
for row in cur.execute('select timestamp as "[timestamp]" from activity where result = \'denied\''):
    dd: datetime = row[0]
    buckets[dd.weekday()][dd.hour] = buckets[dd.weekday()][dd.hour] + 1

maxscans = -1
for day in range(0,7):
    for hour in range(0,24):
        maxscans = max(maxscans, buckets[day][hour])

times = [f"{datetime(2020,1,1,h).strftime('%I %p')}" for h in range(0,24)]
print(f"<tr><th></th>{str.join('',[f'<th>{t}</th>' for t in times])}</tr>")
for d in range(0,7):
    tds = [f"<td style=\"color: {formatTextColor(formatColor(buckets[d][h],maxscans))}; background: {formatColor(buckets[d][h],maxscans)}\">{buckets[d][h]}</td>" for h in range(0,24)]
    print(f"<tr><th>{dayNames[d]}</th>{str.join('',tds)}</tr>")

