"""Shared record schema plus normalization helpers (dates, states, URLs, names)."""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Optional
from urllib.parse import urlparse

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district of columbia": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA",
    "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}
CA_PROVINCES = {
    "alberta": "AB", "british columbia": "BC", "manitoba": "MB", "new brunswick": "NB",
    "newfoundland and labrador": "NL", "newfoundland": "NL", "nova scotia": "NS",
    "northwest territories": "NT", "nunavut": "NU", "ontario": "ON",
    "prince edward island": "PE", "quebec": "QC", "québec": "QC", "saskatchewan": "SK",
    "yukon": "YT",
}
US_ABBR = set(US_STATES.values())
CA_ABBR = set(CA_PROVINCES.values())
NAME_TO_ABBR = {**US_STATES, **CA_PROVINCES}


def norm_state(raw: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Return (state_abbr_or_raw, country). Country is None when unrecognized."""
    if not raw:
        return None, None
    t = raw.strip().rstrip(".")
    if not t:
        return None, None
    up = t.upper()
    if up in US_ABBR:
        return up, "US"
    if up in CA_ABBR:
        return up, "CA"
    ab = NAME_TO_ABBR.get(t.lower())
    if ab:
        return ab, ("CA" if ab in CA_ABBR else "US")
    return t, None


# ---------------------------------------------------------------- dates
_MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july",
                "august", "september", "october", "november", "december"]
MONTHS = {m: i for i, m in enumerate(_MONTH_NAMES, 1)}
MONTHS.update({m[:3]: i for i, m in enumerate(_MONTH_NAMES, 1)})
MONTHS["sept"] = 9

_MON = r"[A-Za-z]{3,9}"
DATE_RE = re.compile(rf"(?P<mon>{_MON})\.?\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?,?\s+(?P<y>\d{{4}})")
SPAN_RE = re.compile(
    rf"(?P<m1>{_MON})\.?\s+(?P<d1>\d{{1,2}})\s*(?:[-–—]|&|and)\s*"
    rf"(?:(?P<m2>{_MON})\.?\s+)?(?P<d2>\d{{1,2}}),?\s+(?P<y>\d{{4}})"
)


def _mk(y: int, mon: str, d: int) -> Optional[dt.date]:
    m = MONTHS.get(mon.lower())
    if not m:
        return None
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


def parse_span(text: str) -> tuple[Optional[dt.date], Optional[dt.date]]:
    """Parse 'Nov 7, 2026', 'Nov 7-8, 2026', 'Nov 28 - Dec 1, 2026',
    or 'June 1, 2024 - June 2, 2024' into (start, end)."""
    if not text:
        return None, None
    for m in SPAN_RE.finditer(text):
        y = int(m["y"])
        start = _mk(y, m["m1"], int(m["d1"]))
        end = _mk(y, m["m2"] or m["m1"], int(m["d2"]))
        if start and end:
            return start, end
    found = []
    for m in DATE_RE.finditer(text):
        d = _mk(int(m["y"]), m["mon"], int(m["d"]))
        if d:
            found.append(d)
    if found:
        return min(found), max(found)
    return None, None


# ---------------------------------------------------------------- urls
PLATFORM_HOSTS = {
    "feisworx.com": "feisworx", "quickfeis.com": "quickfeis", "feisweb.com": "feisweb",
    "ifeis.net": "ifeis", "ifeis.com": "ifeis", "planxti.com": "planxti",
    "feisinfo.com": "feisinfo", "feis.link": "feislink", "feisfwd.com": "feisfwd",
    "efeis.com": "efeis", "feiskeeper.com": "feiskeeper",
}


def fix_url(raw: Optional[str]) -> Optional[str]:
    """Repair common malformed URLs (e.g. 'http:www.x.com') and reject non-http values."""
    if not raw:
        return None
    u = raw.strip().split()[0] if raw.strip() else ""
    if not u or u.lower().startswith("mailto:") or "@" in u.split("/")[0]:
        return None
    u = re.sub(r"^(https?):(?!//)", r"\1://", u, flags=re.I)
    if not re.match(r"^https?://", u, re.I):
        if re.match(r"^[\w-]+(\.[\w-]+)+(/|$)", u):
            u = "https://" + u
        else:
            return None
    return u


def platform_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for dom, name in PLATFORM_HOSTS.items():
        if host == dom or host.endswith("." + dom):
            return name
    return "other"


# ---------------------------------------------------------------- names
_STOP = {"the", "annual", "feis", "feiseanna", "feile", "irish", "dance", "dancing",
         "and", "of", "at", "championships", "championship", "grades", "grade",
         "st", "nd", "rd", "th", "day"}


def name_tokens(name: str) -> list[str]:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\b(19|20)\d{2}\b", " ", s)   # drop years
    s = re.sub(r"\b\d+(st|nd|rd|th)\b", " ", s)
    toks = re.findall(r"[a-z0-9]+", s)
    return [t for t in toks if t not in _STOP]


# ---------------------------------------------------------------- record
@dataclass
class Feis:
    name: str
    start_date: Optional[str] = None          # ISO yyyy-mm-dd
    end_date: Optional[str] = None
    venue: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None               # 2-letter abbreviation when recognized
    country: Optional[str] = None
    region: Optional[str] = None
    host: Optional[str] = None
    website: Optional[str] = None
    registration_links: dict = field(default_factory=dict)   # platform -> url
    extra: dict = field(default_factory=dict)
    source: str = ""
    source_id: Optional[str] = None
    source_url: Optional[str] = None
    sources: list = field(default_factory=list)              # [{"source","url"}] after merge

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Feis":
        names = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in names})

    def add_registration(self, url: Optional[str]) -> None:
        u = fix_url(url)
        if u:
            self.registration_links.setdefault(platform_of(u), u)
