"""Helpers shared by the text-based adapters (Wix/Squarespace pages render events as plain text)."""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..schema import NAME_TO_ABBR

_ZW = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)
COUNTRIES = {"usa": "US", "united states": "US", "canada": "CA", "mexico": "MX"}


def page_lines(html: str) -> list[str]:
    """Visible text of a page as stripped, non-empty lines (scripts, styles, hidden inputs and
    zero-width characters removed)."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    for t in soup.find_all("input", attrs={"type": "hidden"}):
        t.decompose()
    text = soup.get_text("\n").translate(_ZW).replace("\xa0", " ")
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    return [ln for ln in lines if ln]


def parse_location(s: str) -> dict:
    """'Saxe Middle School, South Avenue, New Canaan, CT, USA' -> venue/address/city/state/country.
    Returns {} for placeholders such as 'To be determined'."""
    s = (s or "").strip()
    if not s or s.lower().startswith(("to be determined", "tbd", "tba")):
        return {}
    parts = [p.strip() for p in s.split(",") if p.strip()]
    country = None
    if parts and parts[-1].lower() in COUNTRIES:
        country = COUNTRIES[parts.pop().lower()]
    state = None
    if parts:
        m = re.match(r"^([A-Za-z]{2})(?:\s+\d{5}(?:-\d{4})?)?$", parts[-1])
        if m:
            state = m[1].upper()
            parts.pop()
        elif parts[-1].lower() in NAME_TO_ABBR:
            state = NAME_TO_ABBR[parts.pop().lower()]
    city = parts.pop() if parts else None
    venue = address = None
    if parts:
        if re.match(r"^\d", parts[0]):
            address = ", ".join(parts)
        else:
            venue = parts[0]
            address = ", ".join(parts[1:]) or None
    return {k: v for k, v in dict(venue=venue, address=address, city=city, state=state, country=country).items() if v}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
