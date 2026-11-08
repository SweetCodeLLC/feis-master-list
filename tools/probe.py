"""Fetch a few pages politely, save raw HTML + API-looking URLs, and ALSO print what is
needed to write an adapter into the run log (so no artifact download is required).

Usage: python tools/probe.py URL [URL ...]   (run from the repo root)

Small pages are printed in full; large pages get the first chunk plus a structural
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
HEAD_CHARS = 12_000      # otherwise print this much from the start
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


def emit(url: str, status: int, html: str, hints: list[str]) -> None:
    out(f"===== BEGIN {url} (HTTP {status}, {len(html)} chars) =====")
    block("URL hints", "\n".join(hints) or "(none)")
    if len(html) <= FULL_LIMIT:
        block("full HTML", html)
    else:
        block(f"first {HEAD_CHARS} chars", html[:HEAD_CHARS])
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
