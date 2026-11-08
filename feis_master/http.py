"""Polite HTTP client: identifying User-Agent, robots.txt, per-host rate limit,
retry/backoff (honors Retry-After), and conditional GET with an on-disk cache."""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.robotparser
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import requests


class FetchError(Exception):
    pass


class Disallowed(Exception):
    """robots.txt forbids this URL for our User-Agent."""


@dataclass
class Page:
    url: str
    status: int
    text: str
    headers: dict = field(default_factory=dict)
    from_cache: bool = False


def default_user_agent() -> str:
    contact = os.environ.get("FEIS_CONTACT", "").strip()
    if not contact:
        contact = "set FEIS_CONTACT"
    return f"feis-master-list/0.1 (+{contact})"


class Client:
    def __init__(self, user_agent: str | None = None, min_delay: float = 1.5,
                 cache_dir: str | Path = ".cache/http", respect_robots: bool = True,
                 timeout: int = 30, max_retries: int = 3):
        self.ua = user_agent or default_user_agent()
        self.min_delay = min_delay
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.respect_robots = respect_robots
        self.timeout = timeout
        self.max_retries = max_retries
        self.s = requests.Session()
        self.s.headers["User-Agent"] = self.ua
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._sitemaps: dict[str, list[str]] = {}

    # ------------------------------------------------------------ internals
    def _wait(self, host: str) -> None:
        gap = time.monotonic() - self._last.get(host, 0.0)
        if gap < self.min_delay:
            time.sleep(self.min_delay - gap)
        self._last[host] = time.monotonic()

    def _robots_for(self, url: str):
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base in self._robots:
            return self._robots[base]
        rp = None
        try:
            self._wait(p.netloc)
            r = self.s.get(base + "/robots.txt", timeout=self.timeout)
            if r.status_code == 200:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(r.text.splitlines())
                self._sitemaps[base] = [ln.split(":", 1)[1].strip() for ln in r.text.splitlines()
                                        if ln.lower().startswith("sitemap:")]
            # 404 or other non-200: no robots rules -> everything allowed
        except requests.RequestException:
            rp = None
        self._robots[base] = rp
        return rp

    def sitemaps(self, base_url: str) -> list[str]:
        p = urlparse(base_url)
        base = f"{p.scheme}://{p.netloc}"
        self._robots_for(base + "/")
        return self._sitemaps.get(base, [])

    def _cache_paths(self, url: str) -> tuple[Path, Path]:
        h = hashlib.sha256(url.encode()).hexdigest()[:40]
        return self.cache_dir / f"{h}.body", self.cache_dir / f"{h}.json"

    # ------------------------------------------------------------ public
    def get(self, url: str) -> Page:
        if self.respect_robots:
            rp = self._robots_for(url)
            if rp is not None and not rp.can_fetch(self.ua, url):
                raise Disallowed(url)
        body_p, meta_p = self._cache_paths(url)
        headers = {}
        if body_p.exists() and meta_p.exists():
            meta = json.loads(meta_p.read_text())
            if meta.get("etag"):
                headers["If-None-Match"] = meta["etag"]
            if meta.get("last_modified"):
                headers["If-Modified-Since"] = meta["last_modified"]

        host = urlparse(url).netloc
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            self._wait(host)
            try:
                r = self.s.get(url, headers=headers, timeout=self.timeout)
            except requests.RequestException as e:
                last_exc = e
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 304 and body_p.exists():
                return Page(url, 200, body_p.read_text(encoding="utf-8"),
                            dict(r.headers), from_cache=True)
            if r.status_code in (429, 500, 502, 503, 504):
                try:
                    delay = float(r.headers.get("Retry-After", ""))
                except ValueError:
                    delay = 2 ** (attempt + 1)
                last_exc = FetchError(f"{r.status_code} from {url}")
                time.sleep(min(delay, 60))
                continue
            if r.status_code == 200:
                r.encoding = r.encoding or "utf-8"
                body_p.write_text(r.text, encoding="utf-8")
                meta_p.write_text(json.dumps({
                    "etag": r.headers.get("ETag"),
                    "last_modified": r.headers.get("Last-Modified"),
                }))
            return Page(url, r.status_code, r.text, dict(r.headers))
        raise FetchError(f"giving up on {url}: {last_exc}")
