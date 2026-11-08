"""Generic RSS adapter (e.g. the Western Canada Squarespace feed at /feis-dates?format=rss).

Feeds in this ecosystem usually omit the feis date, so we only keep a date when
one can be found in the title/description. Undated items are written to
data/undated.json for follow-up instead of being merged.
"""
from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET

from ..http import Client
from ..schema import Feis, parse_span
from .base import Adapter, NotConfigured


def parse_feed(xml_text: str, cfg: dict, source: str) -> list[Feis]:
    root = ET.fromstring(xml_text.encode("utf-8"))
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = html.unescape(re.sub(r"<[^>]+>", " ", item.findtext("description") or ""))
        desc = re.sub(r"\s+", " ", desc).strip()
        if not title:
            continue
        s, e = parse_span(f"{title} {desc}")
        f = Feis(
            name=title,
            start_date=s.isoformat() if s else None,
            end_date=e.isoformat() if e else None,
            region=cfg.get("region"), country=cfg.get("country"),
            website=link or None,
            extra={"notes": desc[:300]} if desc else {},
            source=source, source_id=link or title, source_url=link or None,
        )
        out.append(f)
    return out


class RssAdapter(Adapter):
    def fetch(self, client: Client, previous: dict[str, dict]) -> list[Feis]:
        url = self.cfg.get("url")
        if not url:
            raise NotConfigured(f"{self.name}: set 'url' in config/sources.yml")
        page = client.get(url)
        if page.status != 200:
            raise RuntimeError(f"{self.name}: HTTP {page.status}")
        return parse_feed(page.text, self.cfg, self.name)
