"""Fixture = the text lines captured by the probe from quickfeis.com on 2026-11-08 (trimmed),
rendered one-per-<div>. Registration counts and attachment lines are included on purpose:
the parser must ignore them."""
import datetime as dt
import html

from feis_master.adapters.quickfeis import clean_name, infer_dates, parse_home

TODAY = dt.date(2026, 11, 8)

LINES = """QuickFeis 2026
Log in
Create NEW Account
Home
Results
OPEN REGISTRATIONS
Pittsburgh Winter Feis
Pittsburgh Snow Feis
FUTURE FEISES
Wisconsin Winter Feis
Jan 16
Saturday
Open Date:
TBD
Queen City Mini Feis ⭐NEW⭐FEIS⭐
Jan 30
Saturday
Open Date:
TBD
Chicago Feis
May 29-30
Sat & Sun
Open Date:
TBD
Tessie Burke Reel Feis
Jul 25
Saturday
Open Date:
TBD
Welcome to QuickFeis!
Chicago Autumn Feis
Mid America - United States
Sunday
08-Nov-2026
ONLINE REGISTRATION CLOSES:
26-Oct-2026
FEIS VENUE
Canlan Sports
28156 W. Northpointe Pkwy
Lake Barrington
IL
60010
United States
ONLINE REGISTRATION
Opens
11-Sep-2026
Close
26-Oct-2026
LINKS AND ATTACHMENTS
REGISTRATION CAPS
450 NC |350 PC/OC
PAID REGISTRATION
GRADES
297
TOTAL
591
Chicago Autumn Feis
Mid America - United States
Sunday
08-Nov-2026
ONLINE REGISTRATION CLOSES:
26-Oct-2026
STAGE SCHEDULE
Cincinnati Feis
Mid America - United States
Saturday
07-Nov-2026
- (FF, Grades, PC, AA PC)
Sunday
08-Nov-2026
- (Team, FC, OC, Adult Champ)
ONLINE REGISTRATION CLOSES:
26-Oct-2026
FEIS VENUE
The Oasis Conference Center
902 Loveland-Miamiville Road
Loveland
OH
45150
United States
ONLINE REGISTRATION
Opens
24-Sep-2026
Close
26-Oct-2026
IDTANA Southern Region Mini Feis
Southern - United States
Sunday
06-Dec-2026
ONLINE REGISTRATION CLOSES:
03-Nov-2026
FEIS VENUE
Hilton Anatole
2201 N Stemmons Freeway,
Dallas
TX
75027
United States
2026 Mid-America Oireachtas
Mid America - United States
Friday
27-Nov-2026
Sunday
29-Nov-2026
ONLINE REGISTRATION CLOSES:
01-Oct-2026
OIREACHTAS VENUE
The Baird Center
400 W Wisconsin Ave
Milwaukee
WI
53203
United States
ONLINE REGISTRATION
Opens
01-Sep-2026
Late
02-Oct-2026
Close
01-Oct-2026
Feises
Copyright © 2026
QuickFeis
Privacy Policy
Terms of Use""".splitlines()

HTML = "<html><body><form><input type='hidden' name='__VIEWSTATE' value='" + "A" * 500 + "'/>" + \
       "".join(f"<div>{html.escape(ln)}</div>" for ln in LINES) + "</form></body></html>"


def by_name(recs):
    return {r.name: r for r in recs}


def test_future_list_infers_year_from_weekday_and_cleans_names():
    recs, warns = parse_home(HTML, TODAY)
    r = by_name(recs)
    assert r["Wisconsin Winter Feis"].start_date == "2027-01-16"          # Saturday only in 2027
    assert r["Queen City Mini Feis"].start_date == "2027-01-30"           # emoji decoration removed
    assert (r["Chicago Feis"].start_date, r["Chicago Feis"].end_date) == ("2027-05-29", "2027-05-30")
    assert r["Wisconsin Winter Feis"].venue is None and r["Wisconsin Winter Feis"].state is None


def test_weekday_mismatch_is_flagged_not_dropped():
    recs, warns = parse_home(HTML, TODAY)
    f = by_name(recs)["Tessie Burke Reel Feis"]
    assert f.start_date == "2027-07-25" and "date_uncertain" in f.extra
    assert any("Tessie Burke Reel" in w for w in warns)


def test_detail_panels_venue_dates_and_merge_of_repeated_blocks():
    recs, _ = parse_home(HTML, TODAY)
    r = by_name(recs)
    ca = r["Chicago Autumn Feis"]
    assert (ca.start_date, ca.end_date) == ("2026-11-08", "2026-11-08")
    assert (ca.venue, ca.address, ca.city, ca.state, ca.country) == (
        "Canlan Sports", "28156 W. Northpointe Pkwy", "Lake Barrington", "IL", "US")
    assert ca.region == "Mid America"
    assert ca.extra["registration_opens"] == "2026-09-11" and ca.extra["registration_closes"] == "2026-10-26"
    assert sum(1 for x in recs if x.name == "Chicago Autumn Feis") == 1     # repeated panel merged

    cin = r["Cincinnati Feis"]
    assert (cin.start_date, cin.end_date, cin.state) == ("2026-11-07", "2026-11-08", "OH")

    sr = r["IDTANA Southern Region Mini Feis"]
    assert sr.address == "2201 N Stemmons Freeway" and sr.state == "TX"    # trailing comma stripped

    mao = r["2026 Mid-America Oireachtas"]
    assert (mao.start_date, mao.end_date, mao.city, mao.state) == ("2026-11-27", "2026-11-29", "Milwaukee", "WI")


def test_no_counts_or_private_data_stored_and_links_point_to_quickfeis():
    recs, _ = parse_home(HTML, TODAY)
    blob = str([r.to_dict() for r in recs])
    assert "591" not in blob and "REGISTRATION CAPS" not in blob and "AAAA" not in blob
    assert all(r.registration_links == {"quickfeis": "https://www.quickfeis.com/"} for r in recs)
    assert all(r.source_id for r in recs)


def test_infer_dates_edge_cases():
    assert infer_dates("Feb 29", "Tuesday", dt.date(2027, 11, 8))[0] == dt.date(2028, 2, 29)   # leap year skip
    assert infer_dates("garbage", "Sat", TODAY) is None
    assert clean_name("Bell Feis") == "Bell Feis"
