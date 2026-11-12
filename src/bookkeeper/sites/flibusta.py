"""Flibusta: a big library of published books (mostly Russian), in FB2.

Listing, in three steps:
1. Flibusta offers its whole catalog as one file (catalog.zip, about 30 MB: title, authors, series, language and
   year of every book). Bookkeeper keeps it as a small database in its cache and lists every book from it, in the
   languages you chose, many books at a time (no requests to the site while doing so).
2. Then it reads the genre pages (275 genres, a few dozen books per page) to give every book its genres.
3. Later passes read the week's new arrivals (OPDS feed, with genres and descriptions), and the catalog file
   again once a month for anything missed.
Details (description, size, series, genres): each book's own page, a few at a time in the background.
Text for narration analysis: the online reader page, of which we read only the first ~250 KB.
Downloads: the site's own FB2 / EPUB files."""
import html as _html
import io
import os
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
import zipfile

from .. import config
from ..analysis.text import clean_text, html_to_text
from ..http import NotFound
from .base import BookInfo, Site, SiteError

NS = {"a": "http://www.w3.org/2005/Atom", "dc": "http://purl.org/dc/terms/"}
_ID = re.compile(r"^/b/(\d+)$")
_FOOTER = re.compile(r"(Формат:|Язык:|Размер:|Серия:|Год издания:|Перевод:).*$", re.S)
_SIZE = re.compile(r"Размер:\s*([\d.,]+)\s*(Kb|Mb|Кб|Мб)", re.I)
_SERIES = re.compile(r'Все книги серии "(.+)"')
_FORMAT = re.compile(r"\s*\((fb2|epub|pdf|djvu|doc|docx|txt|rtf|html?|mobi|azw3?)\)\s*$", re.I)

CATALOG_DAYS = 30          # read the catalog file again after this many days
CATALOG_BATCH = 2000       # books per batch from the catalog file
GENRE_PAGES_PER_STEP = 8   # genre pages read in one go (that pass is some 25,000 pages)
DEFAULT_LANGUAGES = "ru, uk, be, en"


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


class Flibusta(Site):
    id = "flibusta"
    name = "Flibusta"
    home = "https://flibusta.site"
    lang = "ru"
    min_interval = 1.5
    note = ("Published books. Lists the whole library (over 700,000 books) from Flibusta's catalog file, then adds "
            "their genres page by page; descriptions follow in the background. Downloads use Flibusta's own files.")
    native_formats = ("fb2", "epub")
    state_version = 2  # 0.4.4: the whole catalog instead of the week's new arrivals
    listing_first = True  # book pages take seconds each: list and tag everything first
    newest_first = True
    extra_settings = {"languages": {"label": "Languages to collect (two-letter codes separated by commas; empty: all)",
                                    "default": DEFAULT_LANGUAGES}}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.base = (self.settings.get("base") or self.home).rstrip("/")

    def _languages(self) -> list[str]:
        raw = self.settings.get("languages")
        raw = DEFAULT_LANGUAGES if raw is None else str(raw)
        return sorted({x.strip().lower()[:2] for x in re.split(r"[\s,;]+", raw) if x.strip()})

    # ---------------------------------------------------------------- the week's new arrivals (OPDS)
    def _entry(self, e: ET.Element) -> BookInfo | None:
        book_id = None
        cover = None
        series = None
        for link in e.findall("a:link", NS):
            href, rel = link.get("href", ""), link.get("rel", "")
            m = _ID.match(href)
            if m and rel == "alternate":
                book_id = m.group(1)
            elif rel == "http://opds-spec.org/image":
                cover = self.base + href if href.startswith("/") else href
            elif rel == "related" and (s := _SERIES.match(link.get("title", ""))):
                series = s.group(1)
        if not book_id:
            return None
        title = (e.findtext("a:title", "", NS) or "").strip()
        authors = [(a.findtext("a:name", "", NS) or "").strip() for a in e.findall("a:author", NS)]
        genres = [c.get("label") or c.get("term") for c in e.findall("a:category", NS)]
        lang = (e.findtext("dc:language", "", NS) or "").strip() or None
        fmt = (e.findtext("dc:format", "", NS) or "").strip()
        content = e.findtext("a:content", "", NS) or ""
        size_m = _SIZE.search(content)
        words = None
        if size_m:
            kb = float(size_m.group(1).replace(",", "."))
            kb *= 1024 if size_m.group(2).lower() in ("mb", "мб") else 1
            words = int(kb * 58)  # rough: FB2 kilobytes to words of Russian text
        description = clean_text(html_to_text(_FOOTER.sub("", content)))
        translated = "Перевод:" in content or None
        return BookInfo(
            sid=book_id, url=f"{self.base}/b/{book_id}", title=title or f"#{book_id}",
            authors=[a for a in authors if a], description=description or None, cover=cover,
            lang=lang, status="completed", words=words, is_translation=translated,
            updated_at=(e.findtext("a:updated", "", NS) or "")[:10] or None,
            tags=[g for g in genres if g], extra={"format": fmt, "series": series}, complete=True,
        )

    def _feed(self, page: int) -> tuple[list[BookInfo], bool]:
        p = self.http.get(f"{self.base}/opds/new/{page}/new", retries=5)
        root = ET.fromstring(p.content)
        books = [b for b in (self._entry(e) for e in root.findall("a:entry", NS)) if b]
        has_next = any(link.get("rel") == "next" for link in root.findall("a:link", NS))
        return books, has_next

    def _new_arrivals(self):
        for page in range(60):
            self.batch_offline = False
            self.discover_activity = "reading the week's new arrivals"
            books, has_next = self._feed(page)
            if books:
                yield books
            if not has_next:
                return

    # ---------------------------------------------------------------- the catalog file
    def _catalog_path(self):
        return config.CACHE_DIR / "flibusta_catalog.db"

    def _load_catalog(self) -> None:
        """Download Flibusta's catalog file and keep it as a small database: one row per book and author."""
        self.batch_offline = False
        self.discover_activity = "downloading Flibusta's catalog of every book (about 30 MB)"
        p = self.http.get(f"{self.base}/catalog/catalog.zip", retries=5)
        if p.content[:2] != b"PK":
            raise SiteError("Flibusta's catalog file isn't a zip any more (did the site change it?)")
        path = self._catalog_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.unlink(missing_ok=True)
        con = sqlite3.connect(tmp)
        try:
            con.execute("CREATE TABLE line(id INTEGER, author TEXT, title TEXT, subtitle TEXT, lang TEXT, year TEXT, "
                        "series TEXT)")
            rows = []
            with zipfile.ZipFile(io.BytesIO(p.content)) as z:
                name = next((n for n in z.namelist() if n.lower().endswith(".txt")), None)
                if not name:
                    raise SiteError("Flibusta's catalog file has no catalog in it")
                with z.open(name) as f:
                    # Last name;First name;Middle name;Title;Subtitle;Language;Year;Series;ID
                    for raw in io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace"):
                        parts = raw.rstrip("\r\n").split(";")
                        if len(parts) < 9 or not parts[-1].strip().isdigit():
                            continue  # the header, or a broken line
                        author = " ".join(x.strip() for x in (parts[1], parts[2], parts[0]) if x.strip())
                        rows.append((int(parts[-1]), author, ";".join(parts[3:-5]).strip(), parts[-5].strip(),
                                     parts[-4].strip().lower()[:2], parts[-3].strip(), parts[-2].strip()))
                        if len(rows) >= 50000:
                            con.executemany("INSERT INTO line VALUES(?,?,?,?,?,?,?)", rows)
                            rows = []
            con.executemany("INSERT INTO line VALUES(?,?,?,?,?,?,?)", rows)
            con.execute("CREATE INDEX line_id ON line(id)")
            con.commit()
        finally:
            con.close()
        os.replace(tmp, path)

    def _catalog_books(self, after: int, langs: list[str], limit: int) -> list[BookInfo]:
        con = sqlite3.connect(self._catalog_path())
        try:
            lang_sql = f" AND lang IN ({','.join('?' * len(langs))})" if langs else ""
            ids = [r[0] for r in con.execute(f"SELECT DISTINCT id FROM line WHERE id > ?{lang_sql} ORDER BY id LIMIT ?",
                                             (after, *langs, limit))]
            if not ids:
                return []
            books: dict[int, dict] = {}
            for bid, author, title, subtitle, lang, year, series in con.execute(
                    "SELECT id, author, title, subtitle, lang, year, series FROM line WHERE id BETWEEN ? AND ? "
                    "ORDER BY id, rowid", (ids[0], ids[-1])):
                if langs and lang not in langs:
                    continue
                b = books.setdefault(bid, {"title": title, "subtitle": subtitle, "lang": lang, "year": year,
                                           "series": series, "authors": []})
                if author and author not in b["authors"]:
                    b["authors"].append(author)
        finally:
            con.close()
        return [BookInfo(sid=str(bid), url=f"{self.base}/b/{bid}", title=b["title"] or f"#{bid}", authors=b["authors"],
                         lang=b["lang"] or None, status="completed",
                         extra={k: b[k] for k in ("series", "year", "subtitle") if b[k]})
                for bid, b in sorted(books.items())]

    def _catalog(self, state: dict):
        """Every book in the catalog file (in the chosen languages) after state["cat_after"], many at a time."""
        if state.get("cat_refresh") or not state.get("catalog_at") or not self._catalog_path().exists():
            self._load_catalog()
            state.update(catalog_at=time.time(), cat_refresh=False)
        langs = self._languages()
        if not state.get("cat_total"):
            con = sqlite3.connect(self._catalog_path())
            lang_sql = f" WHERE lang IN ({','.join('?' * len(langs))})" if langs else ""
            state["cat_total"] = con.execute(f"SELECT COUNT(DISTINCT id) FROM line{lang_sql}", langs).fetchone()[0]
            con.close()
        while True:
            books = self._catalog_books(state.get("cat_after", 0), langs, CATALOG_BATCH)
            if not books:
                break
            state["cat_after"] = int(books[-1].sid)
            state["cat_done"] = state.get("cat_done", 0) + len(books)
            self.batch_offline = True
            self.discover_activity = (f"listing every book from Flibusta's catalog: "
                                      f"{state['cat_done']:,} of about {state['cat_total']:,}")
            yield books
        self.batch_offline = False
        state["cat_max"] = max(state.get("cat_max", 0), state.get("cat_after", 0))
        state["cat_langs"] = langs
        for k in ("cat_after", "cat_done", "cat_total"):
            state.pop(k, None)
        self._catalog_path().unlink(missing_ok=True)  # read again from the site next month

    # ---------------------------------------------------------------- the genre pages
    def _genre_list(self) -> list[list]:
        p = self.http.get(f"{self.base}/g/", retries=5)
        genres = [[code, _html.unescape(name).strip(), int(n)] for code, name, n in
                  re.findall(r'<a href="/g/(\w+)"[^>]*>([^<]+)</a>\s*\(\w+\)\s*-\s*(\d+)', p.text)]
        if not genres:
            raise SiteError("Flibusta's genre list is empty (did the page change?)")
        return genres

    def _genre_page(self, code: str, page: int) -> tuple[list[tuple[str, str]], int]:
        """The books on one page of a genre (id, title), and the highest page number the page links to."""
        p = self.http.get(f"{self.base}/g/{code}", params={"page": page} if page else None, retries=5)
        m = re.search(r"<ol>(.*?)</ol>", p.text, re.S)  # the list itself (the sidebar has book links too)
        books = re.findall(r'<a href="/b/(\d+)">([^<]*)</a>', m.group(1)) if m else []
        last = max((int(n) for n in re.findall(rf'href="/g/{re.escape(code)}\?page=(\d+)"', p.text)), default=0)
        return [(bid, _html.unescape(title).strip()) for bid, title in books], last

    def _genres(self, state: dict):
        """Every genre's pages, so every listed book gets its genres (as labels next to the ones it has).
        Pages hold different numbers of books and Flibusta often fails a page (502), or sends one without its list:
        such a page is skipped (the book pages fill in those genres later), and the last page is the highest one any
        page of the genre links to (to begin with, an estimate from the genre's size)."""
        if not state.get("genres"):
            state.update(genres=self._genre_list(), gi=0, gpage=0, glast=None)
        genres = state["genres"]
        while state["gi"] < len(genres):
            code, name, count = genres[state["gi"]]
            if state.get("glast") is None:
                state["glast"] = max(0, -(-count // 50) - 1)  # about 50 books a page
            batch, error = [], None
            for _ in range(GENRE_PAGES_PER_STEP):
                try:
                    found, last = self._genre_page(code, state["gpage"])
                except Exception as e:  # keep what was read; this page is tried again after a pause
                    error = e
                    break
                batch += [BookInfo(sid=bid, url=f"{self.base}/b/{bid}", title=title, tags=[name], add_tags=True)
                          for bid, title in found]
                state["glast"] = max(state["glast"], last)
                if state["gpage"] >= state["glast"]:  # its last page
                    state.update(gi=state["gi"] + 1, gpage=0, glast=None)
                    break
                state["gpage"] += 1
            self.batch_offline = False
            self.discover_activity = (f"adding genres to every book: «{name}» "
                                      f"(genre {min(state['gi'] + 1, len(genres))} of {len(genres)})")
            if batch:
                yield batch
            if error:
                raise error

    # ---------------------------------------------------------------- the passes
    def discover(self, state: dict):
        langs = self._languages()
        if state.get("phase") == "updates":
            if state.get("cat_langs") != langs:  # other languages wanted: list the catalog again
                state.update(phase="catalog", cat_after=0)
            elif time.time() - state.get("catalog_at", 0) > CATALOG_DAYS * 86400:
                state.update(phase="catalog", cat_after=state.get("cat_max", 0), cat_refresh=True)
            else:
                yield from self._new_arrivals()
                return
        if state.get("phase", "catalog") == "catalog":
            first = not state.get("cat_max")
            state["phase"] = "catalog"
            yield from self._catalog(state)
            state["phase"] = "genres" if first else "updates"
        if state["phase"] == "genres":
            yield from self._genres(state)
            for k in ("genres", "gi", "gpage", "glast"):
                state.pop(k, None)
            state.update(phase="updates", full_done=True)
        yield from self._new_arrivals()

    # ---------------------------------------------------------------- one book
    def details(self, book: dict) -> BookInfo:
        p = self.http.get(f"{self.base}/b/{book['sid']}", retries=4)
        m = re.search(r'<h1 class="title">(.*?)</h1>(.*?)(?:<div id="sidebar|</body>)', p.text, re.S)
        if not m:
            raise NotFound(book["sid"])
        fmt = _FORMAT.search(_text(m.group(1)))
        title = _FORMAT.sub("", _text(m.group(1)))
        body = m.group(2)
        head = body.split('<p class="genre">')[0]  # the authors come before the genres
        authors = [_text(a) for a in re.findall(r'<a href="/a/\d+">(.*?)</a>', head)]
        genres = [_text(g) for g in re.findall(r'<a href="/g/\d+" class="genre"[^>]*>(.*?)</a>', body)]
        size = re.search(r"<span style=size>\s*([\d.,]+)\s*([KМ]|K|M)", body)
        words = None
        if size:
            kb = float(size.group(1).replace(",", ".")) * (1024 if size.group(2) in "MМ" else 1)
            words = int(kb * 58) if (not fmt or fmt.group(1).lower() == "fb2") else None
        added = re.search(r"Добавлена:\s*(\d\d)\.(\d\d)\.(\d{4})", body)
        year = re.search(r"издание (\d{4}) г", body)
        series = [_text(s) for s in re.findall(r'издано в серии <a href="/s/\d+">(.*?)</a>', body)]
        annotation = re.search(r"<h2>Аннотация</h2>(.*?)(?:<h2|<div|$)", body, re.S)
        cover = re.search(r'<img[^>]+src="(/i[bm]?/[^"]+?\.(?:jpe?g|png|gif))"', body, re.I)
        description = clean_text(html_to_text(annotation.group(1))) if annotation else ""
        extra = {"series": series[0] if series else None, "year": year.group(1) if year else None,
                 "format": fmt.group(1).lower() if fmt else None}
        return BookInfo(
            sid=book["sid"], url=f"{self.base}/b/{book['sid']}", title=title or f"#{book['sid']}",
            authors=[a for a in authors if a], description=description or None,
            cover=self.base + cover.group(1) if cover else None, status="completed", words=words,
            updated_at=f"{added.group(3)}-{added.group(2)}-{added.group(1)}" if added else None,
            tags=genres or None, extra={k: v for k, v in extra.items() if v}, complete=True,
        )

    # ---------------------------------------------------------------- text and files
    def opening_text(self, book: dict, max_chapters: int = 3, enough_words: int = 6000) -> list[str]:
        fmt = (book.get("extra") or {}).get("format", "fb2")
        if fmt and "fb2" not in fmt:
            return []  # PDF / DjVu scans have no readable text
        p = self.http.get(f"{self.base}/b/{book['sid']}/read", max_bytes=250_000, retries=4)
        html = p.text
        start = html.find("<h3 class=book")
        if start < 0:
            start = html.find('<p class="book"')
        if start < 0:
            return []
        body = html[start:]
        parts = re.split(r"<h3 class=book>", body)
        chapters, words = [], 0
        for part in parts:
            paras = re.findall(r'<p class="book">(.*?)</p>', part, re.S)
            text = "\n".join(clean_text(html_to_text(x)) for x in paras)
            if len(text.split()) < 150:  # book title, epigraph, table of contents...
                continue
            chapters.append(text)
            words += len(text.split())
            if len(chapters) >= max_chapters or words >= enough_words:
                break
        return chapters

    def native_download(self, book: dict, fmt: str):
        if fmt not in self.native_formats:
            return None
        p = self.http.get(f"{self.base}/b/{book['sid']}/{fmt}", retries=5)
        data = p.content
        if fmt == "fb2" and data[:2] == b"PK":  # FB2 comes zipped
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                name = next((n for n in z.namelist() if n.lower().endswith(".fb2")), None)
                if name:
                    return z.read(name), name
        disposition = p.headers.get("content-disposition", "")
        m = re.search(r'filename="?([^";]+)', disposition)
        return data, (m.group(1) if m else f"{book['sid']}.{fmt}")
