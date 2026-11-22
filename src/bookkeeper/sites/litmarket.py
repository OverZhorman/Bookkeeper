"""Litmarket (litmarket.ru): Russian web fiction, about 108,000 e-books, with genres and hashtag tags.

Catalog: the e-book list (/books/ebooks), 10 books per page. Each card already has everything Bookkeeper keeps (author,
series, genres, tags, the whole annotation, status, pages, views, likes, how many readers keep it, price, dates), so
there's no separate details step. Catalog only for now: its reader loads the text through its own app, which
Bookkeeper doesn't read yet."""
import html as _html
import re
from datetime import datetime

from ..analysis.text import clean_text, html_to_text
from ..http import NotFound
from .base import BookInfo, Site, looks_adult

BASE = "https://litmarket.ru"
STATUS = {"закончена": "completed", "в работе": "ongoing", "заморожена": "frozen"}


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


def _count(s: str) -> int | None:
    """"32k", "1.2m", "3622" as numbers."""
    m = re.search(r"([\d.,]+)\s*([kKmMкКмМ]?)", s or "")
    if not m:
        return None
    mult = {"k": 1e3, "к": 1e3, "m": 1e6, "м": 1e6}.get(m.group(2).lower(), 1)
    return int(float(m.group(1).replace(",", ".")) * mult)


def _date(s: str) -> str | None:
    try:
        return datetime.strptime(s.strip(), "%d.%m.%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def parse_card(bid: str, c: str) -> BookInfo | None:
    link = re.search(r'<div class="card-title">\s*<a\s+href="https://litmarket\.ru/books/([^"]+)">(.*?)</a>', c, re.S)
    if not link:
        return None
    byline = re.search(r'<div class="author">(.*?)</div>', c, re.S)
    authors = [_text(a) for a in re.findall(r'<a\s[^>]*itemprop="author"[^>]*>(.*?)</a>', byline.group(1), re.S)]         if byline else []
    cycle = re.search(r'<div class="card-cycle">.*?<a[^>]*>(.*?)</a>', c, re.S)
    likes = re.search(r'<span class="rating-total">(\d+)</span>', c)
    shelves = re.search(r'<span class="libraries-count">\((\d+)\)</span>', c)
    tags = [_text(t).lstrip("#") for t in re.findall(r'<a\s+href="https://litmarket\.ru/books/tag/[^"]+"\s+class="label">(.*?)</a>', c)]
    genres = [_text(g) for g in re.findall(r'<a\s+href="https://litmarket\.ru/books/genres/[^"]+"[^>]*>(.*?)</a>', c, re.S)]
    about = re.search(r'<div itemprop="about" class="card-description">(.*?)</div>', c, re.S)
    status = re.search(r'<div class="book-ebook-status">(.*?)</div>', c, re.S)
    created = re.search(r"<span>Создана:</span>\s*<time>\s*(.*?)\s*</time>", c, re.S)
    updated = re.search(r"<span>Обновлена:</span>\s*<time>\s*(\d\d\.\d\d\.\d{4})\s*</time>", c, re.S)
    pages = re.search(r'lmfont-pages"[^>]*></i>\s*<span>(\d+)\s*стр', c)
    views = re.search(r'lmfont-views"[^>]*></i>\s*([^<]+)<', c)
    cover = re.search(r'<img\s+class="img[^"]*"[^>]*src="([^"]+)"', c)
    free = "read-price_free" in c
    priced = "read-price" in c
    labels = list(dict.fromkeys(x for x in genres + tags if x))
    series = _text(cycle.group(1)) if cycle else None
    return BookInfo(
        sid=bid, url=f"{BASE}/books/{link.group(1)}", title=_text(link.group(2)), authors=authors,
        description=html_to_text(about.group(1)).strip() or None if about else None,
        cover=(BASE + cover.group(1) if cover.group(1).startswith("/") else cover.group(1)) if cover else None,
        lang="ru", is_translation=False, status=STATUS.get(_text(status.group(1)).lower()) if status else None,
        likes=int(likes.group(1)) if likes else None, views=_count(views.group(1)) if views else None,
        pop_raw=int(shelves.group(1)) if shelves else None, adult=looks_adult(labels) or ">18+<" in c,
        access="free" if free else "partial" if priced else None, created_at=_date(created.group(1)) if created else None,
        updated_at=_date(updated.group(1)) if updated else None, tags=labels,
        extra={"slug": link.group(1), "series": series, "pages": int(pages.group(1)) if pages else None,
               "shelved": int(shelves.group(1)) if shelves else None},
        complete=True,
    )


def parse_list(page: str) -> tuple[list[BookInfo], int]:
    end = page.find('<ul class="pagination"')  # the last card ends there, before the page's sidebar and footer
    body = page[:end] if end > 0 else page
    parts = re.split(r'<div class="item" data-book-id="(\d+)">', body)
    books = [parse_card(parts[i], parts[i + 1]) for i in range(1, len(parts) - 1, 2)]
    pages = [int(n) for n in re.findall(r'href="https://litmarket\.ru/books/ebooks\?page=(\d+)"', page)]
    return [b for b in books if b], max(pages, default=1)


class Litmarket(Site):
    id = "litmarket"
    name = "Litmarket"
    home = BASE
    lang = "ru"
    min_interval = 2.0
    has_text = False
    note = ("Russian web fiction, about 108,000 e-books, with genres and tags. Catalog only for now: its reader loads "
            "the text through its own app.")

    def _page(self, page: int) -> tuple[list[BookInfo], int]:
        try:
            s = self.http.get(f"{BASE}/books/ebooks", params={"page": page} if page > 1 else None).text
        except NotFound:
            return [], 0
        return parse_list(s)

    def discover(self, state: dict):
        if state.get("full_done"):
            for page in range(1, 6):  # later passes: the first pages again
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

    def details(self, book: dict) -> BookInfo:  # the list already has everything
        raise NotImplementedError
