"""IDTANA national feis directory (idtana.org).

Enumerates events through the WordPress REST API the site advertises (falls back
to the sitemap), then reads each event's detail page, which carries labelled
fields: Date, Location, REGISTRATION LINK, Host, Region, Feis Website.
The detail page's registration link usually points at the platform used
(QuickFeis, FeisWeb, iFeis, FeisWorx, ...), so it doubles as platform link-out.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from ..http import Client, Disallowed, FetchError
from ..schema import Feis, fix_url, norm_state, parse_span
from .base import Adapter

BASE = "https://idtana.org"
LABELS = {"date", "location", "registration link", "host", "region", "feis website"}
STOP_LINES = {"email organizer", "get in touch", "contact"}


def _lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    out = []
    for ln in soup.get_text("\n").splitlines():
        ln = re.sub(r"\s+", " ", ln).strip()
        if ln and ln.lower() != "edit":
            out.append(ln)
    return out


def _split_location(lines: list[str]) -> dict:
    """Venue / street / city / state from the stacked lines under 'Location'.
    Layout seen on the site: venue, street address, city, state/province."""
    L = [x for x in lines if x]
    res = {"venue": None, "address": None, "city": None, "state": None}
    if not L:
        return res
    if len(L) >= 3:
        res["venue"] = L[0]
        res["state"] = L[-1]
        res["city"] = L[-2]
        res["address"] = " ".join(L[1:-2]) or None
    elif len(L) == 2:
        res["venue"] = L[0]
        m = re.match(r"^(.+?),\s*([A-Za-z .]+)$", L[1])
        if m:
            res["city"], res["state"] = m.group(1), m.group(2)
        else:
            res["city"] = L[1]
    else:
        m = re.match(r"^(.+?),\s*([A-Za-z .]+)$", L[0])
        if m and len(m.group(2).strip()) <= 20:
            res["city"], res["state"] = m.group(1), m.group(2)
        else:
            res["venue"] = L[0]
    return res


def parse_detail(html: str, url: str, fallback_title: str | None = None) -> Feis | None:
    lines = _lines(html)
    low = [x.lower() for x in lines]

    # Feis name: the line after "Back to Directory" (below the "Feis Profile" heading)
    name = None
    for i, x in enumerate(low):
        if x == "back to directory" and i + 1 < len(lines):
            name = lines[i + 1]
            break
    if not name and fallback_title:
        name = fallback_title
    if not name:
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.string:
            name = re.split(r"\s[–—-]\s", soup.title.string.strip())[0]
    if not name:
        return None

    # collect label -> lines
    fields: dict[str, list[str]] = {}
    start_idx = next((i for i, x in enumerate(low) if x == "feis profile"), 0)
    cur = None
    for i in range(start_idx, len(lines)):
        x = low[i]
        if x in LABELS and x not in fields:
            cur = x
            fields[cur] = []
            continue
        if x in STOP_LINES:
            cur = None
            continue
        if cur:
            fields[cur].append(lines[i])

    s, e = parse_span(" ".join(fields.get("date", [])))
    loc = _split_location(fields.get("location", []))
    state, country = norm_state(loc["state"])
    if country is None and re.search(r"\bCanada\b", " ".join(fields.get("location", [])), re.I):
        country = "CA"

    # prefer real hrefs for the two link fields
    soup = BeautifulSoup(html, "html.parser")
    hrefs = {a.get_text(strip=True): a.get("href") for a in soup.find_all("a", href=True)}

    def link_for(label: str) -> str | None:
        for txt in fields.get(label, []):
            u = hrefs.get(txt) or txt
            u = fix_url(u)
            if u:
                return u
        return None

    f = Feis(
        name=name,
        start_date=s.isoformat() if s else None,
        end_date=e.isoformat() if e else None,
        venue=loc["venue"], address=loc["address"], city=loc["city"],
        state=state, country=country,
        region=" ".join(fields.get("region", [])) or None,
        host=" ".join(fields.get("host", [])) or None,
        website=link_for("feis website"),
        source="idtana", source_url=url,
    )
    f.add_registration(link_for("registration link"))
    return f


class IdtanaAdapter(Adapter):
    def _enumerate_rest(self, client: Client) -> list[dict]:
        items, page = [], 1
        while True:
            url = (f"{BASE}/wp-json/wp/v2/events?per_page=100&page={page}"
                   f"&_fields=id,link,title,modified")
            r = client.get(url)
            if r.status != 200:      # WP answers 400 once the page number is out of range
                break
            data = json.loads(r.text)
            if not data:
                break
            for d in data:
                items.append({"id": str(d["id"]), "link": d["link"],
                              "title": re.sub(r"<[^>]+>", "", d.get("title", {}).get("rendered", ""))})
            total = int(r.headers.get("X-WP-TotalPages", page))
            if page >= total:
                break
            page += 1
        return items

    def _enumerate_sitemap(self, client: Client) -> list[dict]:
        seen, items, queue = set(), [], list(client.sitemaps(BASE)) or [f"{BASE}/sitemap.xml"]
        while queue:
            u = queue.pop()
            if u in seen:
                continue
            seen.add(u)
            try:
                r = client.get(u)
            except (FetchError, Disallowed):
                continue
            if r.status != 200:
                continue
            try:
                root = ET.fromstring(r.text.encode("utf-8"))
            except ET.ParseError:
                continue
            for loc in root.iter():
                if loc.tag.endswith("}loc") and loc.text:
                    t = loc.text.strip()
                    if t.endswith(".xml"):
                        queue.append(t)
                    elif "/events/" in t:
                        items.append({"id": t.rstrip("/").rsplit("/", 1)[-1], "link": t, "title": None})
        return items

    def fetch(self, client: Client, previous: dict[str, dict]) -> list[Feis]:
        try:
            items = self._enumerate_rest(client)
        except (FetchError, Disallowed, ValueError, KeyError):
            items = []
        if not items:
            items = self._enumerate_sitemap(client)
        if not items:
            raise FetchError("idtana: could not enumerate events via REST or sitemap")

        cutoff = (dt.date.today() - dt.timedelta(days=14)).isoformat()
        out: list[Feis] = []
        for it in items:
            prev = previous.get(it["id"])
            if prev and (prev.get("end_date") or prev.get("start_date") or "9999") < cutoff:
                out.append(Feis.from_dict(prev))        # long past: don't refetch
                continue
            try:
                page = client.get(it["link"])
            except (FetchError, Disallowed):
                if prev:
                    out.append(Feis.from_dict(prev))
                continue
            if page.status != 200:
                if prev:
                    out.append(Feis.from_dict(prev))
                continue
            f = parse_detail(page.text, it["link"], it.get("title"))
            if f:
                f.source_id = it["id"]
                out.append(f)
        return out
