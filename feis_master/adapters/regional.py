"""IDTANA regional pages that publish plain-text calendars.

Each parser takes the page's visible text lines (see textutil.page_lines) and returns Feis
records. Formats were captured from the live pages on 2026-11-08; if a page layout changes
the adapter raises (zero records) and the previous snapshot is kept.

Not covered on purpose: Western US (irregular layout), Mid-Atlantic (image/widget),
Mid America (links only). iCal/ICS exports are never used (robots.txt disallows them).
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Optional

from ..http import Client
from ..schema import Feis, fix_url, parse_span, platform_of
from .base import Adapter
from .textutil import page_lines, parse_location, slug

LABEL = re.compile(r"^[A-Za-z][A-Za-z ]{1,40}:$")
URLISH = re.compile(r"^(https?://|www\.)\S+$|^[\w.-]+\.(com|net|org|ca|ie)(/\S*)?$", re.I)
CANCEL = re.compile(r"cancel+ed", re.I)


def _finish(f: Feis, reg: Optional[str] = None, website: Optional[str] = None) -> Feis:
    reg = fix_url(reg) if reg else None
    if reg and platform_of(reg) != "other":
        f.add_registration(reg)
    elif reg:
        f.add_registration(reg)
    if website:
        f.website = fix_url(website) or website
    return f


def _norm_url(u: str) -> str:
    u = u.strip()
    return u if u.startswith("http") else "https://" + u


# ---------------------------------------------------------------- Western Canada (Squarespace)
HDR_MON = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$")
DATE_LINE = re.compile(r"^(?:[A-Za-z]{3,9},\s+)?[A-Za-z]{3,9}\.?\s+\d{1,2},\s+\d{4}$")


def parse_western_canada(lines: list[str], source: str) -> list[Feis]:
    out, buf = [], []
    for ln in lines:
        if ln.startswith("View Event"):
            f = _wc_block(buf, source)
            if f:
                out.append(f)
            buf = []
        else:
            buf.append(ln)
    return out


def _wc_block(buf: list[str], source: str) -> Optional[Feis]:
    start = next((i for i in range(len(buf) - 1)
                  if HDR_MON.match(buf[i]) and buf[i + 1].isdigit()), None)
    if start is None:
        return None
    i = start + 2
    if i < len(buf) and buf[i].startswith("to "):
        i += 1
    if i >= len(buf):
        return None
    name = buf[i]
    i += 1
    dates = []
    while i < len(buf) and not (buf[i] in ("(map)", "Google Calendar") or LABEL.match(buf[i])):
        if DATE_LINE.match(buf[i]):
            dates.append(buf[i])
        i += 1
    if not dates:
        return None
    s, _ = parse_span(dates[0])
    _, e = parse_span(dates[-1])
    venue = None
    if "(map)" in buf:
        k = buf.index("(map)")
        if k > 0 and not DATE_LINE.match(buf[k - 1]) and buf[k - 1] not in ("ICS", "Google Calendar"):
            venue = buf[k - 1]
    fields: dict[str, str] = {}
    key = None
    for ln in buf[i:]:
        if LABEL.match(ln):
            key = ln[:-1].strip().lower()
        elif key and key not in fields:
            fields[key] = ln
    f = Feis(name=name, start_date=s.isoformat() if s else None,
             end_date=(e or s).isoformat() if (e or s) else None,
             venue=venue, host=fields.get("hosted by"), country="CA", region="Western Canada",
             source=source, source_id=f"{slug(name)}-{s}", source_url=None)
    web = fields.get("feis website") or fields.get("website")
    reg = fields.get("entry website")
    return _finish(f, _norm_url(reg) if reg and URLISH.match(reg) else None,
                   _norm_url(web) if web and URLISH.match(web) else None)


# ---------------------------------------------------------------- New England (Wix)
NE_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})$")


def _ne_date(m: re.Match) -> Optional[dt.date]:
    y = int(m[3]); y += 2000 if y < 100 else 0
    try:
        return dt.date(y, int(m[1]), int(m[2]))
    except ValueError:
        return None


def parse_new_england(lines: list[str], source: str) -> tuple[list[Feis], list[str]]:
    idx = [i for i, ln in enumerate(lines) if NE_DATE.match(ln)]
    out, warns = [], []
    for n, i in enumerate(idx):
        block = lines[i + 1: idx[n + 1] if n + 1 < len(idx) else i + 12]
        if not block:
            continue
        raw, date = block[0], _ne_date(NE_DATE.match(lines[i]))
        if CANCEL.search(raw):
            continue
        name = raw
        pm = re.search(r"\s*-?\s*Postponed to (\d{1,2})/(\d{1,2})/(\d{2,4})", name, re.I)
        if pm:
            date = _ne_date(pm) or date
            name = name[:pm.start()].strip(" -")
        tbd = re.match(r"^POSTPONED\s+NEW DATE TBD\s*-\s*(.+)$", name, re.I)
        if tbd:
            name, date = tbd[1].strip(), None
        name = re.sub(r"\s*\(Rescheduled from [^)]*\)", "", name, flags=re.I).strip()
        def before(label):
            return block[block.index(label) - 1] if label in block and block.index(label) > 1 else None
        host = block[block.index("Host:") + 1] if "Host:" in block and block.index("Host:") + 1 < len(block) else None
        loc = before("Location:")
        web = before("Website:")
        f = Feis(name=name, start_date=date.isoformat() if date else None,
                 end_date=date.isoformat() if date else None,
                 host=host, region="New England", **parse_location(loc or ""),
                 source=source, source_id=f"{slug(name)}-{date}", source_url=None)
        if tbd:
            f.extra["postponed"] = "new date TBD"
        if web and URLISH.match(web):
            f.website = _norm_url(web)      # host's own site, not necessarily a registration link
        out.append(f)
    return out, warns


# ---------------------------------------------------------------- Eastern Canada (Wix)
def parse_eastern_canada(lines: list[str], source: str) -> list[Feis]:
    try:
        a = next(i for i, ln in enumerate(lines) if re.match(r"^20\d\d Feiseanna$", ln))
    except StopIteration:
        return []
    out = []
    i = a + 1
    while i < len(lines) - 1 and not lines[i].startswith("If you are looking"):
        s, e = parse_span(lines[i]) if len(lines[i]) < 50 else (None, None)
        if s:
            name = lines[i + 1]
            out.append(Feis(name=name, start_date=s.isoformat(), end_date=(e or s).isoformat(),
                            country="CA", region="Eastern Canada", source=source,
                            source_id=f"{slug(name)}-{s}", source_url=None))
            i += 2
        else:
            i += 1
    return out


# ---------------------------------------------------------------- Southern (Wix)
SO_DATE = re.compile(r"^(\d{2})/(\d{2})$")


def parse_southern(lines: list[str], source: str) -> tuple[list[Feis], list[str]]:
    year = next((int(m[1]) for ln in lines[:5] if (m := re.search(r"FEIS CALENDAR (\d{4})", ln))), None)
    if not year:
        return [], ["southern: year heading not found"]
    idx = [i for i, ln in enumerate(lines) if SO_DATE.match(ln)]
    out, warns = [], []
    for n, i in enumerate(idx):
        end = min(idx[n + 1] if n + 1 < len(idx) else len(lines), i + 9)
        block = lines[i + 1: end]
        if not block:
            continue
        name = block[0]
        m = SO_DATE.match(lines[i])
        try:
            d = dt.date(year, int(m[1]), int(m[2]))
        except ValueError:
            warns.append(f"southern: invalid date {lines[i]!r} for {name!r}")
            d = None
        host = block[block.index("Host:") + 1] if "Host:" in block and block.index("Host:") + 1 < len(block) \
            and not block[block.index("Host:") + 1].endswith(":") else None
        if host and re.match(r"^[^,]+,\s*[A-Z]{2}$", host):
            host = None                      # the page left Host blank and the city slid up
        tail = block[block.index("Website:") + 1:] if "Website:" in block else []
        loc = tail[0] if tail and not URLISH.match(tail[0]) else None
        web = next((t for t in tail if URLISH.match(t)), None)
        f = Feis(name=name, start_date=d.isoformat() if d else None,
                 end_date=d.isoformat() if d else None, host=host, region="Southern",
                 **parse_location(loc or ""), source=source,
                 source_id=f"{slug(name)}-{d}", source_url=None)
        if web:
            _finish(f, _norm_url(web), None)
        out.append(f)
    return out, warns


# ---------------------------------------------------------------- adapters
class _PageAdapter(Adapter):
    def _lines(self, client: Client) -> list[str]:
        url = self.cfg.get("url")
        page = client.get(url)
        if page.status != 200:
            raise RuntimeError(f"{self.name}: HTTP {page.status}")
        return page_lines(page.text)


class WesternCanadaAdapter(_PageAdapter):
    def fetch(self, client, previous):
        return parse_western_canada(self._lines(client), self.name)


class NewEnglandAdapter(_PageAdapter):
    def fetch(self, client, previous):
        recs, w = parse_new_england(self._lines(client), self.name)
        self.warnings += w
        return recs


class EasternCanadaAdapter(_PageAdapter):
    def fetch(self, client, previous):
        return parse_eastern_canada(self._lines(client), self.name)


class SouthernAdapter(_PageAdapter):
    def fetch(self, client, previous):
        recs, w = parse_southern(self._lines(client), self.name)
        self.warnings += w
        return recs
