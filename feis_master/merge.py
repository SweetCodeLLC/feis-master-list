"""Merge per-source records into one master list.

Two records are the same feis when their date ranges overlap, their states
agree (or one is missing), and their normalized names match closely. Registration
links from every source are kept (platform -> url) instead of picking one.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from .schema import Feis, name_tokens


def _same(a: Feis, b: Feis) -> bool:
    if not a.start_date or not b.start_date:
        return False
    a_end, b_end = a.end_date or a.start_date, b.end_date or b.start_date
    if not (a.start_date <= b_end and b.start_date <= a_end):   # date ranges must overlap
        return False
    if a.state and b.state and a.state != b.state:
        return False
    ta, tb = name_tokens(a.name), name_tokens(b.name)
    if not ta or not tb:
        return False
    if ta == tb or set(ta) <= set(tb) or set(tb) <= set(ta):
        return True
    return SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio() >= 0.85


def _absorb(base: Feis, other: Feis) -> None:
    for fld in ("end_date", "venue", "address", "city", "state", "country",
                "region", "host", "website"):
        if not getattr(base, fld) and getattr(other, fld):
            setattr(base, fld, getattr(other, fld))
    for plat, url in other.registration_links.items():
        base.registration_links.setdefault(plat, url)
    for k, v in other.extra.items():
        base.extra.setdefault(k, v)
    for s in other.sources:
        if s not in base.sources:
            base.sources.append(s)


def merge(records: list[tuple[int, Feis]]) -> list[Feis]:
    """records: (priority, Feis); lower priority number wins field conflicts."""
    ordered = sorted(records, key=lambda t: (t[0], t[1].name))
    out: list[Feis] = []
    for _prio, rec in ordered:
        rec.sources = [{"source": rec.source, "url": rec.source_url}]
        if not rec.start_date:
            continue
        hit = next((m for m in out if _same(m, rec)), None)
        if hit:
            _absorb(hit, rec)
        else:
            out.append(rec)
    out.sort(key=lambda f: (f.start_date or "", f.name.lower()))
    return out
