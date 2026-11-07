"""Flibusta: a big library of published books (mostly Russian), in FB2.

Catalog: the OPDS feed of new arrivals, newest first (20 books per page, with genres, series and a description).
Text for narration analysis: the online reader page, of which we read only the first ~250 KB.
Downloads: the site's own FB2 / EPUB files."""
import io
import re
import xml.etree.ElementTree as ET
import zipfile

from ..analysis.text import clean_text, html_to_text
from .base import BookInfo, Site

NS = {"a": "http://www.w3.org/2005/Atom", "dc": "http://purl.org/dc/terms/"}
_ID = re.compile(r"^/b/(\d+)$")
_FOOTER = re.compile(r"(Формат:|Язык:|Размер:|Серия:|Год издания:|Перевод:).*$", re.S)
_SIZE = re.compile(r"Размер:\s*([\d.,]+)\s*(Kb|Mb|Кб|Мб)", re.I)
_SERIES = re.compile(r'Все книги серии "(.+)"')


class Flibusta(Site):
    id = "flibusta"
    name = "Flibusta"
    home = "https://flibusta.site"
    lang = "ru"
    min_interval = 1.5
    note = "Published books. Lists the whole library from its catalog feed; downloads use Flibusta's own files."
    native_formats = ("fb2", "epub")

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.base = (self.settings.get("base") or self.home).rstrip("/")

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
        has_next = any(l.get("rel") == "next" for l in root.findall("a:link", NS))
        return books, has_next

    def discover(self, state: dict):
        mode = state.get("mode", "full")
        page = state.get("page", 0)
        while True:
            books, has_next = self._feed(page)
            if books:
                yield books
            page += 1
            if mode == "full":
                state["page"] = page
                if not books or not has_next:
                    state.update(mode="updates", page=0, full_done=True)
                    return
            else:
                if not has_next or page >= 10:  # the newest 200 books per pass
                    state["page"] = 0
                    return
                state["page"] = page

    def details(self, book: dict) -> BookInfo:  # the catalog feed already has everything we use
        raise NotImplementedError

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
