"""Bookriver (bookriver.ru): Russian web fiction, about 26,000 books, mostly romance, with genres and tags.

Catalog: the all-genres list (/genre), most bought first, 24 books per page, read from the data the page carries for
its own app (title, authors, genres, tags, annotation, age, length, status, price). Details: the book page's data
(views, likes, how many are reading it, dates, series). Catalog only: robots.txt keeps programs off its reader's
chapter pages."""
import json
import re

from ..analysis.text import html_to_text
from ..http import NotFound
from .base import BookInfo, Site, SiteError, looks_adult

BASE = "https://bookriver.ru"
PER_PAGE = 24
STATUS = {"writing": "ongoing", "complete": "completed", "frozen": "frozen"}
_NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


def page_state(page: str) -> dict:
    m = _NEXT.search(page)
    if not m:
        raise SiteError("page has no embedded data (layout changed?)")
    return json.loads(m.group(1))["props"]["pageProps"]["state"]


def _cover(images) -> str | None:
    for x in images or []:
        if isinstance(x, dict) and x.get("sizeType") == "original" and x.get("url"):
            return x["url"]
    return next((x.get("url") for x in images or [] if isinstance(x, dict) and x.get("url")), None)


def book_info(b: dict) -> BookInfo:
    authors = b.get("authors") or ([b["author"]] if isinstance(b.get("author"), dict) else [])
    genres = [g.get("name") for g in b.get("genres") or [] if g.get("name")]
    tags = [t.get("name") for t in b.get("tags") or [] if t.get("name")]
    labels = list(dict.fromkeys(genres + tags))
    age = b.get("age") or None
    adult = age in ("18+", "21+") or bool(b.get("containsEroticScenes")) or looks_adult(labels)
    counters = b.get("counters") or {}
    readers = sum(counters.get(k) or 0 for k in ("readNow", "readLater", "readCompleted")) if counters else None
    cycle = b.get("cycle") or {}
    return BookInfo(
        sid=str(b["id"]), url=f"{BASE}/book/{b['slug']}", title=(b.get("name") or "").strip(),
        authors=[a["name"].strip() for a in authors if isinstance(a, dict) and (a.get("name") or "").strip()],
        description=html_to_text(b.get("annotation") or "").strip() or None, cover=_cover(b.get("coverImages")),
        lang="ru", is_translation=False, status=STATUS.get(b.get("statusComplete") or ""),
        words=int(b["symbols"] / 7.2) if b.get("symbols") else None, views=counters.get("views"),
        likes=counters.get("likes"), pop_raw=readers or None, adult=adult, age_rating=age,
        access="free" if b.get("free") else "partial", created_at=(b.get("createdAt") or "")[:10] or None,
        updated_at=(b.get("updatedAt") or "")[:10] or None, tags=labels or None,
        extra={"slug": b["slug"], "series": cycle.get("name"), "type": b.get("type"),
               "free_chapters": b.get("freeChaptersCount")},
    )


class Bookriver(Site):
    id = "bookriver"
    name = "Bookriver"
    home = BASE
    lang = "ru"
    min_interval = 2.0
    has_text = False
    note = ("Russian web fiction, about 26,000 books, mostly romance, with genres and tags. Catalog only: its "
            "robots.txt keeps programs off the reader's chapters.")

    def _page(self, page: int) -> tuple[list[BookInfo], int]:
        try:
            state = page_state(self.http.get(f"{BASE}/genre", params={"page": page} if page > 1 else None).text)
        except NotFound:
            return [], 0
        books = [book_info(b) for b in ((state.get("pagesFilter") or {}).get("genre") or {}).get("books") or []
                 if b.get("id") and b.get("slug")]
        pag = state.get("pagination") or {}
        last = -(-int(pag.get("total") or 0) // int(pag.get("perPage") or PER_PAGE)) if pag.get("total") else page
        return books, last

    def discover(self, state: dict):
        if state.get("full_done"):
            for page in range(1, 4):  # later passes: the first pages again
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

    def details(self, book: dict) -> BookInfo:
        slug = (book.get("extra") or {}).get("slug")
        if not slug:
            m = re.search(r"/book/([^/?#]+)", book.get("url") or "")
            slug = m.group(1) if m else None
        if not slug:
            raise SiteError("book address unknown")
        data = ((page_state(self.http.get(f"{BASE}/book/{slug}").text).get("book") or {}).get("bookPage")) or {}
        if not data.get("id"):
            raise NotFound(slug)
        return book_info(data)
