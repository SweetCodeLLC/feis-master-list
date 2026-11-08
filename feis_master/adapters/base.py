from __future__ import annotations

from ..http import Client
from ..schema import Feis


class NotConfigured(Exception):
    """Adapter is a scaffold, or is gated (e.g. awaiting written consent)."""


class Adapter:
    name = "base"

    def __init__(self, name: str, priority: int, cfg: dict):
        self.name = name
        self.priority = priority
        self.cfg = cfg
        self.warnings: list[str] = []

    def fetch(self, client: Client, previous: dict[str, dict]) -> list[Feis]:
        """Return records. `previous` maps source_id -> last saved record dict so
        adapters can skip refetching long-past events."""
        raise NotImplementedError
