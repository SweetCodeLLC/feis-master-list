"""FeisWorx upcoming-feis table (https://www.feisworx.com/feisinfo.php).

One server-rendered table row per feis; fields are stacked in the first cell
separated by line breaks. Privacy: registrar e-mails and the "Who's Registered?"
(registrant list) pages are deliberately NOT read or stored.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..http import Client
from ..schema import Feis, fix_url, norm_state, parse_span
from .base import Adapter

LOC_DATE_RE = re.compile(r"^(?P<city>.+?),\s*(?P<st>[A-Za-z][A-Za-z .]{1,24}?)\s*[-–—]\s*(?P<date>.+)$")
FEIS_ID_RE = re.compile(r"[?&]feis=(\d+)")


def parse_table(html: str, page_url: str) -> list[Feis]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Feis] = []
    for tr in soup.find_all("tr"):
        if tr.find("table") is not None:        # skip layout rows that wrap tables
            continue
        cells = tr.find_all("td", recursive=False)
        if not cells:
            continue
        first = cells[0]
        lines = [re.sub(r"\s+", " ", x).strip() for x in first.get_text("\n").splitlines()]
        lines = [x for x in lines if x]
        loc_i = next((i for i, x in enumerate(lines) if LOC_DATE_RE.match(x)), None)
        if loc_i is None:
            continue
        m = LOC_DATE_RE.match(lines[loc_i])
        s, e = parse_span(m["date"])
        if not s:
            continue
        bold = first.find(["b", "strong"])
        name = (bold.get_text(" ", strip=True) if bold else (lines[loc_i - 1] if loc_i else "")).strip()
        if not name:
            continue
        state, country = norm_state(m["st"])
        host = lines[loc_i + 1] if loc_i + 1 < len(lines) else None
        if host and host.lower().startswith(("registrar", "contact")):
            host = None

        row_text = tr.get_text(" ", strip=True)
        status = None
        for pat in (r"Registration is (?:CLOSED|Closed|Open|OPEN)", r"Registration is [A-Za-z ]{3,20}"):
            sm = re.search(pat, row_text)
            if sm:
                status = sm.group(0)
                break

        feis_id = None
        website = None
        for a in tr.find_all("a", href=True):
            idm = FEIS_ID_RE.search(a["href"])
            if idm and not feis_id:
                feis_id = idm.group(1)
            txt = a.get_text(" ", strip=True).lower()
            if txt in ("website", "feis website", "web site") and not website:
                website = fix_url(a["href"])

        f = Feis(
            name=name, start_date=s.isoformat(), end_date=e.isoformat(),
            city=m["city"].strip(), state=state, country=country,
            host=host, website=website,
            extra={"registration_status": status} if status else {},
            source="feisworx", source_id=feis_id, source_url=page_url,
        )
        f.registration_links["feisworx"] = page_url   # public listing page, not registrant lists
        out.append(f)
    return out


class FeisworxAdapter(Adapter):
    def fetch(self, client: Client, previous: dict[str, dict]) -> list[Feis]:
        url = self.cfg.get("url", "https://www.feisworx.com/feisinfo.php")
        page = client.get(url)
        if page.status != 200:
            raise RuntimeError(f"feisworx: HTTP {page.status}")
        rows = parse_table(page.text, url)
        if not rows:
            raise RuntimeError("feisworx: parsed 0 rows (page layout changed?)")
        return rows
