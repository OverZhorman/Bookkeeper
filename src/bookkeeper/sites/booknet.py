"""Booknet (booknet.ua): Ukrainian web fiction, about 27,000 books. Litnet grew out of the same platform, and the
reader works the same way, but the catalog and book pages are Booknet's own.

Catalog: the "all genres" list (/top/all), most popular first, 20 books per page with title, author, the start of
the annotation, tags, likes, views, status and length. Details: the book page (genre, every tag, the 18+ mark, the
whole annotation, the chapter list with paid chapters marked). Text: the reader. Page 1 of a chapter is in the reader
page; the rest comes from the reader's own page request, as on Litnet. 18+ books can only be read logged in."""
import html as _html
import re

from ..analysis.text import clean_text, html_to_text
from ..http import NotFound
from .base import BookInfo, Chapter, Site, SiteError

BASE = "https://booknet.ua"
STATUS = {"в процесі": "ongoing", "повний текст": "completed", "заморожено": "frozen"}
_CARD_SPLIT = '<div class="bn_book-genre">'
_TEXT = re.compile(r'<div class="reader-text[^"]*"[^>]*>(.*?)</div>\s*<div id="event-params"', re.S)


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


def _int(s: str | None) -> int | None:
    digits = re.sub(r"\D", "", s or "")
    return int(digits) if digits else None


def _status(s: str) -> str | None:
    s = _text(s).lower()
    return next((v for k, v in STATUS.items() if s.startswith(k)), None)


def _sid(alias: str) -> str | None:
    m = re.search(r"-b(\d+)$", alias)
    return m.group(1) if m else None


def _links(block: str, path: str) -> list[str]:
    return [t for t in (_text(x) for x in re.findall(r'<a[^>]*href="' + path + r'[^"]*"[^>]*>(.*?)</a>', block, re.S))
            if t]


def parse_card(block: str) -> BookInfo | None:
    """One book in a catalog list."""
    link = re.search(r'<a href="/book/([^"]+)" class="bn_book-genre__title-link">(.*?)</a>', block, re.S)
    if not link or not _sid(link.group(1)):
        return None
    alias = link.group(1)
    author = re.search(r'<div class="bn_book-genre__author[^"]*">(.*?)</div>', block, re.S)
    note = re.search(r'<div class="bn_book-genre__annotation[^"]*">(.*?)</div>', block, re.S)
    tags = re.search(r'<div class="bn_book-genre__tags[^"]*">(.*?)</div>', block, re.S)
    stats = re.findall(r'#(star|eye)"></use>\s*</svg>\s*<span[^>]*>(.*?)</span>', block, re.S)
    status = re.search(r'<div class="bn_book-genre__status-content">(.*?)</div>', block, re.S)
    pages = re.search(r'<div class="bn_book-genre__status-pages">(.*?)</div>', block, re.S)
    price = re.search(r'<div class="bn_book-genre__price">(.*?)</div>\s*</div>', block, re.S)
    cover = re.search(r'<img src="([^"]+)"', block)
    nums = {kind: _int(v) for kind, v in stats}
    paid = bool(price and "грн" in price.group(1))
    return BookInfo(
        sid=_sid(alias), url=f"{BASE}/book/{alias}", title=_text(link.group(2)),
        authors=_links(author.group(1), "/") if author else [],
        description=html_to_text(note.group(1)).strip() or None if note else None,
        cover=cover.group(1) if cover else None, lang="uk", is_translation=False,
        status=_status(status.group(1)) if status else None, likes=nums.get("star"), views=nums.get("eye"),
        pop_raw=nums.get("star"), access="partial" if paid else "free",
        tags=_links(tags.group(1), "/tag/") if tags else None, partial_tags=True,
        extra={"alias": alias, "pages": _int(_text(pages.group(1))) if pages else None},
    )


class Booknet(Site):
    id = "booknet"
    name = "Booknet"
    home = BASE
    lang = "uk"
    min_interval = 2.0
    note = ("Ukrainian web fiction, about 27,000 books, with tags. Litnet grew out of the same platform. 18+ books "
            "can only be read logged in.")
    login_url = f"{BASE}/auth/login"
    # Booknet's login has several ways in (e-mail, Google, Facebook), so you log in yourself once; Bookkeeper keeps
    # the session.
    login_autofill = False
    login_benefit = "18+ books, and the chapters you bought (Bookkeeper's downloads then include them)."
    logged_in_js = "(document.querySelector('#ga-isLoggedIn') || {getAttribute: () => '0'}).getAttribute('value') === '1'"

    def check_login(self) -> bool | None:
        m = re.search(r'id="ga-isLoggedIn" value="(\d)"', self.http.get(f"{BASE}/").text)
        return (m.group(1) == "1") if m else None

    # ----- catalog
    def _top(self, page: int) -> tuple[list[BookInfo], int]:
        s = self.http.get(f"{BASE}/top/all", params={"alias": "all", "page": page}).text
        books = [b for b in (parse_card(x) for x in s.split(_CARD_SPLIT)[1:]) if b]
        last = max([int(n) for n in re.findall(r'href="/top/all\?alias=all&amp;page=(\d+)"', s)] + [page])
        return books, last

    def discover(self, state: dict):
        if state.get("full_done"):
            for page in range(1, 6):  # later passes: the first pages again (new and rising books)
                books, _ = self._top(page)
                if not books:
                    break
                yield books
            return
        page = state.get("page", 1)
        while True:
            books, last = self._top(page)
            if books:
                yield books
            if not books or page >= last:
                state.update(full_done=True, page=1)
                return
            page += 1
            state["page"] = page

    def _alias(self, book: dict) -> str:
        alias = (book.get("extra") or {}).get("alias")
        if not alias:
            m = re.search(r"/book/([^/?#]+)", book.get("url") or "")
            alias = m.group(1) if m else None
        if not alias:
            raise SiteError("book address unknown")
        return alias

    def _book_page(self, book: dict) -> str:
        return self.http.get(f"{BASE}/book/{self._alias(book)}").text

    @staticmethod
    def parse_book(alias: str, s: str) -> BookInfo:
        title = re.search(r'<h1 class="bn_book__header-title[^"]*">(.*?)</h1>', s, re.S)
        if not title:
            raise SiteError("unexpected page layout (no book title)")
        adult = "bn_book__header-adult-only" in title.group(1)
        name = _text(re.sub(r"<span.*?</span>", "", title.group(1), flags=re.S))
        genres = [_text(g) for g in re.findall(r'<a class="bn_book__header-genre[^"]*"[^>]*>(.*?)</a>', s, re.S)]
        authors = [_text(a) for a in re.findall(
            r'<h2 class="bn_book__header-author-item-name[^"]*">\s*<a[^>]*>(.*?)</a>', s, re.S)]
        status = re.search(r'<span class="bn_book__header-status-value">(.*?)</span>', s, re.S)
        pages = re.search(r'<span class="bn_book__header-status-count">(.*?)</span>', s, re.S)
        likes = re.search(r'bn_book__header-button-like[^>]*>.*?<span[^>]*>(.*?)</span>', s, re.S)
        about = re.search(r'<div class="bn_book__about-content[^"]*">(.*?)</div>', s, re.S)
        tags = re.search(r'<h4 class="bn_book__tags[^"]*">(.*?)</h4>', s, re.S)
        count = re.search(r"Зміст книги:\s*(\d+)", s)
        paid = re.search(r'class="bn_btn[^"]*bn_buy-button"', s)
        cover = re.search(r'<img class="bn_book__header-image-src" src="([^"]+)"', s)
        labels = genres + (_links(tags.group(1), "/tag/") if tags else [])
        return BookInfo(
            sid=_sid(alias) or alias, url=f"{BASE}/book/{alias}", title=name, authors=authors,
            description=html_to_text(about.group(1)).strip() or None if about else None,
            cover=cover.group(1) if cover else None, lang="uk", is_translation=False,
            status=_status(status.group(1)) if status else None, chapters=int(count.group(1)) if count else None,
            likes=_int(_text(likes.group(1))) if likes else None, adult=adult, age_rating="18+" if adult else None,
            access="partial" if paid else "free", tags=list(dict.fromkeys(x for x in labels if x)),
            extra={"alias": alias, "pages": _int(_text(pages.group(1))) if pages else None},
        )

    def details(self, book: dict) -> BookInfo:
        # The card's views stay as they were: the book page doesn't show them (blank values don't overwrite).
        alias = self._alias(book)
        return self.parse_book(alias, self.http.get(f"{BASE}/book/{alias}").text)

    # ----- text
    @staticmethod
    def parse_chapters(s: str) -> list[Chapter]:
        out = []
        for i, (cls, cid, title) in enumerate(re.findall(
                r'<div class="bn_book__chapters-item ?([^"]*)">\s*<div class="bn_book__chapters-item-heading">\s*'
                r'<a href="/reader/[^"?]+\?c=(\d+)"[^>]*></a>.*?<span class="bn_book__chapters-item-title[^"]*">'
                r'(.*?)</span>', s, re.S)):
            out.append(Chapter(id=cid, title=_text(title) or f"Розділ {i + 1}", index=i, free="lock" not in cls))
        return out

    def chapters(self, book: dict) -> list[Chapter]:
        out = self.parse_chapters(self._book_page(book))
        if not out:
            raise NotFound("no chapter list")
        return out

    def _reader(self, book: dict, chapter: Chapter) -> tuple[str, str]:
        """Page 1 of a chapter, and the reader's request token."""
        s = self.http.get(f"{BASE}/reader/{self._alias(book)}", params={"c": chapter.id}).text
        m = _TEXT.search(s)
        if not m and "Доступ обмежено" in s[:3000]:
            raise SiteError("this book is 18+: Booknet shows it only to logged-in readers")
        text = html_to_text(m.group(1)) if m else ""
        token = re.search(r'<meta name="csrf-token" content="([^"]+)"', s)
        return text, token.group(1) if token else ""

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        """The whole chapter: page 1 from the reader page, the rest from the reader's page request (it answers a
        page past the end with the last page again)."""
        first, token = self._reader(book, chapter)
        parts, last = [], None
        for n in range(1, 200):
            r = self.http.post(f"{BASE}/reader/get-page",
                               data={"chapterId": chapter.id, "page": str(n), "_csrf": token},
                               headers={"X-Requested-With": "XMLHttpRequest", "X-CSRF-Token": token})
            try:
                d = r.json()
            except ValueError:
                break
            if d.get("status") != 1 or not d.get("data") or d["data"] == last:
                break
            last = d["data"]
            parts.append(html_to_text(d["data"]))
            if d.get("isLastPage"):
                break
        text = "\n".join(parts) if parts else first
        return re.sub(r"^((?:Розділ|Глава)[^\n]{0,80}\n)", "", text)

    def opening_text(self, book: dict, max_chapters: int = 3, enough_words: int = 6000) -> list[str]:
        # The first page of each opening chapter is plenty for the narration check.
        out, words = [], 0
        for ch in self.chapters(book)[:max_chapters + 2]:
            if not ch.free:
                break
            text, _ = self._reader(book, ch)
            if not text.strip():
                break
            out.append(text)
            words += len(text.split())
            if len(out) >= max_chapters or words >= enough_words:
                break
        return out
