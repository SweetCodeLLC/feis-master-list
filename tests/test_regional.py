"""Fixtures are trimmed text lines captured by the probe workflow on 2026-11-08."""
from feis_master.adapters.regional import (parse_eastern_canada, parse_new_england,
                                           parse_southern, parse_western_canada)
from feis_master.adapters.textutil import page_lines, parse_location
from feis_master.schema import parse_span
import datetime as dt

WC = """FIND A FEIS IN WESTERN CANADA
— Feiseanna Calendar —
Nov
13
to Nov 15
Western Canada Regional Oireachtas
Fri, Nov 13, 2026
7:00 a.m.
Sun, Nov 15, 2026
8:00 p.m.
Hyatt Regency Calgary
(map)
Google Calendar
ICS
Website:
wcidta.ca/oireachtas
View Event →
Feb
6
Salish Sea Feis
Saturday, February 6, 2027
7:00 a.m.
8:00 p.m.
Mary Winspear Centre
(map)
Google Calendar
ICS
Hosted by:
O’Brien School of Irish Dance and OSIDPA
Feis Website:
https://obrienirishdance.com
Entry Website:
www.ifeis.net
View Event →
Feb
13
to Feb 14
Van Eire Feis
Sat, Feb 13, 2027
8:00 a.m.
Sun, Feb 14, 2027
6:00 p.m.
Google Calendar
ICS
Saturday, February 14, 2026
Richmond Olympic Oval
(map)
Entry Website:
Ifeis.net
View Event →""".splitlines()

NE = """2026
01/25/26
Fairfield County Championships - Postponed to 3/21/26
Host:
Harney Pender Keady
Saxe Middle School, South Avenue, New Canaan, CT, USA
Location:
https://www.penderkeady.com/
Website:
02/01/26
Murray Academy Winter Feis
Host:
Murray Academy
100 Academic Way, Stratham, NH 03885, USA
Location:
https://www.cararince.com/
Website:
03/01/26
POSTPONED NEW DATE TBD - Hansen Keohane Memorial Feis
Host:
Hansen Keohane
To be determined
Location:
https://example.org/
Website:
10/03/26
10/03/26 - Canceled for 2026
Host:
Somebody
Stratford, CT, USA
Location:
https://example.net/
Website:""".splitlines()

EC = """Regional Feiseanna | IDTAC-ER
2026 Feiseanna
January 29 - February 1, 2026
Canadian National Irish Dance Championships
March 14 & 15, 2026
Diamond Championships & Grades Feis
Saturday, May 16, 2026
Feis Montreal
If you are looking to start a new feis, or register an existing one, please refer to:
Feis Registration Procedures (PDF)""".splitlines()

SO = """FEIS CALENDAR 2026 | IDTANA-SR
01/25
Florida State Championships
Host:
Scariff School
Location:
Website:
Tampa, FL, USA
http://www.feisworx.com
02/28
Mexico Feis
Host:
Irish Dancing De Mexico
Location:
Website:
Mexico City, CDMX, Mexico
02/29
Cowtown Feis
Host:
McTeggart School
Location:
Website:
Coppell, TX, USA
http://www.feisworx.com""".splitlines()


def test_western_canada():
    r = parse_western_canada(WC, "wc")
    assert [f.name for f in r] == ["Western Canada Regional Oireachtas", "Salish Sea Feis", "Van Eire Feis"]
    a, b, c = r
    assert (a.start_date, a.end_date, a.venue) == ("2026-11-13", "2026-11-15", "Hyatt Regency Calgary")
    assert a.website == "https://wcidta.ca/oireachtas" and a.country == "CA"
    assert b.start_date == b.end_date == "2027-02-06"
    assert b.host.startswith("O’Brien") and b.registration_links == {"ifeis": "https://www.ifeis.net"}
    # stray old date after "Google Calendar" must not extend the range
    assert (c.start_date, c.end_date, c.venue) == ("2027-02-13", "2027-02-14", "Richmond Olympic Oval")


def test_new_england():
    r, _ = parse_new_england(NE, "ne")
    assert [f.name for f in r] == ["Fairfield County Championships", "Murray Academy Winter Feis",
                                   "Hansen Keohane Memorial Feis"]       # cancelled one skipped
    a, b, c = r
    assert a.start_date == "2026-03-21" and a.city == "New Canaan" and a.state == "CT"
    assert a.host == "Harney Pender Keady" and a.website == "https://www.penderkeady.com/"
    assert b.start_date == "2026-02-01" and b.address == "100 Academic Way" and b.state == "NH"
    assert c.start_date is None and c.extra["postponed"] == "new date TBD" and c.city is None


def test_eastern_canada():
    r = parse_eastern_canada(EC, "ec")
    assert [(f.name, f.start_date, f.end_date) for f in r] == [
        ("Canadian National Irish Dance Championships", "2026-01-29", "2026-02-01"),
        ("Diamond Championships & Grades Feis", "2026-03-14", "2026-03-15"),
        ("Feis Montreal", "2026-05-16", "2026-05-16")]
    assert all(f.country == "CA" and f.region == "Eastern Canada" for f in r)


def test_southern():
    r, w = parse_southern(SO, "so")
    assert len(r) == 3 and r[0].start_date == "2026-01-25" and r[0].city == "Tampa"
    assert r[0].host == "Scariff School" and r[0].registration_links == {"feisworx": "http://www.feisworx.com"}
    assert r[1].country == "MX" and not r[1].registration_links
    assert r[2].start_date is None and "02/29" in w[0]


def test_helpers():
    assert parse_span("March 14 & 15, 2026") == (dt.date(2026, 3, 14), dt.date(2026, 3, 15))
    assert page_lines("<p>A​ B</p><script>x</script><p> </p>") == ["A B"]
    assert parse_location("To be determined") == {}
