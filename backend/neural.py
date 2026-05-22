"""
Tiny online-learning ranker.  Not a deep net — a single-layer logistic regression
with hand-engineered features.  Persists weights + history to data/nn_cache.json.

When the user picks a torrent, we treat it as a positive example; the other top-N
shown are negatives.  Each new pick nudges the weights by `learning_rate`.
"""
from __future__ import annotations
import json, math, os, time, hashlib
from pathlib import Path
from typing import List, Dict

CACHE = Path(__file__).resolve().parent.parent / "data" / "nn_cache.json"

DEFAULT_WEIGHTS = {
    "seeders": 1.0, "resolution": 1.2, "group_trust": 1.5,
    "size_efficiency": 0.8, "prompt_match": 2.0, "codec": 0.6, "batch": 0.4,
    "bias": -0.5,
}

class Ranker:
    def __init__(self, trusted_groups=None, lr: float = 0.05):
        self.trusted = set((trusted_groups or []))
        self.lr = lr
        self.weights = dict(DEFAULT_WEIGHTS)
        self.history: List[Dict] = []
        self._load()

    # --- persistence ---
    def _load(self):
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        if CACHE.exists():
            try:
                data = json.loads(CACHE.read_text())
                self.weights.update(data.get("weights", {}))
                self.history = data.get("history", [])
            except Exception: pass

    def _save(self):
        CACHE.write_text(json.dumps(
            {"weights": self.weights, "history": self.history[-500:]}, indent=2))

    # --- features ---
    def features(self, torrent: Dict, query: str) -> Dict[str, float]:
        title = (torrent.get("title") or "").lower()
        q = (query or "").lower()
        q_tokens = [t for t in q.split() if t]
        match = sum(1 for t in q_tokens if t in title) / max(len(q_tokens), 1)

        res_map = {"2160p": 1.0, "1080p": 0.8, "720p": 0.5, "480p": 0.25, "": 0.1}
        res = res_map.get(torrent.get("resolution", ""), 0.1)

        seeders = math.log1p(torrent.get("seeders", 0)) / 8.0
        trust = 1.0 if torrent.get("group", "") in self.trusted else 0.2

        size = torrent.get("size_bytes", 0)
        # efficiency: smaller for same resolution = better
        size_eff = 1.0 - min(size / (3 * 1024**3), 1.0) if res >= 0.8 else 0.5

        codec = 1.0 if torrent.get("codec","") in ("x265","hevc","h265","av1") else 0.5
        batch = 1.0 if torrent.get("batch") else 0.0

        return {
            "seeders": seeders, "resolution": res, "group_trust": trust,
            "size_efficiency": size_eff, "prompt_match": match,
            "codec": codec, "batch": batch,
        }

    def score(self, torrent: Dict, query: str) -> float:
        f = self.features(torrent, query)
        s = self.weights.get("bias", 0.0)
        for k, v in f.items():
            s += self.weights.get(k, 0.0) * v
        return s

    def rank(self, torrents: List[Dict], query: str) -> List[Dict]:
        scored = sorted(torrents,
                        key=lambda t: self.score(t, query),
                        reverse=True)
        for i, t in enumerate(scored):
            t["nn_score"] = round(self.score(t, query), 3)
            t["nn_rank"] = i + 1
        return scored

    # --- learning ---
    def teach(self, picked: Dict, shown: List[Dict], query: str):
        """Single SGD step toward `picked` and away from the others."""
        for t in shown:
            label = 1.0 if t is picked or t.get("title") == picked.get("title") else 0.0
            f = self.features(t, query)
            z = self.weights.get("bias", 0.0) + sum(self.weights.get(k,0)*v for k,v in f.items())
            pred = 1.0 / (1.0 + math.exp(-z))
            err = label - pred
            for k, v in f.items():
                self.weights[k] = self.weights.get(k, 0.0) + self.lr * err * v
            self.weights["bias"] = self.weights.get("bias", 0.0) + self.lr * err
        self.history.append({
            "ts": int(time.time()), "query": query,
            "title": picked.get("title"), "source": picked.get("source"),
            "group": picked.get("group"), "resolution": picked.get("resolution"),
        })
        self._save()

    def stats(self) -> Dict:
        return {
            "samples": len(self.history),
            "weights": self.weights,
            "recent": self.history[-10:],
        }
