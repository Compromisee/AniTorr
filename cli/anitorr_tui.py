"""Textual TUI — pastel themed, no white backgrounds."""
from __future__ import annotations
import sys, json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal, Container
from textual.widgets import (
    Header, Footer, Input, DataTable, Static, TabbedContent, TabPane,
    Button, Select, Switch, Label,
)
from textual.binding import Binding
from textual.reactive import reactive

from backend import sources, neural, metadata, clients
try:
    from backend import manga_sources, manga_dl
    HAS_MANGA = True
except Exception:
    HAS_MANGA = False

CFG_PATH = ROOT / "config.json"
def load_cfg(): return json.loads(CFG_PATH.read_text())

_LATIN = re.compile(r"[A-Za-z0-9]")
_CJK   = re.compile(r"[\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]")
def _tok(s): return {t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if len(t) >= 2}
def _relevant(q, t):
    qt = _tok(q); tt = _tok(t)
    if qt & tt: return True
    if _CJK.search(t or "") and len(qt) <= 3: return True
    if not _LATIN.search(t or ""): return False
    return False

def _fmt_size(n):
    if not n: return "—"
    for u in ["B","KiB","MiB","GiB","TiB"]:
        if n < 1024: return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}P"


class AnitorrTUI(App):
    """Pastel TUI. Background is a soft cream; no plain white anywhere."""

    CSS = """
    Screen {
        background: #1a1a1f;            /* dark variant by default */
        color: #f1ece6;
        layout: vertical;
    }

    Header {
        background: #ec2a6a;
        color: white;
        text-style: bold;
    }
    Footer {
        background: #1f1f24;
        color: #cfc9c3;
    }

    .panel {
        background: #25252b;
        color: #f1ece6;
        border: round #ec2a6a;
        padding: 1 2;
        margin: 0 1;
    }
    .pill {
        background: #3a1726;
        color: #ff5a92;
        padding: 0 1;
    }
    .ok    { color: #76e0a3; }
    .warn  { color: #f5c26b; }
    .err   { color: #ff6b81; }
    .accent{ color: #ec2a6a; text-style: bold; }
    .muted { color: #7c7771; }

    Input {
        background: #25252b;
        color: #f1ece6;
        border: round #ec2a6a;
    }
    Input:focus { border: round #ff5a92; }

    DataTable {
        background: #1f1f24;
        color: #f1ece6;
    }
    DataTable > .datatable--header {
        background: #2a2a30;
        color: #ec2a6a;
        text-style: bold;
    }
    DataTable > .datatable--cursor {
        background: #3a1726;
        color: #ff5a92;
    }
    DataTable > .datatable--hover {
        background: #2a2a30;
    }

    Button {
        background: #ec2a6a;
        color: white;
        border: none;
        margin: 0 1;
        text-style: bold;
    }
    Button:hover { background: #ff5a92; }
    Button.-ghost { background: #25252b; color: #f1ece6; border: round #4a4a4f; }

    TabbedContent { background: #1a1a1f; }
    Tabs { background: #1f1f24; }
    Tab { color: #cfc9c3; }
    Tab:hover { color: #ff5a92; }
    Tab.-active { color: #ec2a6a; text-style: bold; }

    Static.subtitle { color: #7c7771; padding: 0 1; }
    Static.title    { color: #ec2a6a; text-style: bold; padding: 0 1; }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("/", "focus_query", "Search"),
        Binding("d", "do_download", "Download"),
        Binding("c", "copy_magnet", "Copy magnet"),
        Binding("r", "do_search", "Re-search"),
        Binding("ctrl+l", "toggle_dark", "Toggle theme"),
    ]

    rows = reactive([])
    cur_idx = reactive(0)

    def __init__(self):
        super().__init__()
        self.cfg = load_cfg()
        self.ranker = neural.Ranker(self.cfg.get("trusted_groups", []))
        self.last_query = ""
        self.mode = "anime"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="t-anime"):
            with TabPane("Anime", id="t-anime"):
                with Vertical(classes="panel"):
                    yield Static("[bold #ec2a6a]ANITorr[/]  Anime torrent search · NN ranking · qBittorrent",
                                 classes="title")
                    with Horizontal():
                        yield Input(placeholder="Anime title… (Enter)", id="anime-q")
                        yield Select([
                            ("any",   "any"),
                            ("480p",  "480p"),
                            ("720p",  "720p"),
                            ("1080p", "1080p"),
                            ("2160p", "2160p"),
                        ], value=self.cfg.get("default_resolution", "1080p"),
                            prompt="Quality", id="anime-res")
                    yield DataTable(id="anime-tbl", zebra_stripes=True, cursor_type="row")
                    yield Static("ready · press / to search · ↑↓ to navigate · d to download",
                                 id="anime-status", classes="subtitle")
            with TabPane("Manga", id="t-manga"):
                with Vertical(classes="panel"):
                    yield Static("[bold #ec2a6a]Manga / Manhua / Webtoons[/]  13+ sources · CBZ / EPUB / PDF",
                                 classes="title")
                    with Horizontal():
                        yield Input(placeholder="Manga title… (Enter)", id="manga-q")
                        yield Select([("cbz","cbz"),("zip","zip"),("epub","epub"),("pdf","pdf")],
                                     value="cbz", prompt="Format", id="manga-fmt")
                    yield DataTable(id="manga-tbl", zebra_stripes=True, cursor_type="row")
                    yield Static("press / to search · Enter to load chapters",
                                 id="manga-status", classes="subtitle")
            with TabPane("Settings", id="t-settings"):
                with Vertical(classes="panel"):
                    yield Static("[bold #ec2a6a]Settings[/]  Press number to edit", classes="title")
                    yield DataTable(id="settings-tbl", cursor_type="row", zebra_stripes=True)
                    yield Static("changes save instantly to config.json", classes="subtitle")
        yield Footer()

    # ---- mount / init tables ----
    def on_mount(self):
        t = self.query_one("#anime-tbl", DataTable)
        t.add_columns("#", "Title", "Source", "Group", "Res", "Size", "S/L", "NN")
        t.cursor_foreground_priority = "renderable"

        m = self.query_one("#manga-tbl", DataTable)
        m.add_columns("#", "Title", "Source", "Status", "Lang")

        s = self.query_one("#settings-tbl", DataTable)
        s.add_columns("#", "Key", "Value")
        self._populate_settings()

    # ---- key bindings ----
    def action_focus_query(self):
        tabs = self.query_one(TabbedContent)
        active = tabs.active
        if active == "t-anime":   self.query_one("#anime-q", Input).focus()
        elif active == "t-manga": self.query_one("#manga-q", Input).focus()

    def action_do_search(self):
        tabs = self.query_one(TabbedContent).active
        if tabs == "t-anime":   self._run_anime_search()
        elif tabs == "t-manga": self._run_manga_search()

    def action_do_download(self):
        if self.query_one(TabbedContent).active != "t-anime": return
        if not self.rows: return
        t = self.query_one("#anime-tbl", DataTable)
        try: row_idx = t.cursor_row
        except Exception: row_idx = 0
        if row_idx is None or row_idx >= len(self.rows): return
        r = self.rows[row_idx]
        q = self.cfg.get("qbittorrent", {})
        if q.get("enabled") and (r.get("magnet") or r.get("torrent_url")):
            c = clients.QBitClient(q["host"], q["user"], q["password"], q.get("category","anime"))
            ok = c.add(r.get("magnet") or r.get("torrent_url"))
            self._set_anime_status(("ok" if ok else "err") + " → " + r.get("title","")[:60],
                                   "ok" if ok else "err")
            if ok: self.ranker.teach(r, self.rows[:25], self.last_query)
        else:
            self._set_anime_status("qBittorrent disabled or no magnet", "warn")

    def action_copy_magnet(self):
        if not self.rows: return
        t = self.query_one("#anime-tbl", DataTable)
        try: r = self.rows[t.cursor_row]
        except Exception: return
        try:
            import pyperclip; pyperclip.copy(r.get("magnet") or r.get("torrent_url") or "")
            self._set_anime_status("copied", "ok")
        except Exception:
            self._set_anime_status("clipboard module missing", "warn")

    # ---- input submission ----
    def on_input_submitted(self, ev: Input.Submitted):
        if ev.input.id == "anime-q":   self._run_anime_search()
        elif ev.input.id == "manga-q": self._run_manga_search()

    # ---- anime ----
    def _set_anime_status(self, text, kind=""):
        s = self.query_one("#anime-status", Static)
        s.update(f"[{kind or 'muted'}]{text}[/]")

    def _run_anime_search(self):
        q = self.query_one("#anime-q", Input).value.strip()
        if not q: return
        self.last_query = q
        self._set_anime_status(f"searching {q}…", "accent")
        meta = metadata.anilist_lookup(q) if self.cfg["plugins"].get("anilist_meta") else None
        variants = metadata.title_variants(q, meta)[:3]
        rows = []
        for v in variants:
            rows += sources.aggregate(v, self.cfg["sources"],
                self.cfg.get("cors_proxy_url"), self.cfg["ddl_sources"])
        # relevance gate
        rows = [r for r in rows if _relevant(q, r.get("title",""))]
        # rank + fallback
        ranked = self.ranker.rank(rows, q)
        qt = _tok(q)
        quality = sum(1 for r in ranked[:10] if qt & _tok(r.get("title",""))) / max(1, min(10, len(ranked)))
        if quality < 0.3 and ranked:
            ranked = sorted(rows, key=lambda r: r.get("seeders",0), reverse=True)
        # quality filter
        res = self.query_one("#anime-res", Select).value
        if res and res != "any":
            ranked = [r for r in ranked if r.get("resolution","") == res or not r.get("resolution")]

        self.rows = ranked[:50]
        t = self.query_one("#anime-tbl", DataTable)
        t.clear()
        for i, r in enumerate(self.rows, 1):
            t.add_row(str(i), (r.get("title","") or "")[:80], r.get("source",""),
                      (r.get("group") or "—")[:14],
                      r.get("resolution","") or "—",
                      _fmt_size(r.get("size_bytes",0)),
                      f"{r.get('seeders',0)}/{r.get('leechers',0)}",
                      f"{r.get('nn_score',0):.2f}")
        self._set_anime_status(f"{len(self.rows)} results · NN quality {quality:.0%}",
                               "ok" if self.rows else "warn")

    # ---- manga ----
    def _run_manga_search(self):
        if not HAS_MANGA: return
        q = self.query_one("#manga-q", Input).value.strip()
        if not q: return
        s = self.query_one("#manga-status", Static)
        s.update(f"[accent]searching {q}…[/accent]")
        enabled = self.cfg.get("manga_sources") or {n: True for n in manga_sources.SOURCES}
        rows = manga_sources.search_all(q, enabled)
        t = self.query_one("#manga-tbl", DataTable); t.clear()
        for i, r in enumerate(rows[:40], 1):
            t.add_row(str(i), (r.get("title","") or "")[:80], r.get("source",""),
                      r.get("status","") or "—", r.get("lang","") or "—")
        s.update(f"[ok]{len(rows)} results[/ok]")

    # ---- settings ----
    def _populate_settings(self):
        keys = [
            ("theme",                 self.cfg.get("theme")),
            ("default_resolution",    self.cfg.get("default_resolution")),
            ("default_lang",          self.cfg.get("default_lang")),
            ("min_seeders",           self.cfg.get("min_seeders")),
            ("aggregator_threshold",  self.cfg.get("aggregator_threshold")),
            ("qbittorrent.enabled",   self.cfg.get("qbittorrent",{}).get("enabled")),
            ("qbittorrent.host",      self.cfg.get("qbittorrent",{}).get("host")),
            ("manga.default_format",  self.cfg.get("manga",{}).get("default_format")),
            ("manga.autocrop",        self.cfg.get("manga",{}).get("autocrop")),
        ]
        s = self.query_one("#settings-tbl", DataTable); s.clear()
        for i, (k, v) in enumerate(keys, 1):
            s.add_row(str(i), k, str(v))


def run_tui():
    AnitorrTUI().run()

if __name__ == "__main__":
    run_tui()
