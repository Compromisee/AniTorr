"""
Manga / Manhua / Webtoon source adapters.

Every adapter exposes a uniform API:
    search(query)  -> [{title, slug, source, cover, url, status, lang}]
    chapters(url)  -> [{title, number, url, pages}]
    pages(chapter_url) -> [page_image_url, ...]

The list below is intentionally large (12 sources). Many third-party APIs change
their endpoints frequently; rather than embed brittle scrapers we provide a
stable interface and best-effort URL builders so the rest of the app (download,
packaging, metadata, UI) always works. Each adapter is overridable via a plugin
file in plugins/manga/<name>.py exporting the same three callables.
"""
from __future__ import annotations
import re, urllib.parse, requests, json, importlib.util
from pathlib import Path
from typing import List, Dict, Callable, Tuple
from bs4 import BeautifulSoup

UA = {"User-Agent": "Mozilla/5.0 (ANITorr manga)"}
TIMEOUT = 15

# -------------------------------------------------------------------- helpers
def _get(url, **kw) -> requests.Response | None:
    try:
        r = requests.get(url, headers=UA, timeout=TIMEOUT, **kw)
        return r if r.status_code == 200 else None
    except Exception:
        return None


def _soup(url):
    r = _get(url)
    return BeautifulSoup(r.text, "lxml") if r else None


# -------------------------------------------------------------------- sources

def _mangadex_search(q: str) -> List[Dict]:
    """MangaDex has a public API."""
    r = _get(f"https://api.mangadex.org/manga?title={urllib.parse.quote(q)}&limit=20"
             "&includes[]=cover_art")
    if not r:
        return []
    out = []
    try:
        for d in r.json().get("data", []):
            attr = d.get("attributes", {})
            title_obj = attr.get("title", {}) or {}
            title = title_obj.get("en") or next(iter(title_obj.values()), d["id"])
            cover_fn = ""
            for rel in d.get("relationships", []):
                if rel.get("type") == "cover_art":
                    cover_fn = rel.get("attributes", {}).get("fileName", "")
            cover = f"https://uploads.mangadex.org/covers/{d['id']}/{cover_fn}.256.jpg" if cover_fn else ""
            out.append({
                "title": title, "slug": d["id"], "source": "mangadex",
                "cover": cover, "url": f"https://mangadex.org/title/{d['id']}",
                "status": attr.get("status", ""),
                "lang": attr.get("originalLanguage", ""),
                "year": attr.get("year"),
                "tags": [t["attributes"]["name"].get("en", "")
                         for t in attr.get("tags", []) if t.get("attributes", {}).get("name")],
            })
    except Exception:
        pass
    return out


def _mangadex_chapters(slug_or_url: str) -> List[Dict]:
    sid = slug_or_url.rstrip("/").split("/")[-1] if "://" in slug_or_url else slug_or_url
    r = _get(f"https://api.mangadex.org/manga/{sid}/feed?translatedLanguage[]=en"
             "&order[chapter]=asc&limit=200")
    out = []
    if not r:
        return out
    try:
        for c in r.json().get("data", []):
            a = c.get("attributes", {})
            out.append({
                "title": a.get("title") or f"Chapter {a.get('chapter','?')}",
                "number": a.get("chapter") or "0",
                "url": f"https://api.mangadex.org/at-home/server/{c['id']}",
                "pages": int(a.get("pages") or 0),
                "id": c["id"],
            })
    except Exception:
        pass
    return out


def _mangadex_pages(chapter_url: str) -> List[str]:
    r = _get(chapter_url)
    if not r:
        return []
    try:
        j = r.json()
        host = j.get("baseUrl", "")
        ch = j.get("chapter", {})
        hash_ = ch.get("hash", "")
        data = ch.get("data", []) or ch.get("dataSaver", [])
        return [f"{host}/data/{hash_}/{p}" for p in data]
    except Exception:
        return []


# ---- Generic HTML-scraping adapters --------------------------------------
def _build_simple(name: str, search_url: str, link_selector: str,
                  title_attr: str = "title") -> Tuple[Callable, Callable, Callable]:
    """Factory for "search returns links; everything else handled by plugin"."""
    def search(q: str):
        s = _soup(search_url.format(q=urllib.parse.quote_plus(q)))
        if not s:
            return []
        out = []
        for a in s.select(link_selector)[:40]:
            title = a.get(title_attr) or a.get_text(strip=True)
            href = a.get("href", "")
            if not href:
                continue
            if not href.startswith("http"):
                base = "/".join(search_url.split("/")[:3])
                href = base + href if href.startswith("/") else f"{base}/{href}"
            img = a.find("img")
            cover = img.get("src") if img else ""
            if cover and not cover.startswith("http"):
                base = "/".join(search_url.split("/")[:3])
                cover = base + cover if cover.startswith("/") else f"{base}/{cover}"
            out.append({"title": title.strip(), "slug": href.rstrip("/").split("/")[-1],
                        "source": name, "url": href, "cover": cover or "",
                        "status": "", "lang": "", "year": None, "tags": []})
        return out

    def chapters(url: str):
        s = _soup(url)
        if not s:
            return []
        out = []
        for a in s.select("a"):
            href = a.get("href", "")
            text = a.get_text(strip=True)
            if not href or not text:
                continue
            if re.search(r"chapter|ch[\.\s-]*\d|episode|cap[ií]tulo", text, re.I):
                if not href.startswith("http"):
                    base = "/".join(url.split("/")[:3])
                    href = base + href if href.startswith("/") else f"{base}/{href}"
                m = re.search(r"\d+(?:\.\d+)?", text)
                out.append({"title": text, "number": m.group(0) if m else "0",
                            "url": href, "pages": 0})
            if len(out) > 500:
                break
        return out

    def pages(url: str):
        s = _soup(url)
        if not s:
            return []
        imgs = []
        for img in s.select("img"):
            src = img.get("data-src") or img.get("src") or ""
            if re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", src, re.I) and \
               not re.search(r"(thumb|avatar|logo|icon)", src, re.I):
                if not src.startswith("http"):
                    base = "/".join(url.split("/")[:3])
                    src = base + src if src.startswith("/") else f"{base}/{src}"
                imgs.append(src)
        return imgs

    return search, chapters, pages


# 12 distinct sources. The MangaDex one is API-backed (always works); the rest
# share the generic HTML adapter and are easy to override via plugins.
_mangapark   = _build_simple("mangapark",   "https://mangapark.net/search?word={q}",
                              "a.fw-bold")
_mangakakalot = _build_simple("mangakakalot", "https://mangakakalot.com/search/story/{q}",
                              "a.story_name")
_manganato   = _build_simple("manganato",   "https://manganato.com/search/story/{q}",
                              "a.a-h.text-nowrap-2")
_mangafox    = _build_simple("mangafox",    "https://fanfox.net/search?title={q}",
                              "a.manga-list-1-item-title")
_batoto      = _build_simple("batoto",      "https://bato.to/search?word={q}",
                              "a.item-title")
_hitomi      = _build_simple("hitomi",      "https://hitomi.la/search.html?{q}",
                              "h1.lillie a")
_webtoons    = _build_simple("webtoons",    "https://www.webtoons.com/en/search?keyword={q}",
                              "a.card_item")
_tappytoon   = _build_simple("tappytoon",   "https://www.tappytoon.com/en/search?term={q}",
                              "a.title")
_mangaplus   = _build_simple("mangaplus",   "https://mangaplus.shueisha.co.jp/search?q={q}",
                              "a")
_asurascans  = _build_simple("asurascans",  "https://asurascans.com/?s={q}",
                              "a.bsx")
_reaperscans = _build_simple("reaperscans", "https://reaper-scans.com/?s={q}",
                              "a.bsx")
_flamescans  = _build_simple("flamescans",  "https://flamescans.org/?s={q}",
                              "a.bsx")

SOURCES: Dict[str, Tuple[Callable, Callable, Callable]] = {
    "mangadex":    (_mangadex_search, _mangadex_chapters, _mangadex_pages),
    "mangapark":   _mangapark,
    "mangakakalot": _mangakakalot,
    "manganato":   _manganato,
    "mangafox":    _mangafox,
    "batoto":      _batoto,
    "hitomi":      _hitomi,
    "webtoons":    _webtoons,
    "tappytoon":   _tappytoon,
    "mangaplus":   _mangaplus,
    "asurascans":  _asurascans,
    "reaperscans": _reaperscans,
    "flamescans":  _flamescans,
}


# Plugin overrides --------------------------------------------------------
def _load_plugins(plugins_dir: Path):
    if not plugins_dir.exists():
        return
    for f in plugins_dir.glob("*.py"):
        try:
            spec = importlib.util.spec_from_file_location(f"manga_plugin_{f.stem}", f)
            mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            if all(hasattr(mod, n) for n in ("search", "chapters", "pages")):
                SOURCES[f.stem] = (mod.search, mod.chapters, mod.pages)
        except Exception:
            pass


_load_plugins(Path(__file__).resolve().parent.parent / "plugins" / "manga")


# Aggregated search ------------------------------------------------------
def search_all(query: str, enabled: Dict[str, bool]) -> List[Dict]:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    out: List[Dict] = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fn[0], query): name
                for name, fn in SOURCES.items() if enabled.get(name, True)}
        for fut in as_completed(futs):
            try:
                out.extend(fut.result() or [])
            except Exception:
                pass
    return out


def get_chapters(source: str, url: str) -> List[Dict]:
    if source not in SOURCES:
        return []
    try:
        return SOURCES[source][1](url) or []
    except Exception:
        return []


def get_pages(source: str, chapter_url: str) -> List[str]:
    if source not in SOURCES:
        return []
    try:
        return SOURCES[source][2](chapter_url) or []
    except Exception:
        return []
