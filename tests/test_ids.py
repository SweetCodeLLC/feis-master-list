from feis_master.ids import match_quickfeis, parse_quickfeis_catalog
from feis_master.merge import merge
from feis_master.schema import Feis

PAGE = """<select name="ctl00$ContentPlaceHolderBody$DropDownListFeis">
<option value="">----Please Select a Feis--</option>
<option value="1796">Chicago Autumn Feis 2026</option>
<option value="1700">Chicago Autumn Feis 2025</option>
<option value="1801">Indianapolis - SATURDAY Feis 2026</option>
<option value="1802">Indianapolis - FRIDAY Feis 2026</option>
<option value="1650">For The Love of Ireland Feis - Spring 2026</option>
<option value="1651">For The Love of Ireland Feis 2026</option></select>"""


def ev(name, date, qf=True):
    f = Feis(name=name, start_date=date, end_date=date)
    if qf:
        f.registration_links["quickfeis"] = "https://www.quickfeis.com/"
    return f


def test_catalog():
    c = parse_quickfeis_catalog(PAGE)
    assert [(e["id"], e["year"]) for e in c][:3] == [("1796", 2026), ("1700", 2025), ("1801", 2026)]
    assert len(c) == 6 and all(e["id"].isdigit() for e in c)


def test_match_year_and_name():
    c = parse_quickfeis_catalog(PAGE)
    a, b = ev("Chicago Autumn Feis", "2026-11-08"), ev("Indianapolis Feis - Friday", "2026-05-01")
    assert match_quickfeis([a, b], c) == 2
    assert a.platform_ids == {"quickfeis": "1796"} and a.extra["id_match"] == {"quickfeis": "name+year"}
    assert b.platform_ids == {"quickfeis": "1802"}          # FRIDAY beats SATURDAY


def test_no_guess_when_ambiguous_or_unlinked():
    c = parse_quickfeis_catalog(PAGE)
    amb = ev("For The Love of Ireland Feis", "2026-03-01")   # two near-identical catalog names
    unlinked = ev("Chicago Autumn Feis", "2026-11-08", qf=False)
    nomatch = ev("Totally Different Feis", "2026-11-08")
    assert match_quickfeis([amb, unlinked, nomatch], c) == 0
    assert not amb.platform_ids and not unlinked.platform_ids and not nomatch.platform_ids


def test_feisworx_id_carried_through_merge():
    f = Feis(name="Colorado Fall Feis", start_date="2026-11-08", end_date="2026-11-08",
             source="feisworx", source_id="2422")
    i = Feis(name="Colorado Fall Feis", start_date="2026-11-08", end_date="2026-11-08", source="idtana")
    (m,) = merge([(10, i), (20, f)])
    assert m.platform_ids == {"feisworx": "2422"}
