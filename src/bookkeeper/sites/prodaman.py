"""Prodaman (prodaman.ru): Russian web fiction ("прода" is a new installment), about 20,000 books, with categories and
hashtags.

Catalog: the site-wide list (/books/), 20 books per page, with author, categories, hashtag, size, status, the 18+
mark, views and favourites. Details: the book page (the whole annotation, rating, dates). Text: the reader shows a
book in long pages (/<author>/books/<book>?page=N); each page becomes a chapter."""
import html as _html
import re
from datetime import datetime

from ..analysis.text import clean_text, html_to_text
from ..http import NotFound
from .base import BookInfo, Chapter, Site, SiteError, looks_adult

BASE = "https://prodaman.ru"
_CARD = re.compile(r'<div style="display:table;width:100%;" class="uii-grid-a basic-products-list-item')
# The text box sometimes carries an extra class with a made-up name.
_READER = re.compile(r'<div class="blog-text noselect reader-box[^"]*"[^>]*>(.*?)</div>', re.S)


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


def _int(s: str | None) -> int | None:
    digits = re.sub(r"\D", "", s or "")
    return int(digits) if digits else None


def _date(s: str | None) -> str | None:
    try:
        return datetime.strptime((s or "").strip()[:10], "%d.%m.%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _status(block: str) -> str | None:
    m = re.search(r"<span class='([a-z]+)-text'>(.*?)<br", block)
    s = (m.group(2) if m else "").lower()
    if "процессе" in s:
        return "ongoing"
    if "заверш" in s or "закончен" in s:
        return "completed"
    if "заморож" in s:
        return "frozen"
    return None


def _common(block: str) -> dict:
    """What a list card and a book page both show."""
    size = re.search(r"Размер:\s*<strong>[^<]*</strong>\s*алк\s*/\s*<strong>(\d+)</strong>\s*знаков", block)
    cats = re.search(r"Категории:\s*<span[^>]*>(.*?)</span>", block, re.S)
    genres = [_text(g) for g in re.findall(r"<a href=\"/books/[^\"]+/\"><strong>(.*?)</strong></a>",
                                           cats.group(1))] if cats else []
    tags = [_text(t).lstrip("#").replace("_", " ") for t in
            re.findall(r"Хэштег:\s*(?:<a[^>]*>(.*?)</a>[,\s]*)+", block, re.S)]
    tags = [_text(t).lstrip("#").replace("_", " ") for t in re.findall(r"<a href=\"[^\"]*\?tag=[^\"]+\"[^>]*>(#.*?)</a>",
                                                                        block)] or tags
    stats = re.search(r"(\d+)\s*просмотров.*?(\d+)\s*комментари.*?(\d+)\s*в избранном", block, re.S)
    access = re.search(r"<span class='[a-z]+-text'>[^<]*<br/>([^<]+)</span>", block)
    labels = list(dict.fromkeys(x for x in genres + tags if x))
    adult = 'class="adult18"' in block or looks_adult(labels)
    return {
        "words": int(int(size.group(1)) / 7.2) if size else None, "labels": labels, "adult": adult,
        "views": int(stats.group(1)) if stats else None, "favourites": int(stats.group(3)) if stats else None,
        "status": _status(block),
        "access": None if not access else "free" if "для всех" in access.group(1) else "partial",
        "chars": int(size.group(1)) if size else None,
    }


def parse_list(page: str) -> tuple[list[BookInfo], int]:
    out = []
    for block in _CARD.split(page)[1:]:
        block = block[:block.find('<div style="" class="ui-single-block-a')] if 'ui-single-block-a' in block else block
        link = re.search(r'<p class="blog-title"><a href="/([^"/]+)/books/([^"/?]+)">(.*?)</a></p>', block, re.S)
        if not link:
            continue
        author = re.search(r'<strong><a href="/' + re.escape(link.group(1)) + r'">(.*?)</a></strong>', block, re.S)
        cover = re.search(r'<img src="([^"]+)" class="sam-list-pic', block)
        rating = re.search(r'title="Рейтинг: ([\d.,]+) \* (\d+)"', block)
        about = re.search(r'<p class="blog-text">(.*?)<a class="more', block, re.S)
        c = _common(block)
        score = float(rating.group(1).replace(",", ".")) if rating else 0
        out.append(BookInfo(
            sid=f"{link.group(1)}/{link.group(2)}", url=f"{BASE}/{link.group(1)}/books/{link.group(2)}",
            title=_text(link.group(3)), authors=[_text(author.group(1))] if author else [],
            description=html_to_text(about.group(1)).strip().rstrip(".").strip() or None if about else None,
            cover=cover.group(1) if cover else None, lang="ru", is_translation=False, status=c["status"],
            words=c["words"], rating=round(score * 2, 2) if score else None,
            votes=int(rating.group(2)) if rating and int(rating.group(2)) else None, views=c["views"],
            likes=c["favourites"], pop_raw=c["views"], adult=c["adult"], age_rating="18+" if c["adult"] else None,
            access=c["access"], tags=c["labels"] or None, extra={"chars": c["chars"]},
        ))
    pages = [int(n) for n in re.findall(r'href="/books/\?sortby=-1&(?:amp;)?page=(\d+)"', page)]
    return out, max(pages, default=1)


def parse_book(sid: str, page: str) -> BookInfo:
    title = re.search(r'<h1 itemprop="name"[^>]*>(.*?)</h1>', page, re.S)
    if not title:
        raise SiteError("unexpected page layout (no book title)")
    # The book's own panel; other books' cards follow it on the page.
    end = page.find("custom-corners sam-panel", title.end())
    s = page[title.start():end if end > 0 else None]
    author = re.search(r'Автор:\s*<a href="/[^"]+"[^>]*>(.*?)</a>', s, re.S)
    cover = re.search(r'<img itemprop="image"[^>]*src="([^"]+)"', s)
    about = re.search(r'<div itemprop="description" class="blog-text">(.*?)</div>', s, re.S)
    rating = re.search(r'<meta itemprop="ratingValue" content="([\d.,]+)" />\s*<meta itemprop="ratingCount" '
                       r'content="(\d+)"', s)
    created = re.search(r"Дата размещения:\s*<strong>(.*?)</strong>", s)
    updated = re.search(r"Дата обновления:\s*<strong>(.*?)</strong>", s)
    c = _common(s)
    score = float(rating.group(1).replace(",", ".")) if rating else 0
    return BookInfo(
        sid=sid, url=f"{BASE}/{sid.split('/')[0]}/books/{sid.split('/', 1)[1]}", title=_text(title.group(1)),
        authors=[_text(author.group(1))] if author else [],
        description=html_to_text(about.group(1)).strip() or None if about else None,
        cover=cover.group(1) if cover else None, lang="ru", is_translation=False, status=c["status"],
        words=c["words"], rating=round(score * 2, 2) if score else None,
        votes=int(rating.group(2)) if rating and int(rating.group(2)) else None, views=c["views"],
        likes=c["favourites"], pop_raw=c["views"], adult=c["adult"], age_rating="18+" if c["adult"] else None,
        access=c["access"], created_at=_date(created.group(1)) if created else None,
        updated_at=_date(updated.group(1)) if updated else None, tags=c["labels"] or None,
        extra={"chars": c["chars"]},
    )


class Prodaman(Site):
    id = "prodaman"
    name = "Prodaman"
    home = BASE
    lang = "ru"
    min_interval = 2.0
    note = ("Russian web fiction, about 20,000 books, with categories and hashtags. Its reader shows a book in long "
            "pages, and each page becomes a chapter.")

    def _page(self, page: int) -> tuple[list[BookInfo], int]:
        try:
            s = self.http.get(f"{BASE}/books/", params={"sortby": "-1", "page": page}).text
        except NotFound:
            return [], 0
        return parse_list(s)

    def discover(self, state: dict):
        if state.get("full_done"):
            for page in range(1, 4):  # later passes: the newest books again
                books, _ = self._page(page)
                if not books:
                    break
                yield books
            return
        page = state.get("page", 1)
        while True:
            books, last = self._page(page)
            if books:
                yield books
            if not books or page >= last:
                state.update(full_done=True, page=1)
                return
            page += 1
            state["page"] = page

    def _url(self, book: dict) -> str:
        author, _, slug = book["sid"].partition("/")
        return f"{BASE}/{author}/books/{slug}"

    def details(self, book: dict) -> BookInfo:
        return parse_book(book["sid"], self.http.get(self._url(book)).text)

    # ----- text: the reader's pages
    @staticmethod
    def reader_text(s: str) -> str:
        bodies = [html_to_text(b) for b in _READER.findall(s)]
        return max(bodies, key=len, default="").strip()

    def chapters(self, book: dict) -> list[Chapter]:
        s = self.http.get(self._url(book), params={"nav": "ok"}).text
        total = re.search(r"Показано\s*<strong>\d+</strong>\s*из\s*<strong>(\d+)</strong>\s*страниц", s)
        pages = int(total.group(1)) if total else (1 if _READER.search(s) else 0)
        if not pages:
            raise NotFound("no text")
        return [Chapter(id=str(n), title=f"Страница {n}", index=n - 1) for n in range(1, pages + 1)]

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        params = {"nav": "ok"} if chapter.id == "1" else {"page": chapter.id}
        try:
            return self.reader_text(self.http.get(self._url(book), params=params).text)
        except NotFound:
            return ""
