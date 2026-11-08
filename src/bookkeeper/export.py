"""Building TXT, FB2 and EPUB files for your e-reader.

A download fetches every free chapter of a book at the site's normal polite pace (it stops at the first paid
chapter), then writes the file into data/downloads."""
import base64
import html
import re
import uuid
import zipfile
from datetime import date
from pathlib import Path

from . import config, db
from . import tags as T
from .db import jdump, jload, now
from .http import Blocked, NotFound, Stopped

_BAD_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_BAD_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def _x(text: str) -> str:
    return html.escape(_BAD_XML.sub("", text or ""), quote=True)


def safe_filename(name: str, ext: str) -> str:
    base = _BAD_NAME.sub(" ", name).strip().rstrip(". ")
    base = re.sub(r"\s+", " ", base)[:150] or "book"
    return f"{base}.{ext}"


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in (text or "").split("\n") if p.strip()]


class BookData:
    def __init__(self, title: str, authors: list[str], description: str | None, lang: str | None,
                 url: str, tags: list[str], chapters: list[tuple[str, str]], cover: tuple[bytes, str] | None):
        self.title = title
        self.authors = authors or ["Unknown"]
        self.description = description or ""
        self.lang = lang or "ru"
        self.url = url
        self.tags = tags
        self.chapters = chapters          # [(chapter title, plain text)]
        self.cover = cover                # (bytes, mime type) or None


def build_txt(b: BookData) -> bytes:
    out = [b.title, ", ".join(b.authors), b.url, ""]
    if b.description:
        out += [b.description, ""]
    for title, text in b.chapters:
        out += ["", "", title, ""]
        out += _paragraphs(text)
    return ("﻿" + "\r\n".join(out) + "\r\n").encode("utf-8")


FB2_GENRES = [("litrpg", "sf_litrpg"), ("romantic-fantasy", "love_sf"), ("cyberpunk", "sf_cyberpunk"),
              ("space-opera", "sf_space"), ("alt-history", "sf_history"), ("apocalypse", "sf_postapocalyptic"),
              ("horror", "sf_horror"), ("comedy", "humor_fantasy"), ("fantasy", "sf_fantasy"), ("sci-fi", "sf"),
              ("romance", "love"), ("mystery", "detective"), ("thriller", "thriller"), ("historical", "prose_history"),
              ("adventure", "adventure"), ("fanfiction", "fanfiction")]


def _fb2_author(name: str) -> str:
    parts = name.split()
    if len(parts) == 2:
        return f"<author><first-name>{_x(parts[0])}</first-name><last-name>{_x(parts[1])}</last-name></author>"
    if len(parts) == 3:
        return (f"<author><first-name>{_x(parts[1])}</first-name><middle-name>{_x(parts[2])}</middle-name>"
                f"<last-name>{_x(parts[0])}</last-name></author>")
    return f"<author><nickname>{_x(name)}</nickname></author>"


def build_fb2(b: BookData) -> bytes:
    genres = [g for t, g in FB2_GENRES if t in b.tags][:3] or ["prose_contemporary"]
    cover_ref = '<coverpage><image l:href="#cover.jpg"/></coverpage>' if b.cover else ""
    annotation = "".join(f"<p>{_x(p)}</p>" for p in _paragraphs(b.description)) or "<p></p>"
    keywords = ", ".join(T.info(t)["label_ru"] or T.info(t)["label"] for t in b.tags[:30])
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:l="http://www.w3.org/1999/xlink">',
        "<description><title-info>",
        *[f"<genre>{g}</genre>" for g in genres],
        *[_fb2_author(a) for a in b.authors],
        f"<book-title>{_x(b.title)}</book-title>",
        f"<annotation>{annotation}</annotation>",
        f"<keywords>{_x(keywords)}</keywords>" if keywords else "",
        f"<lang>{_x(b.lang)}</lang>",
        cover_ref,
        "</title-info><document-info><author><nickname>Bookkeeper</nickname></author>",
        f"<program-used>Bookkeeper</program-used><date>{date.today().isoformat()}</date>",
        f"<src-url>{_x(b.url)}</src-url><id>{uuid.uuid4()}</id><version>1.0</version>",
        "</document-info></description>",
        f"<body><title><p>{_x(b.title)}</p></title>",
    ]
    for title, text in b.chapters:
        paras = "".join(f"<p>{_x(p)}</p>" for p in _paragraphs(text)) or "<empty-line/>"
        parts.append(f"<section><title><p>{_x(title)}</p></title>{paras}</section>")
    parts.append("</body>")
    if b.cover:
        data, mime = b.cover
        parts.append(f'<binary id="cover.jpg" content-type="{mime}">{base64.b64encode(data).decode()}</binary>')
    parts.append("</FictionBook>")
    return "\n".join(p for p in parts if p).encode("utf-8")


CSS = """body { font-family: serif; line-height: 1.5; margin: 0 5%; }
h1, h2 { font-family: sans-serif; text-align: center; margin: 1.5em 0 1em; }
p { text-indent: 1.5em; margin: 0 0 0.3em; text-align: justify; }
p.meta { text-indent: 0; text-align: center; }
img.cover { display: block; max-width: 100%; max-height: 100%; margin: 0 auto; }
"""


def _xhtml(title: str, body: str, lang: str) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
            f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
            f'lang="{lang}" xml:lang="{lang}"><head><meta charset="utf-8"/><title>{_x(title)}</title>'
            f'<link rel="stylesheet" type="text/css" href="style.css"/></head><body>{body}</body></html>')


def build_epub(b: BookData) -> bytes:
    import io
    book_id = f"urn:uuid:{uuid.uuid4()}"
    lang = b.lang
    buf = io.BytesIO()
    z = zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED)
    z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
    z.writestr("META-INF/container.xml",
               '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
               '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
               '</rootfiles></container>')
    z.writestr("OEBPS/style.css", CSS)
    manifest = ['<item id="css" href="style.css" media-type="text/css"/>',
                '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>']
    spine = []
    if b.cover:
        data, mime = b.cover
        ext = "png" if "png" in mime else "jpg"
        z.writestr(f"OEBPS/cover.{ext}", data)
        manifest.append(f'<item id="cover-image" href="cover.{ext}" media-type="{mime}" properties="cover-image"/>')
        z.writestr("OEBPS/cover.xhtml", _xhtml(b.title, f'<img class="cover" src="cover.{ext}" alt="cover"/>', lang))
        manifest.append('<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>')
        spine.append('<itemref idref="cover"/>')
    title_body = (f"<h1>{_x(b.title)}</h1><p class=\"meta\">{_x(', '.join(b.authors))}</p>"
                  + "".join(f"<p>{_x(p)}</p>" for p in _paragraphs(b.description)))
    z.writestr("OEBPS/title.xhtml", _xhtml(b.title, title_body, lang))
    manifest.append('<item id="title" href="title.xhtml" media-type="application/xhtml+xml"/>')
    spine.append('<itemref idref="title"/>')
    nav_items, ncx_points = [], []
    for i, (title, text) in enumerate(b.chapters, 1):
        name = f"ch{i:05d}.xhtml"
        body = f"<h2>{_x(title)}</h2>" + "".join(f"<p>{_x(p)}</p>" for p in _paragraphs(text))
        z.writestr(f"OEBPS/{name}", _xhtml(title, body, lang))
        manifest.append(f'<item id="c{i}" href="{name}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="c{i}"/>')
        nav_items.append(f'<li><a href="{name}">{_x(title)}</a></li>')
        ncx_points.append(f'<navPoint id="n{i}" playOrder="{i}"><navLabel><text>{_x(title)}</text></navLabel>'
                          f'<content src="{name}"/></navPoint>')
    z.writestr("OEBPS/nav.xhtml", _xhtml("Contents", f'<nav epub:type="toc" id="toc"><h2>Contents</h2><ol>'
                                                    f'{"".join(nav_items)}</ol></nav>', lang))
    z.writestr("OEBPS/toc.ncx",
               '<?xml version="1.0" encoding="utf-8"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">'
               f'<head><meta name="dtb:uid" content="{book_id}"/></head><docTitle><text>{_x(b.title)}</text></docTitle>'
               f'<navMap>{"".join(ncx_points)}</navMap></ncx>')
    creators = "".join(f"<dc:creator>{_x(a)}</dc:creator>" for a in b.authors)
    subjects = "".join(f"<dc:subject>{_x(T.info(t)['label'])}</dc:subject>" for t in b.tags[:20])
    cover_meta = '<meta name="cover" content="cover-image"/>' if b.cover else ""
    z.writestr("OEBPS/content.opf",
               '<?xml version="1.0" encoding="utf-8"?>'
               '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">'
               '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
               f'<dc:identifier id="bookid">{book_id}</dc:identifier><dc:title>{_x(b.title)}</dc:title>'
               f'{creators}<dc:language>{_x(lang)}</dc:language>'
               f'<dc:description>{_x(b.description[:2000])}</dc:description>{subjects}'
               f'<dc:source>{_x(b.url)}</dc:source>'
               f'<meta property="dcterms:modified">{now()}</meta>{cover_meta}</metadata>'
               f'<manifest>{"".join(manifest)}</manifest><spine toc="ncx">{"".join(spine)}</spine></package>')
    z.close()
    return buf.getvalue()


BUILDERS = {"txt": build_txt, "fb2": build_fb2, "epub": build_epub}


def _update(job_id: int, **fields):
    db.conn().execute(f"UPDATE downloads SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",
                      [*fields.values(), job_id])


def _image_mime(data: bytes) -> str:
    return ("image/png" if data[:4] == b"\x89PNG" else "image/webp" if data[8:12] == b"WEBP"
            else "image/gif" if data[:3] == b"GIF" else "image/jpeg")


def cover_cache_path(url: str) -> Path:
    import hashlib
    return config.CACHE_DIR / "covers" / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".img")


def _fetch_cover(url: str | None, referer: str):
    """The cover from the interface's cache, or fetched now. A missing cover never stops a download."""
    if not url:
        return None
    path = cover_cache_path(url)
    try:
        if not path.exists():
            import httpx
            r = httpx.get(url, headers={"User-Agent": config.USER_AGENT, "Referer": referer}, timeout=20,
                          follow_redirects=True)
            if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
                return None
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(r.content)
        data = path.read_bytes()
        mime = _image_mime(data)
        # Many e-readers only show JPEG/PNG covers.
        return (data, mime) if mime in ("image/jpeg", "image/png") and len(data) > 500 else None
    except Exception:
        return None


def run_download(worker, job) -> None:
    """Runs inside the site's worker thread (so it shares the site's pace and browser)."""
    c = db.conn()
    row = c.execute("SELECT * FROM books WHERE id=?", (job["book_id"],)).fetchone()
    fmt = job["fmt"]
    options = jload(job["options"], {})
    _update(job["id"], state="running", error=None)
    book = {"id": row["id"], "sid": row["sid"], "extra": jload(row["extra"], {})}
    authors = jload(row["authors"], [])
    filename = safe_filename(f"{', '.join(authors[:2])} - {row['title']}" if authors else row["title"], fmt)
    config.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        site = worker.site
        if fmt in site.native_formats and not options.get("rebuild"):
            res = site.native_download(book, fmt)
            if res:
                data, _name = res
                path = config.DOWNLOADS_DIR / filename
                path.write_bytes(data)
                _update(job["id"], state="done", file=path.name, progress=1, total=1, finished_at=now())
                return
        def listing(n: int):  # long books: the chapter list is built (and read) chapter by chapter
            worker.activity = f"downloading «{row['title'][:30]}»: {n} chapters so far"
            _update(job["id"], progress=n)
        site.progress = listing
        try:
            chapters = site.chapters(book)
        finally:
            site.progress = None
        start = max(0, int(options.get("from", 1)) - 1)
        end = int(options["to"]) if options.get("to") else len(chapters)
        chapters = chapters[start:end]
        _update(job["id"], total=len(chapters))
        texts, skipped = [], 0
        for i, ch in enumerate(chapters):
            worker.activity = f"downloading «{row['title'][:30]}» {i + 1}/{len(chapters)}"
            text = ""
            if ch.free:
                try:
                    text = site.chapter_text(book, ch)
                except NotFound:
                    text = ""
                except (Blocked, Stopped):
                    raise
                except Exception:
                    text = ""
            if text.strip():
                texts.append((ch.title, text))
            else:
                skipped += 1
                if texts and options.get("stop_at_locked", True):
                    break  # the first locked chapter: the rest is paid too
            _update(job["id"], progress=i + 1)
        if not texts:
            raise RuntimeError("no chapters could be read (paid, or the site needs a login)")
        tag_ids = [r[0] for r in c.execute("SELECT DISTINCT tag FROM book_tags WHERE book_id=? AND source != 'maybe'", (row["id"],))]
        data = BookData(row["title"], authors, row["description"], row["lang"], row["url"], tag_ids, texts,
                        _fetch_cover(row["cover"], site.home + "/"))
        path = config.DOWNLOADS_DIR / filename
        path.write_bytes(BUILDERS[fmt](data))
        note = f"{len(texts)} chapters" + (f", {skipped} not available" if skipped else "")
        _update(job["id"], state="done", file=path.name, finished_at=now(), error=None,
                options=jdump({**options, "note": note}))
    except Stopped:
        _update(job["id"], state="queued")
        raise
    except Blocked as e:
        _update(job["id"], state="error", error=f"the site blocked the download: {e}", finished_at=now())
        raise
    except Exception as e:
        _update(job["id"], state="error", error=f"{type(e).__name__}: {e}"[:300], finished_at=now())


def queue_download(book_id: int, fmt: str, options: dict | None = None) -> int:
    if fmt not in BUILDERS:
        raise ValueError(f"unknown format {fmt}")
    cur = db.conn().execute("INSERT INTO downloads(book_id, fmt, state, options, created_at) VALUES(?,?,?,?,?)",
                            (book_id, fmt, "queued", jdump(options or {}), now()))
    return cur.lastrowid


def file_path(job_id: int) -> Path | None:
    row = db.conn().execute("SELECT file FROM downloads WHERE id=? AND state='done'", (job_id,)).fetchone()
    if not row or not row["file"]:
        return None
    p = config.DOWNLOADS_DIR / row["file"]
    return p if p.exists() else None
