"""
Torrent source adapters. Each adapter returns a normalized list of dicts:
  { title, size, seeders, leechers, magnet, torrent_url, source, group, resolution,
    codec, audio, batch, episode, files, hash, page_url, date }
"""
from __future__ import annotations
import re, time, urllib.parse, html, json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Callable
import requests
from bs4 import BeautifulSoup
import feedparser

UA = {"User-Agent": "ANITorr/1.0 (+https://github.com/anitorr)"}

# ---------- helpers ----------
_RES_RE = re.compile(r"\b(2160p|1080p|720p|480p|360p|4k|uhd)\b", re.I)
_CODEC_RE = re.compile(r"\b(x265|x264|hevc|h\.?264|h\.?265|av1)\b", re.I)
_AUDIO_RE = re.compile(r"\b(flac|aac|opus|dts|ac3|eac3|truehd)\b", re.I)
_GROUP_RE = re.compile(r"^\s*\[([^\]]+)\]")
_BATCH_RE = re.compile(r"\b(batch|complete|s\d+|season\s*\d+|\d+\s*-\s*\d+|01-\d+)\b", re.I)
_EP_RE = re.compile(r"(?:-\s*|ep\s*|episode\s*|\be)(\d{1,4})\b", re.I)
_SIZE_RE = re.compile(r"([\d\.]+)\s*(GiB|MiB|KiB|GB|MB|KB|TB|TiB)", re.I)

def parse_tags(title: str) -> Dict:
    res = (_RES_RE.search(title) or [None, ""])[0] or ""
    res = res.lower().replace("4k", "2160p").replace("uhd", "2160p")
    codec = (_CODEC_RE.search(title) or [None, ""])[0] or ""
    audio = (_AUDIO_RE.search(title) or [None, ""])[0] or ""
    gm = _GROUP_RE.search(title)
    group = gm.group(1) if gm else ""
    batch = bool(_BATCH_RE.search(title))
    em = _EP_RE.search(title)
    episode = int(em.group(1)) if em else None
    return {"resolution": res, "codec": codec.lower(),
            "audio": audio.lower(), "group": group,
            "batch": batch, "episode": episode}

def size_to_bytes(s: str) -> int:
    if not s: return 0
    m = _SIZE_RE.search(s)
    if not m: return 0
    val = float(m.group(1)); unit = m.group(2).lower()
    mult = {"kib": 1024, "kb": 1000, "mib": 1024**2, "mb": 1000**2,
            "gib": 1024**3, "gb": 1000**3, "tib": 1024**4, "tb": 1000**4}
    return int(val * mult.get(unit, 1))

def _norm(item: dict, source: str) -> dict:
    tags = parse_tags(item.get("title", ""))
    item.update(tags)
    item.setdefault("source", source)
    item.setdefault("magnet", "")
    item.setdefault("torrent_url", "")
    item.setdefault("seeders", 0); item.setdefault("leechers", 0)
    item.setdefault("size_bytes", size_to_bytes(item.get("size", "")))
    return item

# ---------- Nyaa.si ----------
def fetch_nyaa(query: str, cors_proxy: str | None = None, limit: int = 75) -> List[Dict]:
    q = urllib.parse.quote_plus(query)
    base = "https://nyaa.si"
    url = f"{base}/?f=0&c=1_2&q={q}&s=seeders&o=desc"
    if cors_proxy:
        url = f"{cors_proxy.rstrip('/')}/proxy?url={urllib.parse.quote(url, safe='')}"
    try:
        r = requests.get(url, headers=UA, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")
    except Exception:
        return []
    out = []
    for tr in soup.select("table.torrent-list tbody tr")[:limit]:
        tds = tr.find_all("td")
        if len(tds) < 8: continue
        title_a = tds[1].find_all("a")[-1]
        title = title_a.get("title") or title_a.text.strip()
        page = base + title_a.get("href", "")
        links = tds[2].find_all("a")
        torrent_url = ""; magnet = ""
        for a in links:
            href = a.get("href", "")
            if href.endswith(".torrent"): torrent_url = base + href
            elif href.startswith("magnet:"): magnet = href
        size = tds[3].text.strip()
        date = tds[4].text.strip()
        seeders = int(tds[5].text.strip() or 0)
        leechers = int(tds[6].text.strip() or 0)
        out.append(_norm({
            "title": title, "page_url": page, "torrent_url": torrent_url,
            "magnet": magnet, "size": size, "date": date,
            "seeders": seeders, "leechers": leechers,
        }, "nyaa"))
    return out

# ---------- AniDex ----------
def fetch_anidex(query: str, **_) -> List[Dict]:
    q = urllib.parse.quote_plus(query)
    url = f"https://anidex.info/?q={q}&s=seeders&o=desc"
    try:
        r = requests.get(url, headers=UA, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")
    except Exception:
        return []
    out = []
    for tr in soup.select("table tbody tr")[:50]:
        a = tr.find("a", href=re.compile(r"^/torrent/"))
        if not a: continue
        title = a.get("title") or a.text.strip()
        page = "https://anidex.info" + a["href"]
        tds = tr.find_all("td")
        seeders = leechers = 0; size = ""
        for td in tds:
            t = td.text.strip()
            if _SIZE_RE.search(t) and not size: size = t
        try: seeders = int(tds[-3].text.strip())
        except Exception: pass
        try: leechers = int(tds[-2].text.strip())
        except Exception: pass
        magnet_a = tr.find("a", href=re.compile("^magnet:"))
        magnet = magnet_a["href"] if magnet_a else ""
        out.append(_norm({
            "title": title, "page_url": page, "magnet": magnet,
            "size": size, "seeders": seeders, "leechers": leechers,
        }, "anidex"))
    return out

# ---------- TokyoTosho RSS ----------
def fetch_tokyotosho(query: str, **_) -> List[Dict]:
    q = urllib.parse.quote_plus(query)
    url = f"https://www.tokyotosho.info/rss.php?filter=1&terms={q}"
    out = []
    try:
        f = feedparser.parse(url)
        for e in f.entries[:50]:
            magnet = ""
            for l in getattr(e, "links", []):
                if l.get("href", "").startswith("magnet:"):
                    magnet = l["href"]; break
            out.append(_norm({
                "title": e.title, "page_url": e.link, "magnet": magnet,
                "date": getattr(e, "published", ""), "size": "",
                "seeders": 0, "leechers": 0,
            }, "tokyotosho"))
    except Exception:
        pass
    return out

# ---------- SubsPlease ----------
def fetch_subsplease(query: str, **_) -> List[Dict]:
    try:
        r = requests.get("https://subsplease.org/api/?f=search&tz=UTC&s=" + urllib.parse.quote(query),
                         headers=UA, timeout=15)
        data = r.json() if r.headers.get("content-type","").startswith("application/json") else {}
    except Exception:
        return []
    out = []
    for show, info in (data or {}).items():
        for ep in info.get("downloads", []):
            for res, link in ep.items():
                if not isinstance(link, str): continue
                if link.startswith("magnet:") or link.endswith(".torrent"):
                    title = f"[SubsPlease] {info.get('show', show)} - {ep.get('episode','')} ({res})"
                    out.append(_norm({
                        "title": title,
                        "magnet": link if link.startswith("magnet:") else "",
                        "torrent_url": link if link.endswith(".torrent") else "",
                        "size": "", "seeders": 0, "leechers": 0,
                    }, "subsplease"))
    return out

# ---------- Erai-raws RSS ----------
def fetch_erai(query: str, **_) -> List[Dict]:
    url = "https://www.erai-raws.info/rss-1080-magnet/"
    q = query.lower()
    out = []
    try:
        f = feedparser.parse(url)
        for e in f.entries:
            if q in e.title.lower():
                magnet = ""
                for l in getattr(e, "links", []):
                    if l.get("href","").startswith("magnet:"):
                        magnet = l["href"]; break
                out.append(_norm({
                    "title": e.title, "page_url": e.link, "magnet": magnet,
                    "date": getattr(e, "published", ""),
                }, "erai-raws"))
    except Exception:
        pass
    return out

# ---------- AnimeTosho ----------
def fetch_animetosho(query: str, **_) -> List[Dict]:
    q = urllib.parse.quote_plus(query)
    url = f"https://animetosho.org/search?q={q}"
    try:
        r = requests.get(url, headers=UA, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")
    except Exception:
        return []
    out = []
    for div in soup.select("div.home_list_entry")[:50]:
        a = div.select_one("div.link a")
        if not a: continue
        title = a.text.strip()
        page = a["href"]
        size_el = div.select_one("div.size")
        size = size_el.text.strip() if size_el else ""
        magnet_a = div.find("a", href=re.compile("^magnet:"))
        magnet = magnet_a["href"] if magnet_a else ""
        torrent_a = div.find("a", href=re.compile(r"\.torrent$"))
        torrent_url = torrent_a["href"] if torrent_a else ""
        out.append(_norm({
            "title": title, "page_url": page, "size": size,
            "magnet": magnet, "torrent_url": torrent_url,
            "seeders": 0, "leechers": 0,
        }, "animetosho"))
    return out

# ---------- ShanaProject ----------
def fetch_shana(query: str, **_) -> List[Dict]:
    q = urllib.parse.quote_plus(query)
    url = f"https://www.shanaproject.com/search/?title={q}"
    try:
        r = requests.get(url, headers=UA, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")
    except Exception:
        return []
    out = []
    for row in soup.select(".release_row")[:50]:
        a = row.find("a")
        if not a: continue
        title = a.text.strip()
        page = "https://www.shanaproject.com" + a.get("href","")
        out.append(_norm({
            "title": title, "page_url": page, "size":"",
            "seeders": 0, "leechers": 0, "magnet": "", "torrent_url": page,
        }, "shanaproject"))
    return out

# ---------- Anirena ----------
def fetch_anirena(query: str, **_) -> List[Dict]:
    q = urllib.parse.quote_plus(query)
    url = f"https://www.anirena.com/?s={q}"
    try:
        r = requests.get(url, headers=UA, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")
    except Exception:
        return []
    out = []
    for li in soup.select("ul.releases li")[:50]:
        a = li.find("a", title=True)
        if not a: continue
        out.append(_norm({
            "title": a["title"], "page_url": a.get("href",""),
            "magnet": "", "torrent_url": "", "size":"",
            "seeders": 0, "leechers": 0,
        }, "anirena"))
    return out

# ---------- registry ----------
SOURCES: Dict[str, Callable] = {
    "nyaa": fetch_nyaa,
    "anidex": fetch_anidex,
    "tokyotosho": fetch_tokyotosho,
    "subsplease": fetch_subsplease,
    "erai-raws": fetch_erai,
    "animetosho": fetch_animetosho,
    "shanaproject": fetch_shana,
    "anirena": fetch_anirena,
}

# ---------- DDL aggregator placeholders ----------
DDL_SOURCES = ["animepahe","gogoanime","nineanime","zoro","animixplay",
               "animekisa","kissanime","twist","marin","allanime"]

def fetch_ddl(name: str, query: str) -> List[Dict]:
    # Lightweight HEAD-style stub that emits a streaming link card.
    # Real implementations of these endpoints change weekly; this scaffolding
    # gives a uniform interface plugins can override.
    return [{
        "title": f"[{name}] {query} — streaming page",
        "page_url": f"https://{name}.example/search?q={urllib.parse.quote(query)}",
        "source": name, "is_ddl": True, "seeders": 0, "leechers": 0,
        "size": "", "size_bytes": 0, "magnet": "", "torrent_url": "",
        "resolution": "", "group": "", "batch": False,
    }]

def aggregate(query: str, enabled: Dict[str, bool], cors_proxy: str | None,
              ddl_enabled: Dict[str, bool], min_results: int = 5,
              max_threads: int = 12) -> List[Dict]:
    results: List[Dict] = []
    tasks = []
    with ThreadPoolExecutor(max_workers=max_threads) as ex:
        for name, fn in SOURCES.items():
            if not enabled.get(name, True): continue
            tasks.append(ex.submit(fn, query, cors_proxy=cors_proxy))
        for fut in as_completed(tasks):
            try: results.extend(fut.result() or [])
            except Exception: pass
    if len(results) < min_results:
        with ThreadPoolExecutor(max_workers=max_threads) as ex:
            tasks = [ex.submit(fetch_ddl, n, query)
                     for n, ok in ddl_enabled.items() if ok]
            for fut in as_completed(tasks):
                try: results.extend(fut.result() or [])
                except Exception: pass
    # dedupe by title+source
    seen = set(); dedup = []
    for r in results:
        key = (r.get("title",""), r.get("source",""))
        if key in seen: continue
        seen.add(key); dedup.append(r)
    return dedup
