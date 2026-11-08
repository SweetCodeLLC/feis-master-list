"""Scaffolds for registration platforms whose markup could not be inspected yet.

iFeis and FeisWeb: no parser is written blind. (QuickFeis has its own adapter.) Run the 'probe' workflow (it saves the raw
listing pages as an artifact), then implement `fetch` against the real HTML.

Until then, links to these platforms still appear in the master list: IDTANA
event pages carry each feis's registration link, and the merge step records it.
"""
from __future__ import annotations

from ..http import Client
from ..schema import Feis
from .base import Adapter, NotConfigured


class IFeisAdapter(Adapter):
    """iFeis's Find a Feis list is JavaScript-rendered: look for the JSON/XHR
    endpoint in the probe's network capture before reaching for a headless browser."""

    def fetch(self, client: Client, previous: dict[str, dict]) -> list[Feis]:
        raise NotConfigured("ifeis: parser not written yet - run the probe workflow first")


class FeisWebAdapter(Adapter):
    """FeisWeb's terms forbid reproducing or redistributing content without written
    consent. This adapter refuses to run unless config sets written_consent: true."""

    def fetch(self, client: Client, previous: dict[str, dict]) -> list[Feis]:
        if not self.cfg.get("written_consent"):
            raise NotConfigured("feisweb: needs written consent from FeisWeb (see README)")
        raise NotConfigured("feisweb: consent recorded, but parser not written yet")
