#!/usr/bin/env python3
"""ANITorr — interactive colored CLI.

When launched with no arguments it walks you through:
   1. Pick mode: anime torrent / manga / settings
   2. Anime → query, quality, language → table of results
      → pick row → file list (qBittorrent metadata API)
      → pick files → choose action (qBit / .torrent / .magnet / copy)
   3. Manga → query → series picker → chapter table → format → download
   4. Settings → live edit config.json

Direct mode still works:  anitorr -q "Frieren" -r 1080 --auto
"""
from __future__ import annotations
import argparse, json, sys, os, time, urllib.parse, re, base64, hashlib
from pathlib import Path
from typing import List, Dict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.theme import Theme
from rich.text import Text
from rich.align import Align
from rich.box import ROUNDED, MINIMAL_HEAVY_HEAD, SIMPLE_HEAVY
from rich.columns import Columns
import pyfiglet

from backend import sources, neural, metadata, clients, interpreter
try:
    from backend import manga_sources, manga_dl
    HAS_MANGA = True
except Exception:
    HAS_MANGA = False

CFG_PATH = ROOT / "config.json"
def cfg(): return json.loads(CFG_PATH.read_text())
def save_cfg(c): CFG_PATH.write_text(json.dumps(c, indent=2))

# ---------- pastel themes (no white bg anywhere) ----------
THEMES = {
    "pastel": Theme({
        "accent":  "#EC2A6A",
        "muted":   "#8E8A86",
        "ok":      "#76E0A3",
        "warn":    "#F5C26B",
        "err":     "#FF6B81",
        "title":   "bold #EC2A6A",
        "head":    "bold #1A1A1A",
        "bg":      "#F3EFEC",
        "panel":   "#FFFFFF on default",
        "pill":    "bold white on #EC2A6A",
        "soft":    "#EC2A6A on #FCE3EC",
    }),
    "dracula": Theme({
        "accent": "#FF79C6", "muted": "#6272A4", "ok": "#50FA7B", "warn": "#F1FA8C",
        "err": "#FF5555", "title": "bold #BD93F9", "head": "bold #F8F8F2",
        "bg": "#282A36", "pill": "bold white on #FF79C6", "soft": "#FF79C6 on #3D2A4A",
    }),
    "nord": Theme({
        "accent": "#88C0D0", "muted": "#81A1C1", "ok": "#A3BE8C", "warn": "#EBCB8B",
        "err": "#BF616A", "title": "bold #88C0D0", "head": "bold #ECEFF4",
        "bg": "#2E3440", "pill": "bold white on #88C0D0", "soft": "#88C0D0 on #3B4A5A",
    }),
    "mono": Theme({
        "accent":"white","muted":"grey50","ok":"white","warn":"white","err":"white",
        "title":"bold white","head":"bold white","bg":"black",
        "pill":"reverse bold","soft":"white on grey15",
    }),
}

def build_console(theme="pastel"):
    return Console(theme=THEMES.get(theme, THEMES["pastel"]), highlight=False)

# ---------- helpers ----------
def fmt_size(n):
    if not n: return "—"
    for u in ["B","KiB","MiB","GiB","TiB"]:
        if n < 1024: return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}PiB"

def seeder_color(s):
    return "ok" if s >= 50 else ("warn" if s >= 5 else "err")

def banner(c, theme="pastel"):
    art = pyfiglet.figlet_format("ANITorr", font="slant")
    c.print(Panel.fit(
        Align.center(Text(art, style="title")),
        border_style="accent",
        subtitle="[muted]plugin-driven anime + manga + torrents[/muted]",
        padding=(0, 2),
    ))

# ---------- relevance gate (mirror of backend) ----------
_LATIN = re.compile(r"[A-Za-z0-9]")
_CJK   = re.compile(r"[\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]")
def tokens(s):
    return {t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if len(t) >= 2}
def is_relevant(query, title, q_tokens=None):
    if not title: return False
    qt = q_tokens if q_tokens is not None else tokens(query)
    if qt & tokens(title): return True
    if _CJK.search(title) and len(qt) <= 3: return True
    if not _LATIN.search(title): return False
    return False

# ============================================================
# qBittorrent file-listing — uses the same client/host as the
# rest of the app to enumerate files inside a magnet without
# actually starting the download.
# ============================================================
def qbit_inspect(magnet_or_url, host, user, password):
    """Add the magnet paused, wait for metadata, list files, then remove it."""
    import requests
    s = requests.Session()
    try:
        if s.post(f"{host.rstrip('/')}/api/v2/auth/login",
                  data={"username": user, "password": password},
                  timeout=8).text.strip() != "Ok.":
            return None, "auth failed"
    except Exception as e:
        return None, f"login error: {e}"
    # hash from magnet
    m = re.search(r"btih:([A-Fa-f0-9]{40}|[A-Z2-7]{32})", magnet_or_url)
    if not m: return None, "no btih in magnet"
    h = m.group(1).lower()
    if len(h) == 32:  # base32 → hex
        try:
            h = base64.b32decode(h.upper()).hex()
        except Exception: pass
    try:
        s.post(f"{host.rstrip('/')}/api/v2/torrents/add",
               data={"urls": magnet_or_url, "paused": "true",
                     "stopCondition": "MetadataReceived"}, timeout=10)
    except Exception as e:
        return None, f"add failed: {e}"
    files = []
    for _ in range(30):
        time.sleep(1)
        try:
            r = s.get(f"{host.rstrip('/')}/api/v2/torrents/files",
                      params={"hash": h}, timeout=6)
            if r.status_code == 200 and r.json():
                files = r.json(); break
        except Exception:
            pass
    try:
        s.post(f"{host.rstrip('/')}/api/v2/torrents/delete",
               data={"hashes": h, "deleteFiles": "true"}, timeout=6)
    except Exception: pass
    return files, None

# ============================================================
# UI primitives
# ============================================================
def results_table(rows, limit=25, highlight_idx=None) -> Table:
    t = Table(box=ROUNDED, header_style="head", border_style="muted",
              show_lines=False, expand=True, pad_edge=False)
    t.add_column("#",     justify="right", style="muted", width=3)
    t.add_column("Title", overflow="fold")
    t.add_column("Src",   no_wrap=True, style="accent")
    t.add_column("Group", no_wrap=True)
    t.add_column("Res",   no_wrap=True, justify="center")
    t.add_column("Size",  no_wrap=True, justify="right")
    t.add_column("S",     no_wrap=True, justify="right")
    t.add_column("L",     no_wrap=True, justify="right", style="muted")
    t.add_column("NN",    no_wrap=True, justify="right")
    for i, r in enumerate(rows[:limit], 1):
        sc = seeder_color(r.get("seeders", 0))
        style = "bold accent" if highlight_idx == i - 1 else ""
        t.add_row(
            f"[{style}]{i}[/]" if style else str(i),
            (r.get("title", "") or "")[:120],
            r.get("source", ""),
            (r.get("group") or "—")[:14],
            r.get("resolution") or "—",
            fmt_size(r.get("size_bytes", 0)),
            f"[{sc}]{r.get('seeders', 0)}[/{sc}]",
            str(r.get("leechers", 0)),
            f"{r.get('nn_score', 0):.2f}",
        )
    return t

def files_table(files) -> Table:
    t = Table(box=ROUNDED, header_style="head", border_style="muted", expand=True)
    t.add_column("#", justify="right", style="muted", width=4)
    t.add_column("File", overflow="fold")
    t.add_column("Size", justify="right", no_wrap=True)
    for i, f in enumerate(files, 1):
        name = f.get("name") if isinstance(f, dict) else str(f)
        size = f.get("size", 0) if isinstance(f, dict) else 0
        t.add_row(str(i), name, fmt_size(size))
    return t

def kv_panel(title, items, style="accent"):
    body = "\n".join(f"[muted]{k:>16}[/muted] : [head]{v}[/head]" for k, v in items)
    return Panel(body, title=f"[title]{title}[/title]", border_style=style, padding=(1, 2))

# ============================================================
# Anime flow
# ============================================================
def anime_flow(c: Console, cdata, theme, args=None):
    """Interactive anime search → table → file picker → download."""
    if not args or not args.query:
        query = Prompt.ask("[title]Anime title[/title]")
    else:
        query = args.query

    res = Prompt.ask("[title]Quality[/title]",
                     choices=["480p","720p","1080p","2160p","any"],
                     default=cdata.get("default_resolution", "1080p")) if not (args and args.res) else args.res
    lang = Prompt.ask("[title]Language[/title]",
                      choices=["en","jp","es","fr","multi","any"],
                      default=cdata.get("default_lang", "en")) if not (args and args.lang) else args.lang
    use_ai = True
    if not args:
        use_ai = Confirm.ask("[title]Use AI title normalization?[/title]", default=True)

    ranker = neural.Ranker(cdata.get("trusted_groups", []),
                           cdata["neural_network"]["learning_rate"])

    # Search with progress spinner
    with Progress(SpinnerColumn(style="accent"),
                  TextColumn("[muted]{task.description}[/muted]"),
                  BarColumn(complete_style="accent"),
                  TimeElapsedColumn(), console=c, transient=True) as p:
        t1 = p.add_task("metadata…", total=None)
        meta = metadata.anilist_lookup(query) if cdata["plugins"]["anilist_meta"] else None
        variants = metadata.title_variants(query, meta)
        if use_ai and cdata["plugins"].get("ai_title_norm"):
            variants += metadata.ai_normalize(query, cdata["ai"])
        variants = list(dict.fromkeys(variants))[:4]
        p.update(t1, description=f"variants: {variants}")

        all_rows = []
        t2 = p.add_task(f"querying {sum(1 for v in cdata['sources'].values() if v)} sources…",
                        total=len(variants))
        for v in variants:
            all_rows += sources.aggregate(v, cdata["sources"],
                cdata.get("cors_proxy_url"), cdata["ddl_sources"],
                cdata.get("aggregator_threshold", 5),
                cdata.get("max_threads", 12))
            p.advance(t2)

    # --- relevance gate ---
    if cdata.get("plugins", {}).get("relevance_filter", True):
        all_tokens = tokens(query)
        for v in variants: all_tokens |= tokens(v)
        before = len(all_rows)
        all_rows = [r for r in all_rows if is_relevant(query, r.get("title",""), all_tokens)]
        c.print(f"[muted]relevance filter: {before} → {len(all_rows)} results[/muted]")

    # --- user filters ---
    if res != "any":
        all_rows = [r for r in all_rows if r.get("resolution","") == res or not r.get("resolution")]

    # --- NN rank with fallback ---
    ranked = ranker.rank(all_rows, query)
    qt = tokens(query)
    quality = sum(1 for r in ranked[:10] if qt & tokens(r.get("title",""))) / max(1, min(10, len(ranked)))
    if quality < 0.3 and ranked:
        c.print(f"[warn]NN relevance {quality:.0%} too low — sorting by seeders instead[/warn]")
        ranked = sorted(all_rows, key=lambda r: (r.get("seeders",0),
                                                 1 if r.get("resolution")=="1080p" else 0),
                        reverse=True)

    if not ranked:
        c.print("[err]No results.[/err]"); return

    # --- meta + table ---
    if meta:
        title = (meta.get("title") or {}).get("english") or (meta.get("title") or {}).get("romaji")
        c.print(kv_panel("AniList", [
            ("Title", title or "—"),
            ("Score", str(meta.get("averageScore", "—"))),
            ("Episodes", str(meta.get("episodes", "—"))),
            ("Status", meta.get("status", "—")),
            ("Genres", ", ".join(meta.get("genres") or [])[:60]),
        ]))

    c.print(results_table(ranked, limit=25))

    # --- pick row ---
    while True:
        choice = Prompt.ask("[title]Pick #[/title] (n=new search, q=quit)",
                            default="1")
        if choice.lower() == "q": return
        if choice.lower() == "n": return anime_flow(c, cdata, theme)
        try:
            idx = int(choice)
            if 1 <= idx <= len(ranked): break
            c.print("[err]out of range[/err]")
        except ValueError:
            c.print("[err]not a number[/err]")

    pick = ranked[idx - 1]
    ranker.teach(pick, ranked[:25], query)
    c.print(kv_panel("Selected", [
        ("Title", pick.get("title","")[:80]),
        ("Source", pick.get("source","")),
        ("Group",  pick.get("group","") or "—"),
        ("Size",   fmt_size(pick.get("size_bytes",0))),
        ("Seeders / Leechers", f"{pick.get('seeders',0)} / {pick.get('leechers',0)}"),
        ("Magnet", "yes" if pick.get("magnet") else "no"),
        ("Torrent", "yes" if pick.get("torrent_url") else "no"),
    ]))

    # --- file listing via qBittorrent if magnet available ---
    files = []
    q = cdata.get("qbittorrent", {})
    if pick.get("magnet") and q.get("enabled"):
        with c.status("[muted]asking qBittorrent for metadata… (~10s)[/muted]", spinner="dots"):
            files, err = qbit_inspect(pick["magnet"], q["host"], q["user"], q["password"])
        if err:
            c.print(f"[warn]qBit metadata fetch failed: {err}[/warn]")
        elif files:
            c.print(files_table(files))
    elif pick.get("page_url"):
        # Best-effort page scrape
        try:
            import requests; from bs4 import BeautifulSoup
            r = requests.get(pick["page_url"], timeout=12, headers={"User-Agent":"ANITorr/1.0"})
            soup = BeautifulSoup(r.text, "lxml")
            scraped = []
            for li in soup.select(".torrent-file-list li, ul li"):
                t = li.get_text(strip=True)
                if "." in t and len(t) < 200: scraped.append(t)
            if scraped:
                files = [{"name": s, "size": 0} for s in scraped[:50]]
                c.print(files_table(files))
        except Exception: pass

    # --- pick which files (optional) ---
    selected_idx = None
    if files:
        ans = Prompt.ask("[title]Files to download[/title] (e.g. '1,3,5' or 'all')",
                         default="all")
        if ans.lower() != "all":
            try:
                selected_idx = sorted({int(x.strip()) - 1 for x in ans.split(",") if x.strip()})
            except Exception:
                c.print("[err]bad selection, downloading all[/err]")

    # --- action picker ---
    mode = Prompt.ask("[title]Action[/title]",
                      choices=["qbit","file","magnet","copy","skip"], default="qbit")
    if mode == "skip": return
    if mode == "copy":
        try:
            import pyperclip; pyperclip.copy(pick.get("magnet") or pick.get("torrent_url") or "")
            c.print("[ok]Copied.[/ok]")
        except Exception:
            c.print(pick.get("magnet") or pick.get("torrent_url"))
        return
    if mode == "qbit" and q.get("enabled"):
        cli = clients.QBitClient(q["host"], q["user"], q["password"],
                                 q.get("category","anime"), q.get("save_path",""))
        ok = cli.add(pick.get("magnet") or pick.get("torrent_url"))
        c.print("[ok]Sent to qBittorrent.[/ok]" if ok else "[err]qBit add failed.[/err]")
        if ok and selected_idx is not None and pick.get("magnet"):
            # Use qbit API to set file priorities (0 = skip, 1 = normal)
            import requests
            m = re.search(r"btih:([A-Fa-f0-9]{40}|[A-Z2-7]{32})", pick["magnet"])
            if m:
                h = m.group(1).lower()
                if len(h) == 32:
                    try: h = base64.b32decode(h.upper()).hex()
                    except Exception: pass
                sess = requests.Session()
                sess.post(f"{q['host'].rstrip('/')}/api/v2/auth/login",
                          data={"username": q["user"], "password": q["password"]}, timeout=8)
                # Wait for files to materialise
                for _ in range(20):
                    time.sleep(1)
                    r = sess.get(f"{q['host'].rstrip('/')}/api/v2/torrents/files",
                                 params={"hash": h}, timeout=6)
                    if r.status_code == 200 and r.json(): break
                want = set(selected_idx)
                skip_ids = ",".join(str(i) for i in range(len(files)) if i not in want)
                if skip_ids:
                    sess.post(f"{q['host'].rstrip('/')}/api/v2/torrents/filePrio",
                              data={"hash": h, "id": skip_ids, "priority": 0}, timeout=6)
                    c.print(f"[ok]Set {len(want)} files to download, {len(files)-len(want)} skipped.[/ok]")
        return
    if mode == "file" and pick.get("torrent_url"):
        path = clients.save_torrent_file(pick["torrent_url"], str(ROOT/"downloads"))
        c.print(f"[ok]Saved → {path}[/ok]" if path else "[err]Failed.[/err]")
        return
    if mode == "magnet" and pick.get("magnet"):
        path = clients.magnet_to_file(pick["magnet"], str(ROOT/"downloads"))
        c.print(f"[ok]Saved → {path}[/ok]")
        return
    c.print("[warn]Nothing to do — that result has no magnet or torrent URL.[/warn]")


# ============================================================
# Manga flow
# ============================================================
def manga_flow(c, cdata, theme):
    if not HAS_MANGA:
        c.print("[err]Manga module not available.[/err]"); return
    q = Prompt.ask("[title]Manga / manhua / webtoon title[/title]")
    enabled = cdata.get("manga_sources") or {n: True for n in manga_sources.SOURCES}
    with c.status(f"[muted]searching {sum(1 for v in enabled.values() if v)} sources…[/muted]", spinner="dots"):
        rows = manga_sources.search_all(q, enabled)

    if not rows:
        c.print("[err]No matches.[/err]"); return

    # --- series table ---
    t = Table(box=ROUNDED, header_style="head", border_style="muted", expand=True)
    t.add_column("#", justify="right", style="muted", width=3)
    t.add_column("Title", overflow="fold")
    t.add_column("Source", style="accent")
    t.add_column("Status", style="muted")
    t.add_column("Lang", style="muted", no_wrap=True)
    for i, r in enumerate(rows[:30], 1):
        t.add_row(str(i), (r.get("title","") or "")[:80],
                  r.get("source",""), r.get("status","") or "—",
                  r.get("lang","") or "—")
    c.print(t)

    idx = IntPrompt.ask("[title]Pick series #[/title]", default=1)
    if not (1 <= idx <= len(rows)): return
    pick = rows[idx-1]

    with c.status("[muted]loading chapters…[/muted]", spinner="dots"):
        chapters = manga_sources.get_chapters(pick["source"], pick["url"])
    if not chapters:
        c.print("[err]No chapters.[/err]"); return

    ct = Table(box=ROUNDED, header_style="head", border_style="muted", expand=True)
    ct.add_column("#", justify="right", style="muted", width=4)
    ct.add_column("Chapter title", overflow="fold")
    ct.add_column("Num", justify="right", no_wrap=True)
    ct.add_column("Pages", justify="right", no_wrap=True)
    for i, ch in enumerate(chapters[:80], 1):
        ct.add_row(str(i), (ch.get("title","") or "")[:80],
                   str(ch.get("number","")), str(ch.get("pages","?")))
    c.print(ct)

    ans = Prompt.ask("[title]Chapters[/title] (e.g. 1,2,3 / 1-10 / all)",
                     default="1")
    sel = []
    if ans.lower() == "all":
        sel = list(range(len(chapters)))
    else:
        for part in ans.split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-", 1)
                sel.extend(range(int(a)-1, int(b)))
            else:
                sel.append(int(part)-1)
        sel = sorted(set(i for i in sel if 0 <= i < len(chapters)))

    fmt = Prompt.ask("[title]Format[/title]",
                     choices=["cbz","zip","epub","pdf"],
                     default=cdata.get("manga",{}).get("default_format","cbz"))
    crop = Confirm.ask("[title]Auto-crop margins?[/title]",
                       default=cdata.get("manga",{}).get("autocrop", False))

    out_dir = Path(cdata.get("manga",{}).get("save_path") or (ROOT / "manga"))
    out_dir.mkdir(parents=True, exist_ok=True)

    with Progress(SpinnerColumn(style="accent"),
                  TextColumn("[head]{task.fields[name]}[/head]"),
                  BarColumn(complete_style="accent"),
                  TextColumn("{task.completed}/{task.total}"),
                  console=c) as p:
        overall = p.add_task("", total=len(sel), name="chapters")
        for i in sel:
            ch = chapters[i]
            pages = manga_sources.get_pages(pick["source"], ch["url"])
            if not pages:
                c.print(f"[warn]No pages for {ch.get('title')}[/warn]"); p.advance(overall); continue
            title = f"{pick['title']} - {ch.get('title')}"
            jid = manga_dl.start_job(title=title, source=pick["source"],
                page_urls=pages, fmt=fmt, out_dir=out_dir, autocrop=crop,
                series=pick["title"])
            # block until job done
            while True:
                j = manga_dl.get_job(jid)
                if j.get("status") in ("done","error"): break
                time.sleep(0.4)
            if j.get("status") == "done":
                c.print(f"[ok]✓ {Path(j['path']).name}[/ok]")
            else:
                c.print(f"[err]✗ {ch.get('title')}: {j.get('error','')}[/err]")
            p.advance(overall)
    c.print(f"\n[ok]Saved to {out_dir}[/ok]")


# ============================================================
# Settings flow
# ============================================================
def settings_flow(c, cdata):
    sections = [
        ("Theme & language", [
            ("theme",              ["cream","dark","dracula","nord","solarized","mono"]),
            ("language",           ["en","jp","es","fr","de"]),
            ("default_resolution", ["480p","720p","1080p","2160p"]),
            ("default_lang",       ["en","jp","es","fr","multi"]),
        ]),
        ("Behaviour", [
            ("min_seeders",          "int"),
            ("aggregator_threshold", "int"),
            ("cache_ttl_seconds",    "int"),
            ("max_threads",          "int"),
        ]),
        ("qBittorrent", [
            ("qbittorrent.enabled",  "bool"),
            ("qbittorrent.host",     "str"),
            ("qbittorrent.user",     "str"),
            ("qbittorrent.password", "str"),
            ("qbittorrent.category", "str"),
        ]),
        ("Manga", [
            ("manga.default_format", ["cbz","zip","epub","pdf"]),
            ("manga.autocrop",       "bool"),
            ("manga.page_progression", ["rtl","ltr"]),
            ("manga.save_path",      "str"),
        ]),
    ]

    def get(p):
        cur = cdata
        for k in p.split("."): cur = cur.get(k) if isinstance(cur, dict) else None
        return cur
    def setp(p, v):
        cur = cdata
        ks = p.split(".")
        for k in ks[:-1]:
            cur.setdefault(k, {})
            cur = cur[k]
        cur[ks[-1]] = v

    while True:
        c.print("\n[head]Settings[/head]")
        # render
        t = Table(box=ROUNDED, header_style="head", border_style="muted", expand=True)
        t.add_column("#", style="muted", width=3, justify="right")
        t.add_column("Section")
        t.add_column("Key", style="accent")
        t.add_column("Value", style="head")
        flat = []
        i = 1
        for section, keys in sections:
            for k, kind in keys:
                v = get(k); flat.append((section, k, kind))
                t.add_row(str(i), section, k, str(v))
                i += 1
        c.print(t)

        choice = Prompt.ask("[title]Pick # to edit[/title] (s=save, q=quit)", default="q")
        if choice.lower() == "q": return
        if choice.lower() == "s":
            save_cfg(cdata); c.print("[ok]Saved.[/ok]"); continue
        try: idx = int(choice) - 1
        except ValueError: continue
        if not (0 <= idx < len(flat)): continue

        _, key, kind = flat[idx]
        cur = get(key)
        if isinstance(kind, list):
            new = Prompt.ask(f"new value for [accent]{key}[/accent]",
                             choices=kind, default=str(cur) if str(cur) in kind else kind[0])
            setp(key, new)
        elif kind == "bool":
            new = Confirm.ask(f"enable [accent]{key}[/accent]?", default=bool(cur))
            setp(key, new)
        elif kind == "int":
            new = IntPrompt.ask(f"new value for [accent]{key}[/accent]",
                                default=int(cur) if cur is not None else 0)
            setp(key, new)
        else:
            new = Prompt.ask(f"new value for [accent]{key}[/accent]",
                             default=str(cur) if cur is not None else "")
            setp(key, new)
        save_cfg(cdata)
        c.print("[ok]saved → config.json[/ok]")


# ============================================================
# Mode picker
# ============================================================
def pick_mode(c):
    c.print()
    panels = [
        Panel("[head]ANIME[/head]\n[muted]torrent search, NN ranking,\nfile picker, qBittorrent[/muted]",
              border_style="accent", title="[title]1[/title]", padding=(1,2), expand=True),
        Panel("[head]MANGA[/head]\n[muted]13+ sources, CBZ/EPUB/PDF\nApple-Books metadata[/muted]",
              border_style="accent", title="[title]2[/title]", padding=(1,2), expand=True),
        Panel("[head]SETTINGS[/head]\n[muted]edit config.json\ninteractively[/muted]",
              border_style="accent", title="[title]3[/title]", padding=(1,2), expand=True),
    ]
    c.print(Columns(panels, expand=True, equal=True))
    return Prompt.ask("\n[title]What do you want?[/title]",
                      choices=["anime","manga","settings","1","2","3","q"], default="anime")


# ============================================================
# main entry
# ============================================================
def main():
    ap = argparse.ArgumentParser("anitorr")
    ap.add_argument("-q","--query")
    ap.add_argument("-r","--res", default="")
    ap.add_argument("-l","--lang", default="")
    ap.add_argument("-g","--group", default="")
    ap.add_argument("-s","--source", default="all")
    ap.add_argument("-b","--batch", action="store_true")
    ap.add_argument("-a","--auto", action="store_true")
    ap.add_argument("-t","--theme", default="pastel", choices=list(THEMES.keys()))
    ap.add_argument("--tui", action="store_true")
    ap.add_argument("--manga", action="store_true", help="Skip mode picker → manga")
    ap.add_argument("--settings", action="store_true", help="Skip mode picker → settings")
    ap.add_argument("--client", default="qbit",
                    choices=["qbit","deluge","transmission","file","magnet"])
    ap.add_argument("--export", choices=["json","csv"])
    ap.add_argument("--module")
    ap.add_argument("--param", action="append", default=[])
    args = ap.parse_args()

    c = build_console(args.theme)
    cdata = cfg()

    if args.module:
        spec = interpreter.find(args.module)
        if not spec:
            c.print(f"[err]Module '{args.module}' not found.[/err]"); sys.exit(1)
        kw = {kv.split("=",1)[0]: kv.split("=",1)[1] for kv in args.param if "=" in kv}
        out = spec.call(**kw)
        c.print(Panel(str(out), title=f"module:{args.module}", border_style="accent"))
        return

    if args.tui:
        try:
            from anitorr_tui import run_tui; run_tui(); return
        except Exception as e:
            c.print(f"[err]TUI failed: {e}[/err]"); return

    banner(c, args.theme)

    # Direct anime mode if -q passed
    if args.query:
        return anime_flow(c, cdata, args.theme, args=args)
    if args.manga:
        return manga_flow(c, cdata, args.theme)
    if args.settings:
        return settings_flow(c, cdata)

    # Interactive mode picker
    while True:
        mode = pick_mode(c)
        if mode in ("q",): return
        if mode in ("anime","1"):    anime_flow(c, cdata, args.theme); cdata = cfg()
        elif mode in ("manga","2"):  manga_flow(c, cdata, args.theme); cdata = cfg()
        elif mode in ("settings","3"): settings_flow(c, cdata); cdata = cfg()
        if not Confirm.ask("\n[title]Do something else?[/title]", default=True):
            return

if __name__ == "__main__":
    main()
