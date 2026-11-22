"""Litgorod (litgorod.ru): Russian web fiction, about 36,000 books, with genres and tags ("В тексте есть").

Catalog: robots.txt keeps programs off every address with a "?" (so off the lists, which page with ?page=), but the
sitemap lists every book. Bookkeeper reads the sitemap and then each book page, ten at a time: the book's data block
(title, author, genres, tags, annotation, price, likes) and its counters (views, libraries, length, age, status).
Catalog only for now: Bookkeeper doesn't read its reader pages."""
import html as _html
import json
import re

from ..analysis.text import clean_text, html_to_text
from ..http import NotFound
from .base import BookInfo, Site, SiteError, looks_adult

BASE = "https://litgorod.ru"
PER_BATCH = 10
STATUS = {"в процессе написания": "ongoing", "завершена": "completed", "заморожена": "frozen"}
_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


def _counter(s: str, name: str) -> int | None:
    m = re.search(r'data-tooltip="' + name + r' &#183; (\d+)"', s)
    return int(m.group(1)) if m else None


def parse_book(sid: str, s: str) -> BookInfo:
    data = None
    for block in _LD.findall(s):
        try:
            d = json.loads(block)
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("@type") == "Book":
            data = d
            break
    if not data:
        raise SiteError("unexpected page layout (no book data)")
    author = data.get("author") or {}
    genres = list(dict.fromkeys(g for g in data.get("genre") or [] if g))
    tags = [t for t in data.get("keywords") or [] if t]
    likes = next((x.get("userInteractionCount") for x in data.get("interactionStatistic") or []
                  if str(x.get("interactionType", "")).endswith("LikeAction")), None)
    price = (data.get("offers") or {}).get("price")
    age = re.search(r'<div class="b-book_adult_old">\s*(\d+\+)\s*</div>', s)
    status = re.search(r'<div\s+class="b-book_item__status[^"]*">\s*<div class="_text">(.*?)</div>', s, re.S)
    cycle = re.search(r'<div class="b-book_item__cycle">.*?<b>(.*?)</b>', s, re.S)
    chars = _counter(s, "Количество знаков")
    labels = genres + [t for t in tags if t not in genres]
    adult = bool(age and age.group(1) in ("18+", "21+")) or looks_adult(labels)
    return BookInfo(
        sid=sid, url=f"{BASE}/books/view/{sid}", title=_text(data.get("name") or ""),
        authors=[_text(author["name"])] if isinstance(author, dict) and author.get("name") else [],
        description=html_to_text(data.get("description") or "").strip() or None, cover=data.get("image") or None,
        lang="ru", is_translation=False, status=STATUS.get(_text(status.group(1)).lower()) if status else None,
        words=int(chars / 7.2) if chars else None, views=_counter(s, "Просмотры"), likes=likes,
        pop_raw=_counter(s, "Библиотеки"), adult=adult, age_rating=age.group(1) if age else None,
        access="partial" if price and float(price) > 0 else "free", updated_at=data.get("dateModified"),
        tags=labels or None, extra={"series": _text(cycle.group(1)) if cycle else None, "chars": chars,
                                    "libraries": _counter(s, "Библиотеки")},
        complete=True,
    )


class Litgorod(Site):
    id = "litgorod"
    name = "Litgorod"
    home = BASE
    lang = "ru"
    # About one page every 2.3 seconds drew "429 Too Many Requests" after an hour (1,500 book pages): go slower.
    min_interval = 5.0
    has_text = False
    note = ("Russian web fiction, about 36,000 books, with genres and tags. Its robots.txt keeps programs off its "
            "lists, so Bookkeeper reads its sitemap and then each book page. Catalog only for now.")

    def _sitemaps(self) -> list[str]:
        s = self.http.get(f"{BASE}/sitemap.xml").text
        return re.findall(r"<loc>(https://litgorod\.ru/sitemap_\d+\.xml)</loc>", s)

    def _ids(self, url: str) -> list[str]:
        return re.findall(r"<loc>https://litgorod\.ru/books/view/(\d+)</loc>", self.http.get(url).text)

    def _book(self, sid: str) -> BookInfo | None:
        try:
            return parse_book(sid, self.http.get(f"{BASE}/books/view/{sid}").text)
        except NotFound:
            return None

    def discover(self, state: dict):
        if state.get("full_done"):
            # Later passes: books newer than any seen so far (the last sitemap lists them).
            maps = self._sitemaps()
            newer = [i for i in self._ids(maps[-1]) if int(i) > state.get("max_id", 0)] if maps else []
            for n in range(0, len(newer), PER_BATCH):
                chunk = newer[n:n + PER_BATCH]
                books = [b for b in map(self._book, chunk) if b]
                state["max_id"] = max([state.get("max_id", 0)] + [int(i) for i in chunk])
                if books:
                    yield books
            return
        maps = self._sitemaps()
        while state.get("si", 0) < len(maps):
            ids = self._ids(maps[state.get("si", 0)])
            while state.get("offset", 0) < len(ids):
                chunk = ids[state.get("offset", 0):state.get("offset", 0) + PER_BATCH]
                books = [b for b in map(self._book, chunk) if b]
                state["offset"] = state.get("offset", 0) + len(chunk)
                state["max_id"] = max([state.get("max_id", 0)] + [int(i) for i in chunk])
                if books:
                    yield books
            state.update(si=state.get("si", 0) + 1, offset=0)
        state.update(full_done=True, si=0, offset=0)

    def details(self, book: dict) -> BookInfo:
        info = self._book(book["sid"])
        if not info:
            raise NotFound(book["sid"])
        return info
