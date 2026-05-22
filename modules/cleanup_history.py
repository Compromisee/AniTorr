import json
from pathlib import Path
def run(keep=100):
    p = Path(__file__).resolve().parent.parent / "data" / "nn_cache.json"
    if not p.exists(): return "no cache"
    d = json.loads(p.read_text())
    d["history"] = d.get("history", [])[-int(keep):]
    p.write_text(json.dumps(d, indent=2))
    return f"trimmed → {len(d['history'])} entries"
