"""Fixtures are SYNTHETIC: rebuilt from the page structures observed while researching
(text-level descriptions), not saved copies of the live HTML. Once real pages are
captured (probe workflow / a local save), add them to tests/fixtures and extend these."""
import datetime as dt
import json

from feis_master.adapters.feisworx import parse_table
from feis_master.adapters.idtana import parse_detail
from feis_master.adapters.rss import parse_feed
from feis_master.http import Page
from feis_master.merge import merge
from feis_master.schema import Feis, fix_url, norm_state, parse_span, platform_of

IDTANA_HTML = """
<html><head><title>St. Ambrose Fall Feis 2026 – The Irish Dance Teachers Association of North America</title></head>
<body><nav>Find a Feis</nav>
<h2>Feis Profile</h2><a href="/feiseanna">Back to Directory</a>
<h1>St. Ambrose Fall Feis 2026</h1>
<h3>Date</h3><p>October 3, 2026</p>
<h3>Location</h3><p>Burbank Airport Marriott Hotel and Convention Center</p><p>2500 N. Hollywood Way</p><p>Burbank</p><p>California</p>
<h3>REGISTRATION LINK</h3><p><a href="http://feisinfo.com">http://feisinfo.com</a></p>
<h3>Host</h3><p>St. Ambrose Irish Dance Association, Inc.</p>
<h3>Region</h3><p>Western US</p>
<h3>Feis Website</h3><p><a href="http://clearyirishdance.com">http://clearyirishdance.com</a></p>
<h3>Email Organizer</h3><p>Name</p><p>Email</p><p>Message</p>
</body></html>"""

IDTANA_RANGE_CANADA = """
<h2>Feis Profile</h2><a>Back to Directory</a><h1>Wilson Bryson Dennis Championships</h1>
<h3>Date</h3><p>June 1, 2024</p><p>– June 2, 2024</p>
<h3>Location</h3><p>Anapilis Halls</p><p>2185 Stavebank Rd Mississauga ON L5C 1T3 Canada</p><p>Mississauga</p><p>Ontario</p>
<h3>REGISTRATION LINK</h3><p>https://feis.link/feis/Wilson-Bryson-Dennis+Championships?id=65e8ec</p>
<h3>Host</h3><p>Wilson Bryson Dennis School of Irish Dance</p>
<h3>Region</h3><p>Eastern Canada</p>
<h3>Feis Website</h3><p>http:www.wbdfeis.ca</p>
"""

FEISWORX_HTML = """
<table><tr><td><table>
<tr><td><b>CO State Championships 2026</b><br>Brighton, CO - Nov 7, 2026<br>Mile High Irish Dance<br>
<a href="mailto:x@example.com">Jane Registrar</a></td>
<td>Late: Oct 20 $10<br>No Cap / Yes<br>Registration is CLOSED<br>FeisWorx</td>
<td><a href="show_reg.php?feis=2421">Who's Registered?</a> <a href="http://example.org/co">Website</a></td></tr>
<tr><td><b>Feis On The Gulf 2027</b><br>St. Petersburg, FL - Jan 23-24, 2027<br>Gulf Academy<br></td>
<td>Registration is Open</td><td><a href="judge_list.php?feis=2426">Judges</a></td></tr>
</table></td></tr></table>"""

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Prairie Feis</title><link>https://example.ca/prairie</link>
<description>&lt;p&gt;Saskatoon, SK - hosted by River City. Entries via feis fwd.&lt;/p&gt;</description></item>
<item><title>Dated Feis March 7-8, 2027</title><link>https://example.ca/dated</link><description>x</description></item>
</channel></rss>"""


def test_idtana_detail_basic():
    f = parse_detail(IDTANA_HTML, "https://idtana.org/events/x/")
    assert f.name == "St. Ambrose Fall Feis 2026"
    assert (f.start_date, f.end_date) == ("2026-10-03", "2026-10-03")
    assert f.venue.startswith("Burbank Airport Marriott")
    assert f.address == "2500 N. Hollywood Way"
    assert (f.city, f.state, f.country) == ("Burbank", "CA", "US")
    assert f.region == "Western US" and f.host.startswith("St. Ambrose")
    assert f.registration_links == {"feisinfo": "http://feisinfo.com"}
    assert f.website == "http://clearyirishdance.com"


def test_idtana_range_canada_and_url_repair():
    f = parse_detail(IDTANA_RANGE_CANADA, "https://idtana.org/events/y/")
    assert (f.start_date, f.end_date) == ("2024-06-01", "2024-06-02")
    assert (f.city, f.state, f.country) == ("Mississauga", "ON", "CA")
    assert f.registration_links == {"feislink": "https://feis.link/feis/Wilson-Bryson-Dennis+Championships?id=65e8ec"}
    assert f.website == "http://www.wbdfeis.ca"


def test_feisworx_rows():
    rows = parse_table(FEISWORX_HTML, "https://www.feisworx.com/feisinfo.php")
    assert [r.name for r in rows] == ["CO State Championships 2026", "Feis On The Gulf 2027"]
    a, b = rows
    assert (a.city, a.state, a.start_date) == ("Brighton", "CO", "2026-11-07")
    assert a.source_id == "2421" and a.extra["registration_status"] == "Registration is CLOSED"
    assert a.host == "Mile High Irish Dance"
    assert a.website == "http://example.org/co"
    assert (b.start_date, b.end_date, b.state) == ("2027-01-23", "2027-01-24", "FL")
    # privacy: no e-mail or registrant-list URL leaks into stored fields
    blob = str([r.to_dict() for r in rows])
    assert "example.com" not in blob and "show_reg" not in blob


def test_rss_dates_optional():
    items = parse_feed(RSS, {"region": "Western Canada", "country": "CA"}, "wc")
    assert items[0].start_date is None and items[0].region == "Western Canada"
    assert (items[1].start_date, items[1].end_date) == ("2027-03-07", "2027-03-08")


def test_merge_dedupes_and_unions_links():
    a = Feis(name="Cincinnati Feis 2026", start_date="2026-11-07", state="OH",
             source="idtana", source_url="u1", registration_links={"quickfeis": "https://www.quickfeis.com/"})
    b = Feis(name="The Cincinnati Feis", start_date="2026-11-07", state="OH", venue="Oasis",
             source="feisworx", source_url="u2", registration_links={"feisworx": "https://x/"})
    c = Feis(name="Michael Berry Memorial Feis", start_date="2026-11-07", state="MD", source="idtana")
    out = merge([(10, a), (20, b), (10, c)])
    assert len(out) == 2
    cin = next(f for f in out if "Cincinnati" in f.name)
    assert cin.venue == "Oasis"                      # filled from lower-priority source
    assert set(cin.registration_links) == {"quickfeis", "feisworx"}
    assert {s["source"] for s in cin.sources} == {"idtana", "feisworx"}


def test_merge_does_not_join_different_states_or_dates():
    a = Feis(name="Spring Feis", start_date="2027-03-01", state="OH", source="a")
    b = Feis(name="Spring Feis", start_date="2027-03-01", state="TX", source="b")
    c = Feis(name="Spring Feis", start_date="2027-03-08", state="OH", source="c")
    assert len(merge([(1, a), (2, b), (3, c)])) == 3


def test_helpers():
    assert parse_span("Nov 28 - Dec 1, 2026") == (dt.date(2026, 11, 28), dt.date(2026, 12, 1))
    assert parse_span("Sept 5th, 2026") == (dt.date(2026, 9, 5), dt.date(2026, 9, 5))
    assert parse_span("no date here") == (None, None)
    assert norm_state("Arkansas") == ("AR", "US") and norm_state("Quebec") == ("QC", "CA")
    assert fix_url("http:www.debarrairishdance.com") == "http://www.debarrairishdance.com"
    assert fix_url("mailto:a@b.com") is None
    assert platform_of("https://www.quickfeis.com/x") == "quickfeis"
    assert platform_of("https://www.ifeis.net/") == "ifeis"


# ---------------------------------------------------------------- regressions from the first live run
def test_idtana_venue_that_repeats_city_state_is_dropped():
    html = ("<h2>Feis Profile</h2><a>Back to Directory</a><h1>Diamond State Feis</h1>"
            "<h3>Date</h3><p>November 8, 2026</p>"
            "<h3>Location</h3><p>Rogers, Arkansas</p><p>Rogers</p><p>Arkansas</p>"
            "<h3>REGISTRATION LINK</h3><p>https://www.ifeis.net</p>")
    f = parse_detail(html, "https://idtana.org/events/d/")
    assert f.venue is None and (f.city, f.state) == ("Rogers", "AR")


def test_idtana_rest_pagination_with_lowercase_header():
    from feis_master.adapters.idtana import IdtanaAdapter

    class C:
        calls = []
        def get(self, url):
            C.calls.append(url)
            n = 100 if "&page=1&" in url else 5
            rows = [{"id": i, "link": f"https://idtana.org/events/e{i}/", "title": {"rendered": "x"}} for i in range(n)]
            return Page(url, 200, json.dumps(rows), {"x-wp-totalpages": "2"})   # lowercased, as on the runner
    items = IdtanaAdapter("idtana", 10, {})._enumerate_rest(C())
    assert len(items) == 105 and len(C.calls) == 2


def test_idtana_rest_pagination_without_header_uses_short_page():
    from feis_master.adapters.idtana import IdtanaAdapter

    class C:
        def get(self, url):
            first = "&page=1&" in url
            n = 100 if first else 7
            rows = [{"id": i + (0 if first else 1000), "link": "u", "title": {"rendered": ""}} for i in range(n)]
            return Page(url, 200, json.dumps(rows), {})
    assert len(IdtanaAdapter("idtana", 10, {})._enumerate_rest(C())) == 107


def test_merge_matches_overlapping_date_ranges():
    a = Feis(name="Colorado State Championships & Fall Feis", start_date="2026-11-07",
             end_date="2026-11-08", state="CO", source="idtana")
    b = Feis(name="Colorado Fall Feis 2026", start_date="2026-11-08", end_date="2026-11-08",
             state="CO", source="feisworx", extra={"registration_status": "Registration is Open"})
    out = merge([(10, a), (20, b)])
    assert len(out) == 1 and out[0].extra["registration_status"] == "Registration is Open"


def test_merge_keeps_adjacent_day_events_separate():
    a = Feis(name="North Coast Feis", start_date="2027-02-06", end_date="2027-02-06", state="OH", source="a")
    b = Feis(name="North Coast Feis Grade Exams", start_date="2027-02-07", end_date="2027-02-07", state="OH", source="a")
    assert len(merge([(1, a), (1, b)])) == 2


def test_feisworx_reports_unparsed_ids():
    from feis_master.adapters.feisworx import FeisworxAdapter
    html = FEISWORX_HTML + '<a href="show_reg.php?feis=2499">orphan</a>'

    class C:
        def get(self, url):
            return Page(url, 200, html)
    ad = FeisworxAdapter("feisworx", 20, {})
    ad.fetch(C(), {})
    assert any("2499" in w for w in ad.warnings)
