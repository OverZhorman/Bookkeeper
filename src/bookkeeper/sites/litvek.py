"""Litvek (litvek.com): a big Russian e-library (about 670,000 books). Bookkeeper reads one listing of it, by default
its web fiction: the genre "Самиздат, сетевая литература" (about 95,000 books, most read first).

Catalog: the listing's pages, 15 books each (title, authors, genres, series, pages, rating, whether only a fragment
is there). Details: the book page adds its keywords (Ключевые слова), the full description and whether it's finished.
Text: the online reader (/br/ID?p=N). The site's robots.txt asks programs not to use its download links, so Bookkeeper
doesn't: a download is put together from the reader pages, split at the book's own chapter headings."""
import html as _html
import re

from ..analysis.text import clean_text, html_to_text, opening_pieces
from ..http import NotFound
from .base import BookInfo, Chapter, Site, looks_adult

BASE = "https://litvek.com"
DEFAULT_LISTING = "/genre/network_literature-zhanr-samizdat-setevaya-literatura"
LANGS = {"русский": "ru", "английский": "en", "украинский": "uk", "белорусский": "be"}
_CARD_SPLIT = '<div class="pbook" itemscope="" itemtype="http://schema.org/Book">'
_NOTICES = re.compile(r"^\s*©")  # copyright lines at the start of the reader


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


def _field(s: str, name: str) -> str:
    """The HTML after "<name>:" up to the end of its paragraph."""
    m = re.search(r"<p[^>]*>\s*" + re.escape(name) + r":(.*?)</p>", s, re.S)
    return m.group(1) if m else ""


def _links(fragment: str, kind: str) -> list[str]:
    return [t for t in (_text(x) for x in re.findall(r"""href=['"]/""" + kind + r"""/[^'"]+['"][^>]*>(.*?)</a>""",
                                                     fragment, re.S)) if t]


def _int(text: str) -> int | None:
    digits = re.sub(r"\D", "", text or "")
    return int(digits) if digits else None


def _common(s: str) -> dict:
    """What a listing card and a book page both show."""
    genres = _links(_field(s, "Жанр"), "genre")
    series = _links(_field(s, "Серия"), "serial")
    lang = _text(_field(s, "Язык книги")).lower()
    pages = re.search(r"itemprop='numberOfPages'>(\d+)<", s)
    year = re.search(r"itemprop='datePublished'>(\d{4})<", s) or re.search(r"Год издания:\s*<span[^>]*>\s*(\d{4})", s)
    rating = re.search(r"оценок:\s*(\d+)\s*\(средняя:\s*<span[^>]*>([\d.]+)", s)
    return {
        "authors": _links(_field(s, "Автор"), "avtor"), "genres": genres, "series": series[0] if series else None,
        "lang": LANGS.get(lang, lang or None), "pages": int(pages.group(1)) if pages else None,
        "year": year.group(1) if year else None,
        "rating": min(10.0, float(rating.group(2))) if rating else None, "votes": int(rating.group(1)) if rating else None,
        "fragment": "ознакомительный фрагмент" in s,
    }


class Litvek(Site):
    id = "litvek"
    name = "Litvek"
    home = BASE
    lang = "ru"
    min_interval = 2.5  # robots.txt asks for at least 1 second
    note = ("A big Russian e-library. Bookkeeper reads its web fiction (Самиздат, сетевая литература, about 95,000 "
            "books) with each book's keywords. Some books are only a fragment there (marked as partly free).")
    extra_settings = {
        "listing": {"label": "Which books: a genre's address on litvek.com, or “all” for the whole library (newest first)",
                    "default": DEFAULT_LISTING},
        "pages": {"label": "Catalog pages to read (15 books each)", "default": "7000"},
    }

    # ----- catalog
    def _listing_path(self) -> str:
        value = str(self.settings.get("listing") or DEFAULT_LISTING).strip()
        if value.lower() in ("all", "все", "/"):
            return "/"
        value = re.sub(r"^https?://(www\.)?litvek\.com", "", value).split("?")[0]
        return value if value.startswith("/") else "/" + value

    def _card(self, card: str) -> BookInfo | None:
        link = re.search(r"<div class='ob_tit'><a href='(/books/(\d+)-[^']+)'><h2 itemprop='name'>(.*?)</h2>", card, re.S)
        if not link:
            return None
        path, bid = link.group(1), link.group(2)
        c = _common(card)
        cover = re.search(r"itemprop='image' class='cover' src='([^']+)'", card)
        readable = "dw_dis" not in (re.search(r"<span class='ob_read[^']*'|<a class='ob_read[^']*'", card) or [""])[0]
        return BookInfo(
            sid=bid, url=BASE + path, title=_text(link.group(3)) or f"#{bid}", authors=c["authors"],
            cover=BASE + cover.group(1) if cover and cover.group(1).startswith("/") else None, lang=c["lang"],
            rating=c["rating"], votes=c["votes"], pop_raw=c["votes"],
            words=c["pages"] * 280 if c["pages"] else None,
            access="partial" if c["fragment"] else "free" if readable else "paid",
            adult=looks_adult(c["genres"]), tags=list(dict.fromkeys(c["genres"])), partial_tags=True,
            created_at=f"{c['year']}-01-01" if c["year"] else None,
            extra={"path": path, "series": c["series"], "pages": c["pages"], "fragment": c["fragment"],
                   "readable": readable, "self_published": "(СИ)" in link.group(3)},
        )

    def _list(self, page: int) -> tuple[list[BookInfo], int]:
        """One listing page: its books, and the number of the listing's last page."""
        path = self._listing_path()
        try:
            s = self.http.get(BASE + path, params={"page": page} if page > 1 else None).text
        except NotFound:
            return [], 0
        last = max([int(x) for x in re.findall(r"[?&]page=(\d+)", s)] + [page])
        return [b for b in (self._card(c) for c in s.split(_CARD_SPLIT)[1:]) if b], last

    def discover(self, state: dict):
        if state.get("listing") not in (None, self._listing_path()):  # you chose other books: start again
            state.clear()
        state["listing"] = self._listing_path()
        if state.get("full_done"):
            for page in range(1, 6):
                books, _ = self._list(page)
                if not books:
                    break
                yield books
            return
        limit = _int(str(self.settings.get("pages") or "7000")) or 7000
        page = state.get("page", 1)
        while page <= limit:
            books, last = self._list(page)
            if not books:
                break
            yield books
            page += 1
            state["page"] = page
            if page > last:
                break
        state.update(full_done=True, page=1)

    def details(self, book: dict) -> BookInfo:
        path = (book.get("extra") or {}).get("path") or f"/books/{book['sid']}"
        s = self.http.get(BASE + path).text
        s = s[max(0, s.find("<h1")):]  # the book itself, not the other books shown above it
        title = re.search(r"<h1[^>]*>(.*?)</h1>", s, re.S)
        c = _common(s)
        kw = re.search(r"Ключевые слова:(.*?)</td>", s, re.S)
        keywords = _links(kw.group(1), "keywords") if kw else []
        desc = re.search(r"<p class='ob_ann' itemprop='description'>(.*?)<br>\s*</td>", s, re.S)
        publisher = _links(_field(s, "Издательство"), "publisher")
        isbn = re.search(r"itemprop='isbn'>([^<]+)<", s)
        views = re.search(r"всего:\s*<span class='o'>([\d\s]+)<", s)
        reader = re.search(r"<a class='ob_read[^']*' href='(/book-read/[^']+)'", s)
        status = "completed" if "Книга закончена" in s else "ongoing" if "Книга не закончена" in s else None
        genres = c["genres"] or None
        return BookInfo(
            sid=book["sid"], url=BASE + path, title=_text(title.group(1)) if title else book.get("title") or "",
            authors=c["authors"], description=html_to_text(desc.group(1)).strip() if desc else None,
            lang=c["lang"], status=status, views=_int(views.group(1)) if views else None,
            words=c["pages"] * 280 if c["pages"] else None,
            access="partial" if c["fragment"] else "free" if reader else "paid",
            adult=looks_adult(genres or []),
            tags=list(dict.fromkeys([*(genres or []), *keywords])) if genres or keywords else None,
            created_at=f"{c['year']}-01-01" if c["year"] else None,
            extra={"path": path, "series": c["series"], "pages": c["pages"], "keywords": keywords,
                   "publisher": publisher[0] if publisher else None, "isbn": _text(isbn.group(1)) if isbn else None,
                   "readable": bool(reader)},
        )

    # ----- the reader
    def _reader(self, sid: str, page: int) -> tuple[str, int]:
        """(HTML of one reader page's text, number of reader pages)."""
        try:
            s = self.http.get(f"{BASE}/br/{sid}", params={"p": page}).text
        except NotFound:
            return "", 0
        start = s.find("class='btext'")
        if start < 0:
            return "", 0
        end = s.find("</main>", start)
        pages = [int(x) for x in re.findall(r"href='\?p=(\d+)", s)]
        return s[s.find(">", start) + 1: end if end > 0 else None], max(pages + [page])

    @staticmethod
    def _readable(book: dict) -> bool:
        """False when the site took the text down (the book page then only links to a shop)."""
        return (book.get("extra") or {}).get("readable") is not False

    def chapters(self, book: dict) -> list[Chapter]:
        if not self._readable(book):
            return []
        first, total = self._reader(book["sid"], 1)
        parts = [first]
        for n in range(2, total + 1):
            parts.append(self._reader(book["sid"], n)[0])
            if self.progress:
                self.progress(n)
        # Split at the book's own headings; the first one is the book's author and title.
        pieces = re.split(r"<h3 class=['\"]book['\"]>", "".join(parts))
        chapters, self._parts = [], {}
        for piece in pieces:
            head = re.match(r"(.*?)</h3>", piece, re.S)
            title = _text(head.group(1)) if head else ""
            body = html_to_text(piece[head.end():] if head else piece)
            if len(body.split()) < 30:
                continue
            cid = str(len(chapters))
            self._parts[cid] = body
            chapters.append(Chapter(id=cid, title=title or f"Часть {len(chapters) + 1}", index=len(chapters)))
        return chapters

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        if not getattr(self, "_parts", None) or chapter.id not in self._parts:
            self.chapters(book)
        return self._parts.get(chapter.id, "")

    def opening_text(self, book: dict, max_chapters: int = 3, enough_words: int = 6000) -> list[str]:
        if not self._readable(book):
            return []
        html, total = self._reader(book["sid"], 1)
        text = html_to_text(html)
        n = 2
        while len(text.split()) < enough_words + 500 and n <= min(total, 4):
            text += "\n" + html_to_text(self._reader(book["sid"], n)[0])
            n += 1
        return opening_pieces(text, enough_words, max_chapters, skip_lines=_NOTICES)
