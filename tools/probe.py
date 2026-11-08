"""Fetch a few pages politely and save raw HTML + API-looking URLs for adapter writing.
Usage: python tools/probe.py URL [URL ...]   (run from the repo root)"""
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from feis_master.http import Client, Disallowed  # noqa: E402

out = Path("probe_out")
out.mkdir(exist_ok=True)
client = Client(cache_dir=".cache/probe")
hint_re = re.compile(r"""["'(](https?://[^"'()\s]+|/[^"'()\s]*)(api|json|graphql|ajax|feis)[^"'()\s]*""", re.I)

for url in sys.argv[1:]:
    host = urlparse(url).netloc.replace(":", "_")
    try:
        page = client.get(url)
    except Disallowed:
        print(f"{url}: disallowed by robots.txt - skipping")
        continue
    except Exception as e:
        print(f"{url}: {e}")
        continue
    (out / f"{host}.html").write_text(page.text, encoding="utf-8")
    hints = sorted({m.group(0)[1:] for m in hint_re.finditer(page.text)})[:80]
    (out / f"{host}.hints.txt").write_text("\n".join(hints), encoding="utf-8")
    print(f"{url}: HTTP {page.status}, {len(page.text)} bytes, {len(hints)} URL hints")
