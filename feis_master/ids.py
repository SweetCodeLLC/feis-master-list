"""Per-feis platform ids: each platform's own number for a feis (QuickFeis FeisId, FeisWorx feis).

An app needs these to open a feis's results on the platform. They are event facts, not
dancer data. Two ways to get them:
  * FeisWorx: the id is already in the listing it came from (exact).
  * QuickFeis: its public Results page has a dropdown of every feis (id + "Name Year");
    we match those to master events by year and normalized name (fuzzy, flagged as such).
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from bs4 import BeautifulSoup

from .schema import Feis, name_tokens

QF_SELECT = "DropDownListFeis"
YEAR = re.compile(r"(20\d\d)")


def parse_quickfeis_catalog(html: str) -> list[dict]:
    """Results page -> [{id, name, year}] from the feis dropdown (placeholder option skipped)."""
    soup = BeautifulSoup(html, "html.parser")
    sel = soup.find("select", attrs={"name": re.compile(QF_SELECT)})
    out = []
    for o in (sel.find_all("option") if sel else []):
        val, text = (o.get("value") or "").strip(), re.sub(r"\s+", " ", o.get_text(" ")).strip()
        if not val.isdigit() or not text:
            continue
        years = YEAR.findall(text)
        out.append({"id": val, "name": text, "year": int(years[-1]) if years else None})
    return out


def _score(a: Feis, entry: dict) -> float:
    ta, tb = name_tokens(a.name), name_tokens(entry["name"])
    if not ta or not tb:
        return 0.0
    if ta == tb:
        return 1.0
    sa, sb = set(ta), set(tb)
    ratio = SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    if sa <= sb or sb <= sa:
        ratio = max(ratio, 0.9)
    return ratio


def match_quickfeis(events: list[Feis], catalog: list[dict], threshold: float = 0.85,
                    margin: float = 0.15) -> int:
    """Set platform_ids['quickfeis'] on events that link to QuickFeis. Same year, best name
    match above threshold, and clearly ahead of the runner-up; otherwise leave unset.
    Returns how many were matched."""
    n = 0
    for f in events:
        if "quickfeis" in f.platform_ids or "quickfeis" not in f.registration_links or not f.start_date:
            continue
        year = int(f.start_date[:4])
        scored = sorted(((_score(f, e), e) for e in catalog if e["year"] == year),
                        key=lambda t: t[0], reverse=True)
        if not scored or scored[0][0] < threshold:
            continue
        if len(scored) > 1 and scored[0][0] - scored[1][0] < margin:
            continue                                   # ambiguous: do not guess
        f.platform_ids["quickfeis"] = scored[0][1]["id"]
        f.extra.setdefault("id_match", {})["quickfeis"] = "name+year"
        n += 1
    return n
