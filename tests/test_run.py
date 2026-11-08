import json
from pathlib import Path

import yaml

from feis_master import run as runmod
from feis_master.http import FetchError, Page
from tests.test_parsers import FEISWORX_HTML, IDTANA_HTML

CFG = {
    "min_fraction_of_previous": 0.5,
    "sources": {
        "idtana": {"adapter": "idtana", "enabled": True, "priority": 10},
        "feisworx": {"adapter": "feisworx", "enabled": True, "priority": 20,
                     "url": "https://www.feisworx.com/feisinfo.php"},
        "quickfeis": {"adapter": "quickfeis", "enabled": False, "priority": 40},
    },
}


def fake_get_factory(fail_feisworx=False):
    rest = [{"id": 1, "link": "https://idtana.org/events/st-ambrose/", "title": {"rendered": "St. Ambrose Fall Feis 2026"}}]

    def fake_get(self, url):
        if "wp-json" in url:
            return Page(url, 200, json.dumps(rest), {"X-WP-TotalPages": "1"})
        if url.startswith("https://idtana.org/events/"):
            return Page(url, 200, IDTANA_HTML)
        if "feisworx" in url:
            if fail_feisworx:
                raise FetchError("boom")
            return Page(url, 200, FEISWORX_HTML)
        raise AssertionError(url)
    return fake_get


def test_end_to_end_and_failure_keeps_snapshot(tmp_path, monkeypatch):
    cfg = tmp_path / "sources.yml"
    cfg.write_text(yaml.safe_dump(CFG))
    data = tmp_path / "data"
    # freeze "today" before the fixtures' dates
    import datetime as dt
    class D(dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 1)
    monkeypatch.setattr(runmod.dt, "date", D)
    from feis_master.adapters import idtana
    monkeypatch.setattr(idtana.dt, "date", D)

    monkeypatch.setattr("feis_master.http.Client.get", fake_get_factory())
    args = ["--config", str(cfg), "--data-dir", str(data), "--cache-dir", str(tmp_path / "c")]
    assert runmod.main(args) == 0
    master = json.loads((data / "feiseanna.json").read_text())
    names = [f["name"] for f in master["feiseanna"]]
    assert "St. Ambrose Fall Feis 2026" in names and "Feis On The Gulf 2027" in names
    assert (data / "feiseanna.csv").exists()
    assert (data / "sources" / "feisworx.json").exists()

    # second run: FeisWorx fails -> previous snapshot is kept, master still has its events
    monkeypatch.setattr("feis_master.http.Client.get", fake_get_factory(fail_feisworx=True))
    assert runmod.main(args) == 0
    master2 = json.loads((data / "feiseanna.json").read_text())
    assert "Feis On The Gulf 2027" in [f["name"] for f in master2["feiseanna"]]
