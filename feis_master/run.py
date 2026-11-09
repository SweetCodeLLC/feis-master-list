"""Entry point: python -m feis_master.run [--only NAME] [--data-dir data] [--config config/sources.yml]

Each adapter writes its own snapshot (data/sources/<name>.json) only on success, so a
broken or blocked source never wipes earlier data. The master list is rebuilt from
all snapshots every run.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

import yaml

from .adapters import REGISTRY
from .adapters.base import NotConfigured
from .http import Client
from .ids import match_quickfeis, parse_quickfeis_catalog
from .merge import merge
from .schema import Feis

CSV_FIELDS = ["name", "start_date", "end_date", "venue", "address", "city", "state",
              "country", "region", "host", "website", "registration_links", "platform_ids", "sources"]


def load_snapshot(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return {str(r.get("source_id") or r["name"]): r for r in data}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/sources.yml")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--only")
    ap.add_argument("--cache-dir", default=".cache/http")
    args = ap.parse_args(argv)

    cfg = yaml.safe_load(Path(args.config).read_text())
    data = Path(args.data_dir)
    (data / "sources").mkdir(parents=True, exist_ok=True)
    client = Client(min_delay=float(cfg.get("min_delay_seconds", 1.5)), cache_dir=args.cache_dir)

    status: dict[str, str] = {}
    priorities: dict[str, int] = {}
    for name, sc in cfg["sources"].items():
        if args.only and name != args.only:
            continue
        priorities[name] = int(sc.get("priority", 50))
        if not sc.get("enabled", False):
            status[name] = "disabled"
            continue
        adapter_cls = REGISTRY[sc["adapter"]]
        adapter = adapter_cls(name, priorities[name], sc)
        snap_path = data / "sources" / f"{name}.json"
        prev = load_snapshot(snap_path)
        try:
            recs = adapter.fetch(client, prev)
        except NotConfigured as e:
            status[name] = f"skipped: {e}"
            continue
        except Exception as e:          # keep last good snapshot
            status[name] = f"FAILED ({type(e).__name__}): {e} - kept previous snapshot"
            continue
        floor = int(len(prev) * float(cfg.get("min_fraction_of_previous", 0.5)))
        if prev and len(recs) < floor:
            status[name] = f"FAILED: only {len(recs)} records vs {len(prev)} before - kept previous snapshot"
            continue
        snap_path.write_text(json.dumps([r.to_dict() for r in recs], indent=1, sort_keys=True) + "\n")
        status[name] = f"ok: {len(recs)} records" + "".join(f" [warning: {w}]" for w in adapter.warnings)

    # rebuild master from every snapshot on disk
    allrecs: list[tuple[int, Feis]] = []
    undated: list[dict] = []
    for p in sorted((data / "sources").glob("*.json")):
        name = p.stem
        prio = priorities.get(name, int(cfg["sources"].get(name, {}).get("priority", 50)))
        for r in json.loads(p.read_text()):
            f = Feis.from_dict(r)
            if f.start_date:
                allrecs.append((prio, f))
            else:
                undated.append(r)

    today = dt.date.today().isoformat()
    master = [f for f in merge(allrecs) if (f.end_date or f.start_date) >= today]

    # per-feis platform ids (QuickFeis catalog); a failed fetch keeps the previous catalog file
    cat_path = data / "platform_feises.json"
    catalog = json.loads(cat_path.read_text()) if cat_path.exists() else {}
    qcfg = cfg.get("platform_catalogs", {}).get("quickfeis", {})
    if qcfg.get("enabled"):
        try:
            page = client.get(qcfg["url"])
            fresh = parse_quickfeis_catalog(page.text) if page.status == 200 else []
            if fresh and len(fresh) >= 0.5 * len(catalog.get("quickfeis", [])):
                catalog["quickfeis"] = fresh
                cat_path.write_text(json.dumps(catalog, indent=1, sort_keys=True) + "\n")
                status["quickfeis_catalog"] = f"ok: {len(fresh)} feiseanna"
            else:
                status["quickfeis_catalog"] = "FAILED: empty or much smaller list - kept previous catalog"
        except Exception as e:
            status["quickfeis_catalog"] = f"FAILED ({type(e).__name__}): {e} - kept previous catalog"
    matched = match_quickfeis(master, catalog.get("quickfeis", []))
    if qcfg.get("enabled"):
        status["quickfeis_catalog"] += f"; matched {matched} of {sum(1 for f in master if 'quickfeis' in f.registration_links)} QuickFeis events"

    out = {"count": len(master), "feiseanna": [f.to_dict() for f in master]}
    (data / "feiseanna.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    (data / "undated.json").write_text(json.dumps(undated, indent=1, sort_keys=True) + "\n")
    with open(data / "feiseanna.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        w.writeheader()
        for f in master:
            d = f.to_dict()
            d["platform_ids"] = "; ".join(f"{k}={v}" for k, v in sorted(f.platform_ids.items()))
            d["registration_links"] = "; ".join(f"{k}={v}" for k, v in sorted(f.registration_links.items()))
            d["sources"] = "; ".join(s["source"] for s in f.sources)
            w.writerow({k: d.get(k) for k in CSV_FIELDS})

    print(f"master list: {len(master)} upcoming feiseanna ({len(undated)} undated items held back)")
    for k, v in status.items():
        print(f"  {k}: {v}")
    # Fail the job only if an enabled source failed AND there was nothing to fall back on.
    hard = [k for k, v in status.items() if v.startswith("FAILED") and not (data / "sources" / f"{k}.json").exists()]
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
