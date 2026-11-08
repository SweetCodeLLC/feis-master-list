"""QuickFeis home page (https://www.quickfeis.com/).

Server-rendered ASP.NET page. Two kinds of content are read from its text:
  * "FUTURE FEISES": name / "Jan 16" / weekday / "Open Date:". No year and no venue, so the
    year is inferred from the weekday (Jan 16 + Saturday -> 2027).
  * Detail panels for feiseanna open for registration: title, "<Region> - <Country>",
    weekday + dd-Mon-yyyy lines, and a FEIS/OIREACHTAS VENUE block (name, street, city,
    state, zip, country).
Aggregate registration counts shown on the page are ignored on purpose.

NOTE: the page footer links a Terms of Use that has not been reviewed, so this source is
disabled in config/sources.yml until someone has read it.
"""
from __future__ import annotations

import datetime as dt
import re

from bs4 import BeautifulSoup

from ..http import Client
from ..schema import MONTHS, Feis, norm_state
from .base import Adapter

HOME = "https://www.quickfeis.com/"
DMY = re.compile(r"^(\d{2})-([A-Za-z]{3})-(\d{4})$")
REGION = re.compile(r"^(?P<region>.+?) - (?P<country>United States|Canada|Mexico)$")
SHORT = re.compile(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?$")
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
FULL_WEEKDAYS = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
COUNTRY = {"United States": "US", "Canada": "CA", "Mexico": "MX"}
EMOJI = re.compile("[←-⯿\U0001F000-\U0001FAFF️]")   # arrows..dingbats..stars, plus emoji


def page_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    for t in soup.find_all("input", attrs={"type": "hidden"}):
        t.decompose()
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in soup.get_text("\n").splitlines()]
    return [ln for ln in lines if ln]


def clean_name(s: str) -> str:
    return EMOJI.split(s)[0].strip(" -–")


def _dmy(s: str) -> dt.date | None:
    m = DMY.match(s)
    if not m:
        return None
    mon = MONTHS.get(m[2].lower())
    try:
        return dt.date(int(m[3]), mon, int(m[1])) if mon else None
    except ValueError:
        return None


def infer_dates(text: str, weekday_text: str, today: dt.date):
    """('May 29-30', 'Sat & Sun') -> (start, end, uncertain). Picks the first year, from this
    one on, whose date falls on the stated weekday; if none does, uses the next occurrence
    and flags it."""
    m = SHORT.match(text.strip())
    if not m:
        return None
    mon = MONTHS.get(m[1].lower())
    if not mon:
        return None
    d1, d2 = int(m[2]), int(m[3] or m[2])
    wd = weekday_text.strip()[:3].lower()
    fallback = None
    for year in (today.year, today.year + 1, today.year + 2):
        try:
            start, end = dt.date(year, mon, d1), dt.date(year, mon, d2)
        except ValueError:
            continue
        if start < today:
            continue
        if fallback is None:
            fallback = (start, end)
        if wd in WEEKDAYS and WEEKDAYS[start.weekday()] == wd:
            return start, end, False
    return (fallback[0], fallback[1], True) if fallback else None


def _venue(block: list[str]) -> dict:
    out = {}
    for i, ln in enumerate(block):
        if ln in ("FEIS VENUE", "OIREACHTAS VENUE"):
            c = next((j for j in range(i + 1, min(i + 9, len(block))) if block[j] in COUNTRY), None)
            if c is None:
                break
            seg = block[i + 1:c]
            if len(seg) >= 4:
                out["venue"] = seg[0]
                out["address"] = " ".join(seg[1:-3]).rstrip(", ") or None
                out["city"], out["state"], out["zip"] = seg[-3], seg[-2], seg[-1]
            elif len(seg) == 3:
                out["venue"], out["city"], out["state"] = seg
            out["country_name"] = block[c]
            break
    return out


def parse_home(html: str, today: dt.date | None = None) -> tuple[list[Feis], list[str]]:
    today = today or dt.date.today()
    lines = page_lines(html)
    warnings: list[str] = []
    found: dict[tuple[str, str], Feis] = {}

    def add(f: Feis) -> None:
        key = (re.sub(r"\W+", "", f.name.lower()), f.start_date)
        cur = found.get(key)
        if not cur:
            found[key] = f
            return
        for fld in ("end_date", "venue", "address", "city", "state", "country", "region"):
            if not getattr(cur, fld) and getattr(f, fld):
                setattr(cur, fld, getattr(f, fld))
        for k, v in f.extra.items():
            cur.extra.setdefault(k, v)

    # ---- FUTURE FEISES list
    try:
        start = lines.index("FUTURE FEISES") + 1
    except ValueError:
        start = None
    if start is not None:
        end = next((i for i in range(start, len(lines)) if lines[i].startswith("Welcome to QuickFeis")), len(lines))
        for i in range(start + 3, end):
            if lines[i] != "Open Date:":
                continue
            name, datetxt, wk = clean_name(lines[i - 3]), lines[i - 2], lines[i - 1]
            res = infer_dates(datetxt, wk, today)
            if not name or not res:
                warnings.append(f"future list: could not read '{lines[i-3]} / {datetxt} / {wk}'")
                continue
            s, e, uncertain = res
            f = Feis(name=name, start_date=s.isoformat(), end_date=e.isoformat(), source="quickfeis",
                     source_url=HOME, extra={"date_inferred_from_weekday": True})
            if uncertain:
                f.extra["date_uncertain"] = f"'{datetxt}' on '{wk}' matches no upcoming year"
                warnings.append(f"{name}: {f.extra['date_uncertain']}")
            f.registration_links["quickfeis"] = HOME
            add(f)

    # ---- detail panels
    idx = [i for i, ln in enumerate(lines) if i >= 1 and REGION.match(ln)]
    for n, i in enumerate(idx):
        nxt = idx[n + 1] - 1 if n + 1 < len(idx) else len(lines)    # next block's title line
        block = lines[i + 1:nxt]
        m = REGION.match(lines[i])
        dates = []
        for ln in block:
            if ln.startswith("ONLINE REGISTRATION CLOSES"):
                break
            d = _dmy(ln)
            if d:
                dates.append(d)
        if not dates:
            continue
        v = _venue(block)
        state, country = norm_state(v.get("state"))
        f = Feis(
            name=clean_name(lines[i - 1]), start_date=min(dates).isoformat(), end_date=max(dates).isoformat(),
            venue=v.get("venue"), address=v.get("address"), city=v.get("city"),
            state=state, country=country or COUNTRY[m["country"]], region=m["region"],
            source="quickfeis", source_url=HOME,
        )
        for label, key in (("ONLINE REGISTRATION CLOSES:", "registration_closes"), ("Opens", "registration_opens")):
            for j, ln in enumerate(block[:-1]):
                if ln == label and _dmy(block[j + 1]):
                    f.extra[key] = _dmy(block[j + 1]).isoformat()
                    break
        f.registration_links["quickfeis"] = HOME
        add(f)

    recs = list(found.values())
    for f in recs:
        f.source_id = f"{re.sub(r'[^a-z0-9]+', '-', f.name.lower()).strip('-')}-{f.start_date}"
    return recs, warnings


class QuickFeisAdapter(Adapter):
    def fetch(self, client: Client, previous: dict[str, dict]) -> list[Feis]:
        page = client.get(self.cfg.get("url", HOME))
        if page.status != 200:
            raise RuntimeError(f"quickfeis: HTTP {page.status}")
        recs, warns = parse_home(page.text)
        self.warnings.extend(warns[:10])
        if not recs:
            raise RuntimeError("quickfeis: parsed 0 events (page layout changed?)")
        return recs
