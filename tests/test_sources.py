import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend import sources, neural

def test_parse_tags():
    t = "[SubsPlease] Frieren - 12 (1080p) [ABCDEF12].mkv"
    tags = sources.parse_tags(t)
    assert tags["resolution"] == "1080p"
    assert tags["group"] == "SubsPlease"
    assert tags["episode"] == 12
    assert tags["batch"] is False

def test_parse_batch():
    t = "[Judas] Vinland Saga S2 (BD 1080p) [Batch] [HEVC x265 10bit][FLAC]"
    tags = sources.parse_tags(t)
    assert tags["batch"] is True
    assert tags["codec"] in ("x265", "hevc")

def test_size():
    assert sources.size_to_bytes("1.5 GiB") > 1_500_000_000
    assert sources.size_to_bytes("700 MiB") > 700_000_000

def test_ranker_ranks_trusted_first():
    r = neural.Ranker(trusted_groups=["SubsPlease"])
    A = {"title": "[SubsPlease] Frieren 12 1080p", "resolution": "1080p",
         "group": "SubsPlease", "seeders": 100, "size_bytes": 1_500_000_000}
    B = {"title": "[Junk] Frieren 12 480p", "resolution": "480p",
         "group": "Junk", "seeders": 1, "size_bytes": 200_000_000}
    ranked = r.rank([B, A], "Frieren")
    assert ranked[0] is A  # trusted/1080p > untrusted/480p

def test_ranker_learns_over_time():
    """Repeatedly teaching A as positive should keep A ranked above B."""
    r = neural.Ranker(trusted_groups=[], lr=0.2)
    A = {"title": "[GroupX] foo 1080p HEVC", "resolution": "1080p",
         "group": "GroupX", "seeders": 30, "size_bytes": 1_400_000_000, "codec": "x265"}
    B = {"title": "[Other] foo 720p", "resolution": "720p",
         "group": "Other", "seeders": 8, "size_bytes": 700_000_000, "codec": "x264"}
    for _ in range(20):
        r.teach(A, [A, B], "foo")
    assert r.score(A, "foo") > r.score(B, "foo")

def test_ranker_persists(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(neural, "CACHE", tmp_path / "nn.json")
    r = neural.Ranker(lr=0.1)
    A = {"title": "x", "resolution": "1080p", "group": "g", "seeders": 5, "size_bytes": 1_000_000_000}
    r.teach(A, [A], "x")
    assert (tmp_path / "nn.json").exists()
    data = json.loads((tmp_path / "nn.json").read_text())
    assert data["history"] and "weights" in data
