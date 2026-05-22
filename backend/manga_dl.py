"""
Manga downloader: fetches pages, optionally auto-crops white margins, and packages
as CBZ / ZIP / EPUB / PDF with Apple-Books-compatible OPF metadata.

Designed to work with the lightest possible dependencies. PIL is optional —
without it, auto-crop is silently skipped.
"""
from __future__ import annotations
import io, os, re, time, zipfile, uuid, html, requests, threading
from pathlib import Path
from typing import List, Dict, Callable

UA = {"User-Agent": "Mozilla/5.0 (ANITorr manga-dl)"}

# Optional Pillow (auto-crop only)
try:
    from PIL import Image
    HAS_PIL = True
except Exception:
    HAS_PIL = False


def _sanitize(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|]", "_", name).strip()
    return (name or "untitled")[:140]


def _fetch_bytes(url: str) -> bytes | None:
    try:
        r = requests.get(url, headers=UA, timeout=30)
        return r.content if r.status_code == 200 else None
    except Exception:
        return None


def _autocrop(data: bytes) -> bytes:
    """Trim near-white borders. Returns original bytes on any failure."""
    if not HAS_PIL or not data:
        return data
    try:
        img = Image.open(io.BytesIO(data))
        if img.mode == "P":
            img = img.convert("RGB")
        # Threshold to mask near-white pixels
        gray = img.convert("L")
        bbox = gray.point(lambda p: 0 if p > 240 else 255).getbbox()
        if not bbox or bbox == (0, 0, img.width, img.height):
            return data
        cropped = img.crop(bbox)
        buf = io.BytesIO()
        fmt = (img.format or "JPEG").upper()
        if fmt not in ("JPEG", "PNG", "WEBP"):
            fmt = "JPEG"
        cropped.save(buf, format=fmt, quality=88)
        return buf.getvalue()
    except Exception:
        return data


# ------------------------------------------------------------------ writers

def _write_zip_or_cbz(path: Path, pages: List[Dict], progress: Callable | None = None):
    """pages: list of {ext, data}. Filenames pad to 4 digits."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        for i, p in enumerate(pages):
            z.writestr(f"{i+1:04d}.{p['ext']}", p["data"])
            if progress:
                progress(i + 1, len(pages))


def _write_pdf(path: Path, pages: List[Dict], progress: Callable | None = None):
    """Pure-Python PDF: one page per image. Falls back to PIL when available,
    otherwise writes a minimal valid PDF with embedded JPEGs."""
    if HAS_PIL:
        try:
            imgs = []
            for p in pages:
                im = Image.open(io.BytesIO(p["data"])).convert("RGB")
                imgs.append(im)
            if not imgs:
                return
            imgs[0].save(path, "PDF", save_all=True, append_images=imgs[1:])
            if progress:
                progress(len(pages), len(pages))
            return
        except Exception:
            pass
    # Minimal JPEG-only PDF
    objs = ["%PDF-1.4\n%\xff\xff\xff\xff\n".encode("latin-1", "ignore")]
    refs, offs = [], []
    def add(b):
        offs.append(sum(len(o) for o in objs))
        objs.append(b)
        return len(refs) + 1

    # placeholder pages container
    pages_id = add(b"")  # will rewrite
    refs.append(pages_id)
    page_ids = []
    for i, p in enumerate(pages):
        if p["ext"].lower() not in ("jpg", "jpeg"):
            continue
        img_data = p["data"]
        w, h = 800, 1200
        if HAS_PIL:
            try:
                im = Image.open(io.BytesIO(img_data)); w, h = im.size
            except Exception:
                pass
        img_id = add(f"{len(objs)} 0 obj\n<< /Type /XObject /Subtype /Image /Width {w} /Height {h} "
                     f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(img_data)} >>\n"
                     "stream\n".encode() + img_data + b"\nendstream\nendobj\n")
        content = f"q\n{w} 0 0 {h} 0 0 cm\n/Im0 Do\nQ\n".encode()
        cont_id = add(f"{len(objs)} 0 obj\n<< /Length {len(content)} >>\nstream\n".encode()
                      + content + b"\nendstream\nendobj\n")
        page_id = add(f"{len(objs)} 0 obj\n<< /Type /Page /Parent {pages_id} 0 R "
                      f"/MediaBox [0 0 {w} {h}] /Contents {cont_id} 0 R "
                      f"/Resources << /XObject << /Im0 {img_id} 0 R >> >> >>\nendobj\n".encode())
        page_ids.append(page_id)
        if progress:
            progress(i + 1, len(pages))

    kids = " ".join(f"{i} 0 R" for i in page_ids)
    objs[1] = (f"{pages_id} 0 obj\n<< /Type /Pages /Count {len(page_ids)} "
               f"/Kids [{kids}] >>\nendobj\n").encode()
    catalog_id = add(f"{len(objs)} 0 obj\n<< /Type /Catalog /Pages {pages_id} 0 R >>\nendobj\n".encode())

    # rebuild offsets
    blob = objs[0]
    offs = []
    for o in objs[1:]:
        offs.append(len(blob))
        blob += o
    xref_off = len(blob)
    blob += f"xref\n0 {len(objs)}\n0000000000 65535 f \n".encode()
    for o in offs:
        blob += f"{o:010d} 00000 n \n".encode()
    blob += (f"trailer\n<< /Size {len(objs)} /Root {catalog_id} 0 R >>\n"
             f"startxref\n{xref_off}\n%%EOF\n").encode()
    path.write_bytes(blob)


# ---------------------------------------------------------------- EPUB
def _write_epub(path: Path, title: str, author: str, language: str,
                pages: List[Dict], cover_idx: int = 0,
                identifier: str = "", series: str = "",
                progress: Callable | None = None):
    """
    Minimal EPUB 3 with all the Apple-Books-recognised metadata fields:
      - dc:identifier (unique-identifier)
      - dc:title, dc:creator, dc:language, dc:date, dc:publisher
      - calibre:series, calibre:series_index (recognised by Apple Books too)
      - <meta property="ibooks:specified-fonts">true</meta>
      - rendition:layout pre-paginated
    """
    identifier = identifier or f"urn:uuid:{uuid.uuid4()}"
    today = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = []
    spine = []
    nav_items = []

    cover_ext = pages[cover_idx]["ext"] if pages else "jpg"
    manifest.append(f'<item id="cover-img" href="images/cover.{cover_ext}" '
                    f'media-type="image/{ "jpeg" if cover_ext in ("jpg","jpeg") else cover_ext}" '
                    f'properties="cover-image"/>')
    for i, p in enumerate(pages):
        ext = p["ext"]
        media = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
        manifest.append(f'<item id="img{i}" href="images/{i+1:04d}.{ext}" media-type="{media}"/>')
        manifest.append(f'<item id="p{i}" href="xhtml/p{i+1:04d}.xhtml" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="p{i}"/>')
        nav_items.append(f'<li><a href="xhtml/p{i+1:04d}.xhtml">Page {i+1}</a></li>')

    nav = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<html xmlns="http://www.w3.org/1999/xhtml" '
           'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Nav</title></head><body>'
           f'<nav epub:type="toc"><h1>{html.escape(title)}</h1><ol>'
           + "".join(nav_items) + '</ol></nav></body></html>')

    series_meta = ""
    if series:
        series_meta = (f'<meta name="calibre:series" content="{html.escape(series)}"/>'
                       '<meta name="calibre:series_index" content="1"/>')

    opf = f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid"
         prefix="rendition: http://www.idpf.org/vocab/rendition/# ibooks: http://vocabulary.itunes.apple.com/rdf/ibooks/vocabulary-extensions-1.0/">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{identifier}</dc:identifier>
    <dc:title>{html.escape(title)}</dc:title>
    <dc:creator>{html.escape(author or "Unknown")}</dc:creator>
    <dc:language>{language or "en"}</dc:language>
    <dc:date>{today}</dc:date>
    <dc:publisher>ANITorr</dc:publisher>
    <meta property="dcterms:modified">{today}</meta>
    <meta property="rendition:layout">pre-paginated</meta>
    <meta property="rendition:orientation">portrait</meta>
    <meta property="rendition:spread">auto</meta>
    <meta property="ibooks:specified-fonts">true</meta>
    <meta name="cover" content="cover-img"/>
    {series_meta}
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    {"".join(manifest)}
  </manifest>
  <spine page-progression-direction="rtl">
    {"".join(spine)}
  </spine>
</package>'''

    container = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                 'media-type="application/oebps-package+xml"/></rootfiles></container>')

    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav, compress_type=zipfile.ZIP_DEFLATED)
        for i, p in enumerate(pages):
            z.writestr(f"OEBPS/images/{i+1:04d}.{p['ext']}", p["data"], compress_type=zipfile.ZIP_STORED)
            html_page = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
                         '<html xmlns="http://www.w3.org/1999/xhtml"><head><meta charset="utf-8"/>'
                         f'<title>Page {i+1}</title></head>'
                         '<body style="margin:0;padding:0;text-align:center">'
                         f'<img src="../images/{i+1:04d}.{p["ext"]}" '
                         'style="width:100%;height:auto"/></body></html>')
            z.writestr(f"OEBPS/xhtml/p{i+1:04d}.xhtml", html_page, compress_type=zipfile.ZIP_DEFLATED)
            if progress:
                progress(i + 1, len(pages))
        z.writestr(f"OEBPS/images/cover.{cover_ext}", pages[cover_idx]["data"]
                   if pages else b"", compress_type=zipfile.ZIP_STORED)


# ----------------------------------------------------------- public API

JOBS: Dict[str, Dict] = {}
_LOCK = threading.Lock()


def start_job(title: str, source: str, page_urls: List[str], fmt: str,
              out_dir: Path, *, author: str = "", language: str = "en",
              autocrop: bool = False, series: str = "") -> str:
    """Starts a background download/package job; returns job_id."""
    job_id = uuid.uuid4().hex[:12]
    with _LOCK:
        JOBS[job_id] = {"id": job_id, "title": title, "source": source,
                        "fmt": fmt, "total": len(page_urls), "done": 0,
                        "status": "queued", "path": "", "ts": int(time.time()),
                        "error": ""}

    def worker():
        try:
            JOBS[job_id]["status"] = "downloading"
            pages = []
            for i, u in enumerate(page_urls):
                data = _fetch_bytes(u)
                if not data:
                    continue
                if autocrop:
                    data = _autocrop(data)
                ext = (re.search(r"\.(jpe?g|png|webp)(\?|$)", u, re.I) or [None, "jpg"])[1].lower()
                if ext == "jpeg":
                    ext = "jpg"
                pages.append({"ext": ext, "data": data})
                with _LOCK:
                    JOBS[job_id]["done"] = i + 1
            if not pages:
                with _LOCK:
                    JOBS[job_id]["status"] = "error"; JOBS[job_id]["error"] = "no pages downloaded"
                return

            out_dir.mkdir(parents=True, exist_ok=True)
            base = out_dir / _sanitize(title)
            JOBS[job_id]["status"] = "packaging"
            if fmt == "cbz":
                p = base.with_suffix(".cbz"); _write_zip_or_cbz(p, pages)
            elif fmt == "zip":
                p = base.with_suffix(".zip"); _write_zip_or_cbz(p, pages)
            elif fmt == "pdf":
                p = base.with_suffix(".pdf"); _write_pdf(p, pages)
            elif fmt == "epub":
                p = base.with_suffix(".epub")
                _write_epub(p, title=title, author=author, language=language,
                            pages=pages, series=series or title)
            else:
                with _LOCK:
                    JOBS[job_id]["status"] = "error"; JOBS[job_id]["error"] = "bad fmt"
                return
            with _LOCK:
                JOBS[job_id]["status"] = "done"
                JOBS[job_id]["path"] = str(p)
        except Exception as e:
            with _LOCK:
                JOBS[job_id]["status"] = "error"; JOBS[job_id]["error"] = str(e)

    threading.Thread(target=worker, daemon=True).start()
    return job_id


def get_job(job_id: str) -> Dict:
    return JOBS.get(job_id, {})


def list_jobs() -> List[Dict]:
    with _LOCK:
        return sorted(JOBS.values(), key=lambda j: j["ts"], reverse=True)


def download_by_url(url: str, fmt: str, out_dir: Path, *,
                    title: str = "", autocrop: bool = False) -> str:
    """For ad-hoc URL → single chapter download. Tries every source until one
    yields pages."""
    from . import manga_sources as ms
    pages_urls = []
    source = "url"
    for name, fns in ms.SOURCES.items():
        try:
            p = fns[2](url)
            if p:
                pages_urls = p; source = name; break
        except Exception:
            continue
    if not pages_urls:
        # last resort: HTML scrape via simple adapter
        try:
            pages_urls = ms._build_simple("adhoc", url, "a")[2](url)
        except Exception:
            pass
    if not pages_urls:
        raise ValueError("no pages found at " + url)
    title = title or url.rstrip("/").split("/")[-1].replace("-", " ").title()
    return start_job(title=title, source=source, page_urls=pages_urls,
                     fmt=fmt, out_dir=out_dir, autocrop=autocrop)
