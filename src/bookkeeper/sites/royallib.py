"""RoyalLib (royallib.com): a big library of published books, mostly Russian, with ready FB2 / EPUB / TXT files.

Catalog: first the genre pages (popular and new books in each genre), then the alphabetical index of every book
(up to 1000 titles per page). Details: the book page (author, genres, series, rating, annotation).
Text for the narration check: the opening of the book's TXT file. Downloads: the site's own FB2 / EPUB / TXT."""
import html as _html
import io
import re
import zipfile

from ..analysis.text import clean_text, detect_lang, opening_pieces
from ..http import Blocked, NotFound, decode_bytes
from .base import BookInfo, Site, SiteError, looks_adult

BASE = "https://royallib.com"
_BOOK = re.compile(r'href="(?:https:)?//royallib\.com/book/([a-z0-9_]+/[a-z0-9_]+)\.html"[^>]*>(.*?)</a>', re.S)
_NOTICE = re.compile(r"royallib|Спасибо, что скачали|Все книги автора|Эта же книга в других форматах|"
                     r"Приятного чтения|Другие книги серии", re.I)


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


class RoyalLib(Site):
    id = "royallib"
    name = "RoyalLib"
    home = BASE
    lang = "ru"
    min_interval = 6.0  # the site shows a captcha to fast readers, and blocked 3 s (2026-11)
    note = ("Published books, mostly Russian. Downloads use RoyalLib's own FB2, EPUB and TXT files. The site shows a "
            "captcha when it's read too fast; Bookkeeper then stops and waits for you to press Try again.")
    native_formats = ("fb2", "epub", "txt")

    def _get(self, url: str, **kw):
        p = self.http.get(url, **kw)
        if "window.__RLD" in p.text[:20000] or "<title>Проверка</title>" in p.text[:3000]:
            raise Blocked("RoyalLib showed a captcha (open royallib.com in your browser once, then press Try again)")
        return p

    # ----- catalog
    def _links(self, page: str) -> list[tuple[str, str]]:
        seen, out = set(), []
        for sid, title in _BOOK.findall(page):
            if sid not in seen:
                seen.add(sid)
                out.append((sid, _text(title) or _text(re.sub(r".*/", "", sid).replace("_", " "))))
        return out

    def _infos(self, links) -> list[BookInfo]:
        out = []
        for sid, label in links:
            # Genre pages show "Title" and the author on the next line; index pages only the title.
            lines = [x.strip() for x in label.split("\n") if x.strip()]
            out.append(BookInfo(sid=sid, url=f"{BASE}/book/{sid}.html", title=lines[0] if lines else sid,
                                authors=lines[1:2], lang="ru", status="completed", access="free"))
        return out

    def discover(self, state: dict):
        if "queue" not in state:
            home = self._get(f"{BASE}/").text
            genres = sorted(set(re.findall(r'href="(?:https:)?//royallib\.com/genre/([a-z_]+)/"', home)))
            state.update(queue=[f"/genre/{g}/" for g in genres] + ["/books-a.html"], i=0,
                         seen=[f"/genre/{g}/" for g in genres] + ["/books-a.html"])
        if state.get("full_done"):
            # Later passes: the genre pages again (their "new books" lists).
            state.update(i=0, full_done=False, queue=[q for q in state["queue"] if q.startswith("/genre/")])
        seen = set(state.get("seen") or [])
        while state["i"] < len(state["queue"]):
            path = state["queue"][state["i"]]
            state["i"] += 1
            try:
                page = self._get(BASE + path).text
            except NotFound:
                continue
            for more in re.findall(r'href="(?:https:)?//royallib\.com/((?:books|genre)[-/][a-z0-9_/-]*?(?:\.html|/))"',
                                   page):
                more = "/" + more
                if more not in seen and (more.startswith("/books-") or more.count("/") == 3):
                    seen.add(more)
                    state["queue"].append(more)
            state["seen"] = sorted(seen)
            books = self._infos(self._links(page))
            if books:
                yield books
        state["full_done"] = True

    # ----- details
    def details(self, book: dict) -> BookInfo:
        s = self._get(f"{BASE}/book/{book['sid']}.html").text
        t = re.sub(r"\s+", " ", _text(re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", s)))
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", s, re.S)
        if not h1:
            raise SiteError("unexpected page layout (no title)")
        title_m = re.search(r"Название:\s*(.+?)\s+(?:Жанр|Серия|Оригинальное|Читать|Доступные)", t)
        authors = [_text(a) for a in re.findall(r'href="(?:https:)?//royallib\.com/author/[^"]+"[^>]*title="Все книги [^"]*"[^>]*>(.*?)</a>', s, re.S)]
        genres = [_text(g) for g in re.findall(r'href="(?:https:)?//royallib\.com/genre/[^"]+"[^>]*title="Все книги жанра[^"]*"[^>]*>(.*?)</a>', s, re.S)]
        series = re.search(r"Серия:\s*(.{1,120}?)\s+(?:Аннотация|Рейтинг|Жанр|Оригинальное|Читать|Доступные|Добавить)", t)
        rating = re.search(r"Рейтинг:\s*([\d,.]+)\s*\((\d+)\s*голос", t)
        ann = re.search(r"Аннотация:\s*(.+?)(?:\s+Скачать|\s+Читать книгу|\s+Доступные форматы|$)", t)
        description = ann.group(1)[:3000] if ann else None
        title = title_m.group(1) if title_m else _text(h1.group(1)).split("—")[-1].replace("скачать книгу бесплатно", "").strip()
        return BookInfo(
            sid=book["sid"], url=f"{BASE}/book/{book['sid']}.html", title=title,
            authors=list(dict.fromkeys(a for a in authors if a))[:4], description=description,
            lang=detect_lang(f"{title} {description or ''}") or "ru", status="completed", access="free",
            rating=round(float(rating.group(1).replace(",", ".")) * 2, 2) if rating else None,
            votes=int(rating.group(2)) if rating else None, pop_raw=int(rating.group(2)) if rating else None,
            tags=list(dict.fromkeys(g for g in genres if g)), adult=looks_adult(genres),
            extra={"series": series.group(1) if series else None},
        )

    # ----- the book's own files
    def _file(self, book: dict, fmt: str, max_bytes: int | None = None) -> tuple[bytes, str] | None:
        self._get(f"{BASE}/book/{book['sid']}.html")  # the site wants its cookie before a download
        p = self.http.get(f"{BASE}/get/{fmt}/{book['sid']}.zip", max_bytes=max_bytes,
                          headers={"Referer": f"{BASE}/book/{book['sid']}.html"})
        data = p.content
        if data[:2] != b"PK":
            return None
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                name = next((n for n in z.namelist() if n.lower().endswith("." + fmt)), z.namelist()[0])
                return z.read(name), name
        except zipfile.BadZipFile:
            return None

    def native_download(self, book: dict, fmt: str):
        return self._file(book, fmt) if fmt in self.native_formats else None

    def chapters(self, book: dict):
        return []  # downloads use the site's own files

    def opening_text(self, book: dict, max_chapters: int = 3, enough_words: int = 6000) -> list[str]:
        res = self._file(book, "txt")
        if not res:
            return []
        text = clean_text(decode_bytes(res[0][:600_000]))  # UTF-8, else Windows-1251
        return opening_pieces(text, enough_words, max_chapters, skip_lines=_NOTICE)
