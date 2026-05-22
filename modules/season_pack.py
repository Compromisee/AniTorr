import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend import sources

def run(title="", season=1):
    cfg = json.loads((ROOT/"config.json").read_text())
    q = f"{title} S{int(season):02d} batch 1080p"
    rows = sources.aggregate(q, cfg["sources"], cfg.get("cors_proxy_url"), cfg["ddl_sources"])
    rows = [r for r in rows if r.get("batch") and r.get("resolution")=="1080p"]
    rows.sort(key=lambda r: r.get("size_bytes", 1<<60))
    return [{"title": r["title"], "size_bytes": r["size_bytes"],
             "seeders": r.get("seeders",0), "magnet": r.get("magnet","")} for r in rows[:10]]
