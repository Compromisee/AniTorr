"""
ANITorr Flask backend.

  GET  /                                      → dashboard
  GET  /api/search?q=...&res=...&lang=...     → JSON ranked list
  GET  /api/search/stream?q=...               → SSE live stream
  POST /api/pick                              → train ranker on a chosen torrent
  GET  /api/meta?q=...                        → AniList + MAL metadata
  GET  /api/autocomplete?q=...                → title suggestions
  GET  /api/torrent_files?url=...             → list files inside a .torrent (approx)
  POST /api/download                          → push to qbit / file / magnet
  GET  /api/stats                             → ranker stats
  GET/POST /api/config                        → read/update settings
  GET  /api/modules                           → list .module blocks
  POST /api/modules/run                       → run a module
  POST /api/notify/test                       → fire a discord/ntfy/telegram test
"""
from __future__ import annotations
import json, os, time, threading, queue
from pathlib import Path
from flask import Flask, request, jsonify, Response, send_from_directory, render_template
from flask_cors import CORS
from cachetools import TTLCache

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
DATA_DIR = ROOT / "data"; DATA_DIR.mkdir(exist_ok=True)
DOWNLOADS = ROOT / "downloads"; DOWNLOADS.mkdir(exist_ok=True)

import sys
sys.path.insert(0, str(ROOT))
from backend import sources, neural, metadata, clients, notify, interpreter

def load_cfg():
    return json.loads(CONFIG_PATH.read_text())
def save_cfg(c):
    CONFIG_PATH.write_text(json.dumps(c, indent=2))

cfg = load_cfg()
ranker = neural.Ranker(trusted_groups=cfg.get("trusted_groups", []),
                       lr=cfg["neural_network"]["learning_rate"])
search_cache = TTLCache(maxsize=512, ttl=cfg.get("cache_ttl_seconds", 600))

app = Flask(__name__,
            template_folder=str(ROOT / "frontend" / "templates"),
            static_folder=str(ROOT / "frontend" / "static"))
CORS(app)

# ---------- pages ----------
@app.route("/")
def index():
    return render_template("index.html", cfg=cfg, active_tab="dashboard")

@app.route("/settings")
def settings_page():
    return render_template("settings.html", cfg=cfg, active_tab="settings")

@app.route("/stats")
def stats_page():
    return render_template("stats.html", cfg=cfg, stats=ranker.stats(), active_tab="stats")

@app.route("/modules")
def modules_page():
    mods = [m.raw | {"file": m.path.name} for m in interpreter.discover()]
    return render_template("modules.html", cfg=cfg, modules=mods, active_tab="modules")

# ====================== category browse / library pages ======================

# Pre-baked browse categories — each one maps to a saved query / filter set.
BROWSE_CATEGORIES = {
    # key: (title, description, default_query, filters)
    "seasonal":         ("Seasonal anime",      "Currently airing season releases.",     "anime 2026 ongoing",   {}),
    "movies":           ("Anime movies",        "Theatrical and OVA releases.",          "anime movie 1080p",    {}),
    "watch-later":      ("Watch later",         "Saved for later viewing.",              "",                      {"_kind": "favorites"}),
    "backlog":          ("Backlog",             "Older shows you mean to finish.",       "",                      {"_kind": "history"}),
    "batch":            ("Batch / Season packs","Complete season packs.",                "anime batch complete",  {"batch": True}),
    "audio-flac":       ("OSTs · FLAC",         "Lossless soundtrack rips.",             "anime ost flac",        {}),
    "audio-mp3":        ("OSTs · MP3",          "Compressed soundtrack rips.",           "anime ost mp3",         {}),
    "picks-by-user":    ("Picks by user",       "What you have personally chosen.",      "",                      {"_kind": "picks"}),
    "download-duration":("Download duration",   "How long your past downloads took.",    "",                      {"_kind": "download_duration"}),
    "downloads":        ("Download history",    "All previous downloads.",               "",                      {"_kind": "downloads"}),
    "searches":         ("Searches",            "Every query you have run.",             "",                      {"_kind": "searches"}),
}
@app.route("/browse/<category>")
def browse_page(category):
    info = BROWSE_CATEGORIES.get(category)
    if not info:
        return render_template("browse.html", cfg=cfg, active_tab="dashboard",
                               title="Not found", description="Unknown category.",
                               category="", default_query="", filters={}), 404
    title, desc, q, filters = info
    return render_template("browse.html", cfg=cfg, active_tab="dashboard",
                           title=title, description=desc, category=category,
                           default_query=q, filters=filters)

@app.route("/favorites")
def favorites_page():
    return render_template("favorites.html", cfg=cfg, active_tab="favorites",
                           favorites=_read(FAV_PATH))

@app.route("/recent")
def recent_page():
    return render_template("recent.html", cfg=cfg, active_tab="recent",
                           history=_read(HIST_PATH))

@app.route("/downloads")
def downloads_page():
    items = []
    if DOWNLOADS.exists():
        for f in sorted(DOWNLOADS.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if not f.is_file(): continue
            items.append({
                "name": f.name,
                "size": f.stat().st_size,
                "mtime": int(f.stat().st_mtime),
                "type": "magnet" if f.suffix == ".magnet" else ("torrent" if f.suffix == ".torrent" else "other"),
            })
    return render_template("downloads.html", cfg=cfg, active_tab="downloads", items=items)

# ====================== analytics endpoints ======================

@app.route("/api/analytics/summary")
def api_analytics_summary():
    hist = _read(HIST_PATH)
    favs = _read(FAV_PATH)
    # tally
    by_group = {}
    by_res = {}
    by_source = {}
    timeline = {}
    for h in hist:
        g = h.get("group") or "—"
        r = h.get("resolution") or "—"
        s = h.get("source") or "—"
        by_group[g] = by_group.get(g, 0) + 1
        by_res[r]   = by_res.get(r, 0) + 1
        by_source[s]= by_source.get(s, 0) + 1
        # daily timeline
        if h.get("ts"):
            day = time.strftime("%Y-%m-%d", time.localtime(h["ts"]))
            timeline[day] = timeline.get(day, 0) + 1
    return jsonify({
        "samples": len(hist),
        "favorites": len(favs),
        "by_group": by_group,
        "by_resolution": by_res,
        "by_source": by_source,
        "timeline": timeline,
        "last": hist[-1] if hist else None,
    })

@app.route("/api/analytics/downloads")
def api_analytics_downloads():
    items = []
    if DOWNLOADS.exists():
        for f in sorted(DOWNLOADS.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if not f.is_file(): continue
            items.append({
                "name": f.name,
                "size": f.stat().st_size,
                "mtime": int(f.stat().st_mtime),
                "type": "magnet" if f.suffix == ".magnet" else ("torrent" if f.suffix == ".torrent" else "other"),
            })
    return jsonify(items)

@app.route("/api/downloads/delete", methods=["POST"])
def api_downloads_delete():
    name = (request.get_json(force=True) or {}).get("name","")
    p = DOWNLOADS / name
    if p.exists() and p.is_file() and p.parent == DOWNLOADS:
        p.unlink()
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error":"not found"}), 404


# ---------- search ----------
import re as _re, unicodedata as _ud

# Detect titles that are mostly non-Latin / unrelated (Russian, Arabic, etc. when
# the user typed an English title). We *don't* drop CJK by default because many
# valid releases include kanji/hiragana for the show name.
_LATIN_RE = _re.compile(r"[A-Za-z0-9]")
_CJK_RE   = _re.compile(r"[\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]")

def _tokenize(s: str):
    s = _ud.normalize("NFKD", s or "").lower()
    return [t for t in _re.split(r"[^a-z0-9]+", s) if len(t) >= 2]

def _relevant(query: str, title: str, query_tokens=None) -> bool:
    """Reject results that share no meaningful token with the query and contain
    no CJK characters either. Releases tagged in unrelated languages typically
    fall into this bucket."""
    if not title: return False
    qt = query_tokens if query_tokens is not None else set(_tokenize(query))
    tt = set(_tokenize(title))
    overlap = qt & tt
    if overlap:
        return True
    # Title may be a JP/CN/KR rendition – allow if it has CJK characters AND
    # the user used a single-word romaji query (the matching is hard either way)
    if _CJK_RE.search(title) and len(qt) <= 3:
        return True
    # If title has no Latin chars at all (e.g. pure Cyrillic / Arabic) and no
    # CJK either, it's almost certainly an unrelated dub. Drop it.
    if not _LATIN_RE.search(title):
        return False
    # Otherwise require at least one query token to appear
    return False

def _nn_quality(ranked, query):
    """Heuristic: if the top-10 NN results have <30% token overlap with the
    query, fall back to a plain seeder-sorted view of the same results filtered
    by relevance."""
    if not ranked: return 0.0
    qt = set(_tokenize(query))
    if not qt: return 1.0
    hits = sum(1 for r in ranked[:10]
               if qt & set(_tokenize(r.get("title",""))))
    return hits / min(10, len(ranked))

def _search(query: str, want_res: str = "", lang: str = "", group: str = ""):
    key = (query, want_res, lang, group)
    if key in search_cache: return search_cache[key]

    meta = metadata.anilist_lookup(query) if cfg["plugins"]["anilist_meta"] else None
    variants = metadata.title_variants(query, meta)
    if cfg["plugins"]["ai_title_norm"]:
        variants += metadata.ai_normalize(query, cfg["ai"])
    variants = list(dict.fromkeys(variants))[:5]

    all_results = []
    for v in variants:
        all_results += sources.aggregate(
            v, cfg["sources"], cfg.get("cors_proxy_url"),
            cfg["ddl_sources"], cfg.get("aggregator_threshold", 5),
            cfg.get("max_threads", 12))

    # ---- relevance gate (drop unrelated-language releases) ----
    if cfg.get("plugins", {}).get("relevance_filter", True):
        all_tokens = set(_tokenize(query))
        for v in variants:
            all_tokens |= set(_tokenize(v))
        before = len(all_results)
        all_results = [r for r in all_results
                       if _relevant(query, r.get("title",""), all_tokens)]
        log_event(f"relevance filter: {before} -> {len(all_results)} (q={query!r})")

    # ---- user filters ----
    if want_res:
        all_results = [r for r in all_results
                       if r.get("resolution","") == want_res or not r.get("resolution")]
    if group:
        all_results = [r for r in all_results
                       if group.lower() in (r.get("group","") or "").lower()]

    # ---- rank: NN first, fall back to plain if quality too low ----
    ranked = ranker.rank(all_results, query)
    quality = _nn_quality(ranked, query)
    used_fallback = False
    if quality < 0.3 and ranked:
        log_event(f"NN quality {quality:.2f} too low — falling back to seeder sort")
        used_fallback = True
        ranked = sorted(all_results,
                        key=lambda r: (r.get("seeders", 0),
                                       1 if r.get("resolution") == "1080p" else 0),
                        reverse=True)
        for i, r in enumerate(ranked):
            r["nn_rank"] = i + 1

    out = {"meta": meta, "variants": variants, "results": ranked[:200],
           "nn_quality": quality, "fallback": used_fallback}
    search_cache[key] = out
    return out

@app.route("/api/search")
def api_search():
    q = request.args.get("q","").strip()
    if not q: return jsonify({"error":"missing q"}), 400
    return jsonify(_search(q,
        request.args.get("res",""), request.args.get("lang",""),
        request.args.get("group","")))

@app.route("/api/search/stream")
def api_search_stream():
    q = request.args.get("q","").strip()
    res = request.args.get("res",""); group = request.args.get("group","")
    def gen():
        yield f"data: {json.dumps({'event':'start','q':q})}\n\n"
        meta = metadata.anilist_lookup(q) if cfg["plugins"]["anilist_meta"] else None
        yield f"data: {json.dumps({'event':'meta','meta':meta})}\n\n"
        variants = metadata.title_variants(q, meta)
        for name, fn in sources.SOURCES.items():
            if not cfg["sources"].get(name, True): continue
            try:
                rows = fn(variants[0] if variants else q,
                          cors_proxy=cfg.get("cors_proxy_url"))
            except Exception: rows = []
            ranked = ranker.rank(rows, q)
            yield f"data: {json.dumps({'event':'batch','source':name,'rows':ranked})}\n\n"
        yield f"data: {json.dumps({'event':'done'})}\n\n"
    return Response(gen(), mimetype="text/event-stream")

@app.route("/api/pick", methods=["POST"])
def api_pick():
    body = request.get_json(force=True)
    picked, shown, q = body["picked"], body.get("shown", []), body.get("query","")
    ranker.teach(picked, shown, q)
    return jsonify({"ok": True, "stats": ranker.stats()})

# ---------- meta / autocomplete ----------
@app.route("/api/meta")
def api_meta():
    q = request.args.get("q","")
    return jsonify({
        "anilist": metadata.anilist_lookup(q),
        "mal": metadata.mal_lookup(q),
    })

@app.route("/api/autocomplete")
def api_autocomplete():
    return jsonify(metadata.autocomplete(request.args.get("q","")))

# ---------- torrent file inspection (approximation via page scrape) ----------
@app.route("/api/torrent_files")
def api_torrent_files():
    page = request.args.get("url","")
    if not page: return jsonify([])
    import requests as rq
    from bs4 import BeautifulSoup
    try:
        r = rq.get(page, timeout=15, headers={"User-Agent":"ANITorr/1.0"})
        soup = BeautifulSoup(r.text, "lxml")
        files = []
        for li in soup.select(".torrent-file-list li, .file-list li, ul li"):
            t = li.get_text(strip=True)
            if t and len(t) < 300 and ("." in t):
                files.append(t)
            if len(files) > 200: break
        return jsonify(files[:200])
    except Exception as e:
        return jsonify({"error": str(e)}), 200

# ---------- downloads ----------
@app.route("/api/download", methods=["POST"])
def api_download():
    body = request.get_json(force=True)
    mode = body.get("mode","qbit")   # qbit | deluge | transmission | file | magnet
    magnet = body.get("magnet","")
    url = body.get("torrent_url","")
    title = body.get("title","download")

    if mode == "qbit" and cfg["qbittorrent"]["enabled"]:
        q = cfg["qbittorrent"]
        c = clients.QBitClient(q["host"], q["user"], q["password"],
                               q["category"], q["save_path"])
        ok = c.add(magnet or url)
        return jsonify({"ok": ok})
    if mode == "file" and url:
        path = clients.save_torrent_file(url, str(DOWNLOADS))
        return jsonify({"ok": bool(path), "path": path})
    if mode == "magnet" and magnet:
        path = clients.magnet_to_file(magnet, str(DOWNLOADS),
                                      name=f"{title[:60]}.magnet")
        return jsonify({"ok": True, "path": path, "magnet": magnet})
    return jsonify({"ok": False, "error":"no actionable target"})

# ---------- stats / settings / modules ----------
@app.route("/api/stats")
def api_stats(): return jsonify(ranker.stats())

@app.route("/api/config", methods=["GET","POST"])
def api_config():
    global cfg, ranker, search_cache
    if request.method == "GET": return jsonify(cfg)
    new = request.get_json(force=True)
    cfg.update(new); save_cfg(cfg)
    ranker = neural.Ranker(trusted_groups=cfg.get("trusted_groups", []),
                           lr=cfg["neural_network"]["learning_rate"])
    search_cache = TTLCache(maxsize=512, ttl=cfg.get("cache_ttl_seconds", 600))
    return jsonify({"ok": True})

@app.route("/api/modules")
def api_modules():
    return jsonify([m.raw | {"file": m.path.name} for m in interpreter.discover()])

@app.route("/api/modules/run", methods=["POST"])
def api_modules_run():
    body = request.get_json(force=True)
    spec = interpreter.find(body.get("name",""))
    if not spec: return jsonify({"error":"not found"}), 404
    try:
        out = spec.call(**body.get("params", {}))
        return jsonify({"ok": True, "result": out})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/notify/test", methods=["POST"])
def api_notify_test():
    msg = "ANITorr test notification ✓"
    if cfg["discord_webhook"]["enabled"]:
        notify.discord(cfg["discord_webhook"]["url"], msg)
    if cfg["ntfy"]["enabled"]:
        notify.ntfy(cfg["ntfy"]["url"], cfg["ntfy"]["topic"], msg)
    if cfg["telegram"]["enabled"]:
        notify.telegram(cfg["telegram"]["token"], cfg["telegram"]["chat_id"], msg)
    return jsonify({"ok": True})

# ---------- favorites / history (simple JSON file store) ----------
HIST_PATH = DATA_DIR / "history.json"
FAV_PATH = DATA_DIR / "favorites.json"
def _read(p): return json.loads(p.read_text()) if p.exists() else []
def _write(p, d): p.write_text(json.dumps(d, indent=2))

@app.route("/api/history", methods=["GET","POST","DELETE"])
def api_history():
    if request.method == "GET": return jsonify(_read(HIST_PATH))
    if request.method == "DELETE": _write(HIST_PATH, []); return jsonify({"ok":True})
    h = _read(HIST_PATH); h.append({"ts":int(time.time()), **request.get_json(force=True)})
    _write(HIST_PATH, h[-300:]); return jsonify({"ok":True})

@app.route("/api/favorites", methods=["GET","POST","DELETE"])
def api_favorites():
    if request.method == "GET": return jsonify(_read(FAV_PATH))
    body = request.get_json(force=True)
    favs = _read(FAV_PATH)
    if request.method == "DELETE":
        favs = [f for f in favs if f.get("title") != body.get("title")]
    else:
        favs.append(body)
    _write(FAV_PATH, favs); return jsonify({"ok":True, "favorites":favs})


@app.route("/api/cache/clear", methods=["POST"])
def api_cache_clear():
    global search_cache
    from cachetools import TTLCache
    search_cache = TTLCache(maxsize=512, ttl=cfg.get("cache_ttl_seconds", 600))
    return jsonify({"ok": True})

@app.route("/api/qbit/test", methods=["POST"])
def api_qbit_test():
    q = cfg.get("qbittorrent", {})
    if not q.get("enabled"):
        return jsonify({"ok": False, "error": "qBittorrent disabled in settings"})
    try:
        c = clients.QBitClient(q["host"], q["user"], q["password"], q.get("category","anime"), q.get("save_path",""))
        ok = c.login()
        return jsonify({"ok": ok, "error": "" if ok else "login failed (check creds/host)"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/stats/reset", methods=["POST"])
def api_stats_reset():
    global ranker
    p = DATA_DIR / "nn_cache.json"
    if p.exists():
        p.unlink()
    ranker = neural.Ranker(trusted_groups=cfg.get("trusted_groups", []),
                           lr=cfg["neural_network"]["learning_rate"])
    return jsonify({"ok": True})


# ====================== MANGA SOURCES & DOWNLOADER ======================
from backend import manga_sources, manga_dl  # noqa
MANGA_DIR = ROOT / "manga"; MANGA_DIR.mkdir(exist_ok=True)

@app.route("/manga")
def manga_page():
    return render_template("manga.html", cfg=cfg, active_tab="manga",
                           sources=list(manga_sources.SOURCES.keys()))

@app.route("/manga/<source>/<path:slug>")
def manga_detail(source, slug):
    return render_template("manga_detail.html", cfg=cfg, active_tab="manga",
                           source=source, slug=slug)

@app.route("/api/manga/search")
def api_manga_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    enabled = cfg.get("manga_sources") or {n: True for n in manga_sources.SOURCES}
    rows = manga_sources.search_all(q, enabled)
    return jsonify(rows[:200])

@app.route("/api/manga/chapters")
def api_manga_chapters():
    src = request.args.get("source", "")
    url = request.args.get("url", "")
    return jsonify(manga_sources.get_chapters(src, url))

@app.route("/api/manga/pages")
def api_manga_pages():
    src = request.args.get("source", "")
    url = request.args.get("url", "")
    return jsonify(manga_sources.get_pages(src, url))

@app.route("/api/manga/download", methods=["POST"])
def api_manga_download():
    body = request.get_json(force=True)
    title = body.get("title", "")
    fmt = body.get("fmt", "cbz")
    pages = body.get("pages", [])
    src = body.get("source", "manual")
    author = body.get("author", "")
    series = body.get("series", "")
    autocrop = bool(body.get("autocrop", cfg.get("manga", {}).get("autocrop", False)))
    if not pages:
        return jsonify({"ok": False, "error": "no pages"})
    job_id = manga_dl.start_job(title=title or "untitled", source=src,
                                page_urls=pages, fmt=fmt, out_dir=MANGA_DIR,
                                author=author, series=series, autocrop=autocrop)
    push_notification(f"Started {fmt.upper()} export: {title}", kind="info",
                      link=f"/manga#job-{job_id}")
    return jsonify({"ok": True, "job_id": job_id})

@app.route("/api/manga/download/by-url", methods=["POST"])
def api_manga_download_url():
    body = request.get_json(force=True)
    url = body.get("url", "").strip()
    fmt = body.get("fmt", "cbz")
    title = body.get("title", "")
    autocrop = bool(body.get("autocrop", cfg.get("manga", {}).get("autocrop", False)))
    if not url:
        return jsonify({"ok": False, "error": "missing url"})
    try:
        job_id = manga_dl.download_by_url(url, fmt, MANGA_DIR,
                                          title=title, autocrop=autocrop)
        push_notification(f"Started URL download: {title or url}", kind="info")
        return jsonify({"ok": True, "job_id": job_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/manga/jobs")
def api_manga_jobs():
    return jsonify(manga_dl.list_jobs())

@app.route("/api/manga/job/<jid>")
def api_manga_job(jid):
    return jsonify(manga_dl.get_job(jid) or {"error": "not found"})

# ====================== NOTIFICATIONS ======================
NOTIF_PATH = DATA_DIR / "notifications.json"
def _read_notifs():
    if NOTIF_PATH.exists():
        try: return json.loads(NOTIF_PATH.read_text())
        except Exception: pass
    return []
def _write_notifs(arr):
    NOTIF_PATH.write_text(json.dumps(arr[-200:], indent=2))

def push_notification(message: str, kind: str = "info", link: str = ""):
    notifs = _read_notifs()
    notifs.append({
        "id": int(time.time() * 1000),
        "ts": int(time.time()),
        "message": message, "kind": kind, "link": link, "read": False,
    })
    _write_notifs(notifs)
    # Fan out to discord/ntfy/telegram if configured
    try:
        if cfg.get("discord_webhook", {}).get("enabled"):
            notify.discord(cfg["discord_webhook"]["url"], message)
        if cfg.get("ntfy", {}).get("enabled"):
            notify.ntfy(cfg["ntfy"]["url"], cfg["ntfy"]["topic"], message)
        if cfg.get("telegram", {}).get("enabled"):
            notify.telegram(cfg["telegram"]["token"], cfg["telegram"]["chat_id"], message)
    except Exception:
        pass

@app.route("/api/notifications")
def api_notifs():
    return jsonify(_read_notifs())

@app.route("/api/notifications/unread")
def api_notifs_unread():
    n = [x for x in _read_notifs() if not x.get("read")]
    return jsonify({"count": len(n), "items": n[-20:]})

@app.route("/api/notifications/read", methods=["POST"])
def api_notifs_read():
    body = request.get_json(silent=True) or {}
    items = _read_notifs()
    if body.get("all"):
        for it in items: it["read"] = True
    elif body.get("id"):
        for it in items:
            if it["id"] == body["id"]: it["read"] = True
    _write_notifs(items)
    return jsonify({"ok": True})

@app.route("/api/notifications", methods=["DELETE"])
def api_notifs_clear():
    _write_notifs([])
    return jsonify({"ok": True})

# ====================== HELP / DOCS / FAVICON ======================
@app.route("/help")
def help_page():
    return render_template("help.html", cfg=cfg, active_tab="help",
                           categories=BROWSE_CATEGORIES,
                           manga_sources=list(manga_sources.SOURCES.keys()))

@app.route("/notifications")
def notifications_page():
    return render_template("notifications.html", cfg=cfg, active_tab="notifications",
                           items=_read_notifs())

@app.route("/favicon.ico")
def favicon():
    return send_from_directory(str(ROOT / "frontend" / "static"),
                               "favicon.svg", mimetype="image/svg+xml")

@app.route("/api/dashboard/widgets", methods=["GET", "POST"])
def api_dashboard_widgets():
    p = DATA_DIR / "widgets.json"
    if request.method == "POST":
        body = request.get_json(force=True)
        p.write_text(json.dumps(body, indent=2))
        return jsonify({"ok": True})
    if p.exists():
        return jsonify(json.loads(p.read_text()))
    # Defaults
    return jsonify({
        "widgets": [
            {"id": "kpi-seeders",   "enabled": True,  "size": "small"},
            {"id": "kpi-top-res",   "enabled": True,  "size": "small"},
            {"id": "kpi-best-size", "enabled": True,  "size": "small"},
            {"id": "kpi-sources",   "enabled": True,  "size": "small"},
            {"id": "top-three",     "enabled": True,  "size": "wide"},
            {"id": "source-chart",  "enabled": True,  "size": "medium"},
            {"id": "res-chart",     "enabled": True,  "size": "medium"},
            {"id": "results",       "enabled": True,  "size": "full"},
            {"id": "recent-notifs", "enabled": False, "size": "small"},
            {"id": "manga-jobs",    "enabled": False, "size": "medium"},
        ]
    })


# ====================== LOGGING ======================
import logging, logging.handlers
LOG_PATH = DATA_DIR / "anitorr.log"
_logger = logging.getLogger("anitorr")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    _fh = logging.handlers.RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=2)
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    _logger.addHandler(_fh)
    _sh = logging.StreamHandler()
    _sh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    _logger.addHandler(_sh)
def log_event(msg, level="info"):
    getattr(_logger, level, _logger.info)(msg)

@app.before_request
def _log_req():
    if not request.path.startswith(("/static", "/api/notifications/unread")):
        _logger.info("%s %s", request.method, request.path)

# ====================== LIBRARY + REPORTS pages ======================
@app.route("/library")
def library_page():
    return render_template("library.html", cfg=cfg, active_tab="library")

@app.route("/reports")
def reports_page():
    return render_template("reports.html", cfg=cfg, active_tab="reports")

@app.route("/api/library/summary")
def api_library_summary():
    favs = _read(FAV_PATH)
    hist = _read(HIST_PATH)
    torrents = sorted(DOWNLOADS.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True) if DOWNLOADS.exists() else []
    torrents = [p for p in torrents if p.is_file()]
    mangas = sorted(MANGA_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True) if MANGA_DIR.exists() else []
    mangas = [p for p in mangas if p.is_file()]
    return jsonify({
        "torrents": [{"name": p.name, "size": p.stat().st_size, "mtime": int(p.stat().st_mtime),
                      "type": p.suffix.lstrip(".")} for p in torrents[:25]],
        "torrents_count": len(torrents),
        "torrents_size": sum(p.stat().st_size for p in torrents),
        "manga":    [{"name": p.name, "size": p.stat().st_size, "mtime": int(p.stat().st_mtime),
                      "type": p.suffix.lstrip(".")} for p in mangas[:25]],
        "manga_count": len(mangas),
        "manga_size": sum(p.stat().st_size for p in mangas),
        "favorites": favs[-25:],
        "favorites_count": len(favs),
        "recent": list(reversed(hist))[:25],
    })

@app.route("/api/logs")
def api_logs():
    n = int(request.args.get("n", 500))
    if not LOG_PATH.exists():
        return jsonify({"lines": [], "totals": {"total":0,"errors":0,"warns":0}})
    lines = LOG_PATH.read_text(errors="ignore").splitlines()[-n:]
    totals = {
        "total":  sum(1 for l in lines),
        "errors": sum(1 for l in lines if "[ERROR]" in l or "[CRITICAL]" in l),
        "warns":  sum(1 for l in lines if "[WARNING]" in l),
        "last":   lines[-1] if lines else "",
    }
    return jsonify({"lines": lines, "totals": totals})

@app.route("/api/logs", methods=["DELETE"])
def api_logs_clear():
    if LOG_PATH.exists(): LOG_PATH.write_text("")
    log_event("Log cleared via web UI")
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, threaded=True)
