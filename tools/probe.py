"""Fetch a few pages politely, save raw HTML + API-looking URLs, and ALSO print what is
needed to write an adapter into the run log (so no artifact download is required).

Usage: python tools/probe.py URL [URL ...]   (run from the repo root)

Small pages are printed in full; large pages get a readable text view, sample event rows and a structural
skeleton (repeated tag/class combos, link patterns, script sources). Every printed
line is indented so page content can never be read as a GitHub workflow command."""
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from feis_master.http import Client, Disallowed  # noqa: E402

FULL_LIMIT = 40_000      # print the whole page when it is at most this many characters
HINT_RE = re.compile(r"""["'(](https?://[^"'()\s]+|/[^"'()\s]*)(api|json|graphql|ajax|feis)[^"'()\s]*""", re.I)


def out(line: str = "") -> None:
    print("  " + line)        # leading spaces: '::' at line start would be a workflow command


def block(title: str, text: str) -> None:
    out(f"----- {title} -----")
    for ln in text.splitlines():
        out(ln.rstrip())
    out(f"----- end {title} -----")


def skeleton(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    parts = []
    combos = Counter()
    for t in soup.find_all(True):
        cls = ".".join(t.get("class", [])[:3])
        combos[f"{t.name}{'.' + cls if cls else ''}"] += 1
    parts.append("repeated tag.class combos (count >= 3):")
    parts += [f"  {n:4d}  {k}" for k, n in combos.most_common(60) if n >= 3]

    pats: dict[str, tuple[int, str]] = {}
    for a in soup.find_all("a", href=True):
        h = a["href"]
        key = re.sub(r"\d+", "N", urlparse(h).path)[:80] or h[:80]
        n, ex = pats.get(key, (0, h))
        pats[key] = (n + 1, ex)
    parts.append("link patterns (path with digits as N), count, example:")
    for k, (n, ex) in sorted(pats.items(), key=lambda kv: -kv[1][0])[:40]:
        parts.append(f"  {n:4d}  {k}   e.g. {ex[:120]}")

    parts.append("script sources / inline JSON hints:")
    for s in soup.find_all("script"):
        if s.get("src"):
            parts.append(f"  src={s['src'][:150]}")
        elif s.string and re.search(r"(api|json|graphql|fetch\(|XMLHttpRequest)", s.string, re.I):
            parts.append("  inline: " + re.sub(r"\s+", " ", s.string.strip())[:300])
    parts.append("form actions: " + (", ".join(f.get("action", "") for f in soup.find_all("form")) or "none"))
    return "\n".join(parts)


DATE_HINT = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? +\d{1,2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b", re.I)


def strip_hidden(html: str) -> str:
    """Shorten the value of hidden inputs (ASP.NET __VIEWSTATE etc.) so it doesn't drown the log."""
    def repl(m: re.Match) -> str:
        tag = m.group(0)
        if not re.search(r"""type\s*=\s*["']?hidden""", tag, re.I):
            return tag
        return re.sub(r"""(value\s*=\s*)(["'])(.*?)\2""",
                      lambda v: f'{v.group(1)}{v.group(2)}[{len(v.group(3))} chars]{v.group(2)}', tag,
                      flags=re.S | re.I)
    return re.sub(r"<input\b[^>]*>", repl, html, flags=re.I | re.S)


def text_view(html: str, limit: int = 9000) -> str:
    """Readable text of the page with scripts, styles and hidden inputs (e.g. ASP.NET
    __VIEWSTATE, ~11 KB of noise) removed."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    for t in soup.find_all("input", attrs={"type": "hidden"}):
        t.decompose()
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in soup.get_text("\n").splitlines()]
    return "\n".join(ln for ln in lines if ln)[:limit]


def sample_rows(html: str, n: int = 4, cap: int = 2500) -> str:
    """Raw HTML of the first few innermost table rows that look like event rows."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup.find_all("input", attrs={"type": "hidden"}):
        t.decompose()
    out_rows = []
    for tr in soup.find_all("tr"):
        if tr.find("table") is not None:
            continue
        txt = tr.get_text(" ", strip=True)
        if DATE_HINT.search(txt) and len(txt) > 15:
            out_rows.append(str(tr)[:cap])
        if len(out_rows) >= n:
            break
    return "\n\n".join(out_rows) or "(no table rows with dates found)"


def legal_links(html: str) -> str:
    """Links that look like terms / privacy / policy pages (absolute where possible)."""
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for a in soup.find_all("a"):
        txt = a.get_text(" ", strip=True)
        href = a.get("href") or ""
        blob = f"{txt} {href}"
        if re.search(r"terms|privacy|policy|conditions|legal|disclaimer|robots", blob, re.I):
            found.append(f"{txt[:60]!r} -> {href[:200]}")
    return "\n".join(dict.fromkeys(found)) or "(none found)"


def js_endpoints(js: str, limit: int = 120) -> str:
    """API-looking strings in a JavaScript bundle (for single-page apps)."""
    found = []
    pats = [r"""["'`](/?(?:api|rest|v\d)/[A-Za-z0-9_\-./{}:?=&$+]*)["'`]""",
            r"""https?://[A-Za-z0-9_.\-]+/[A-Za-z0-9_\-./{}:?=&]*(?:api|json)[A-Za-z0-9_\-./{}:?=&]*""",
            r"""\.(?:get|post|query)\(\s*["'`]([^"'`]{3,120})["'`]"""]
    for pat in pats:
        for m in re.finditer(pat, js, re.I):
            v = m.group(1) if m.groups() else m.group(0)
            if v not in found:
                found.append(v)
    return "\n".join(found[:limit]) or "(no API-looking strings found)"


def emit(url: str, status: int, html: str, hints: list[str]) -> None:
    out(f"===== BEGIN {url} (HTTP {status}, {len(html)} chars) =====")
    if urlparse(url).path.lower().endswith(".js"):
        block("API-looking strings in bundle", js_endpoints(html))
        out(f"===== END {url} =====")
        return
    block("URL hints", "\n".join(hints) or "(none)")
    block("legal-looking links", legal_links(html))
    if len(html) <= FULL_LIMIT:
        block("full HTML", strip_hidden(html))
    else:
        block("text view (scripts/hidden inputs removed)", text_view(html))
        block("sample event-like table rows (raw HTML)", sample_rows(html))
        block("skeleton", skeleton(html))
    out(f"===== END {url} =====")


def main(urls: list[str]) -> None:
    outdir = Path("probe_out")
    outdir.mkdir(exist_ok=True)
    client = Client(cache_dir=".cache/probe")
    for url in urls:
        host = urlparse(url).netloc.replace(":", "_")
        try:
            page = client.get(url)
        except Disallowed:
            print(f"{url}: disallowed by robots.txt - skipping")
            continue
        except Exception as e:
            print(f"{url}: {e}")
            continue
        (outdir / f"{host}.html").write_text(page.text, encoding="utf-8")
        hints = sorted({m.group(0)[1:] for m in HINT_RE.finditer(page.text)})[:80]
        (outdir / f"{host}.hints.txt").write_text("\n".join(hints), encoding="utf-8")
        print(f"{url}: HTTP {page.status}, {len(page.text)} bytes, {len(hints)} URL hints")
        emit(url, page.status, page.text, hints)


if __name__ == "__main__":
    main(sys.argv[1:])
