"""GoodNovel (goodnovel.com): English web novels, originals and translations, with tags (Fast-Paced Plot, System,
Level up, Hidden Identity, First Person POV...). Most books sell their later chapters; the first ones are free.

Catalog: each genre's list, most popular first (20 books per page, at most 100 pages a genre). Every book in a list
carries everything Bookkeeper keeps (genres, tags, length in words, views, rating, status, original or translation),
read from the data the page carries for its own app, so there's no separate details step. Text: the book page lists
its first ten chapters (which of them are free), and each chapter page carries its text. robots.txt keeps programs off
the full chapter list and the other language versions, so only the English site and the first chapters are read."""
import json
import re

from ..http import NotFound
from .base import BookInfo, Chapter, Site, SiteError, looks_adult

BASE = "https://www.goodnovel.com"
GENRES = ["Romance-novels", "Apocalypse-novels", "Werewolf-novels", "Mafia-novels", "System-novels",
          "Fantasy-novels", "Urban-novels", "LGBTQ-novels", "YA-TEEN-novels", "Paranormal-novels",
          "Mystery-Thriller-novels", "Eastern-novels", "Games-novels", "History-novels", "MM-Romance-novels",
          "Sci-Fi-novels", "War-novels", "Other-novels"]
MAX_PAGES = 100                               # the lists stop there
HEADERS = {"Accept-Language": "en-US,en;q=0.9"}  # otherwise the pages come in the reader's language
STATUS = {"ONGOING": "ongoing", "COMPLETED": "completed", "COMPLETE": "completed"}
_STATE = re.compile(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;?\s*(?:\(function|</script>)", re.S)


def page_state(page: str) -> dict:
    m = _STATE.search(page)
    if not m:
        raise SiteError("page has no embedded data (layout changed?)")
    return json.loads(m.group(1))


def _count(s) -> int | None:
    """"2.5M", "210.1K", 1342 as numbers."""
    m = re.match(r"([\d.,]+)\s*([KMB]?)", str(s or "").strip(), re.I)
    if not m:
        return None
    return int(float(m.group(1).replace(",", "")) * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2).upper()])


def book_info(it: dict) -> BookInfo:
    sid = str(it["bookId"])
    slug = it.get("bookResourceUrl") or sid
    labels = [x for x in (it.get("genreNames") or []) + (it.get("newTagsNames") or []) if x]
    kind = (it.get("novelType") or "").upper()
    return BookInfo(
        sid=sid, url=f"{BASE}/book/{slug}", title=(it.get("bookName") or "").strip() or sid,
        authors=[it["pseudonym"].strip()] if (it.get("pseudonym") or "").strip() else [],
        description=(it.get("introduction") or "").strip() or None, cover=it.get("cover") or None, lang="en",
        status=STATUS.get((it.get("writeStatus") or "").upper()),
        is_translation=True if kind == "TRANSLATION" else False if kind == "ORIGINAL" else None,
        chapters=it.get("chapterCount"), words=it.get("totalWords") or None,
        rating=round(float(it["ratings"]), 2) if it.get("ratings") else None,
        views=_count(it.get("viewCountDisplay")), pop_raw=_count(it.get("viewCountDisplay")),
        adult=bool(it.get("pornographic") or it.get("mature")) or looks_adult(labels),
        access="free" if it.get("freeBook") else "partial",
        created_at=(it.get("ctime") or "")[:10] or None, updated_at=(it.get("lastChapterTime") or "")[:10] or None,
        tags=list(dict.fromkeys(labels)),
        extra={"slug": slug, "free_chapters": it.get("chargeChapterNum")}, complete=True,
    )


class GoodNovel(Site):
    id = "goodnovel"
    name = "GoodNovel"
    home = BASE
    lang = "en"
    min_interval = 2.5
    note = ("English web novels, originals and translations, with tags. Bookkeeper reads each genre's most popular "
            "books (up to 2,000 a genre). Most books sell their later chapters: narration checks and downloads use "
            "the free first ones.")

    def _get(self, path: str, **kw) -> str:
        return self.http.get(f"{BASE}{path}", headers=HEADERS, **kw).text

    def _list(self, genre: str, page: int) -> tuple[list[BookInfo], int]:
        try:
            browse = page_state(self._get(f"/stories/{genre}", params={"page": page} if page > 1 else None))["Browse"]
        except NotFound:
            return [], 0
        books = [book_info(it) for it in browse.get("bookList") or []
                 if it.get("bookId") and (it.get("language") or "ENGLISH") == "ENGLISH"]
        return books, min(int(browse.get("totalPage") or 1), MAX_PAGES)

    def discover(self, state: dict):
        if state.get("full_done"):
            for genre in GENRES:  # later passes: the first pages again
                for page in range(1, 3):
                    books, _ = self._list(genre, page)
                    if books:
                        yield books
            return
        while state.get("gi", 0) < len(GENRES):
            genre, page = GENRES[state.get("gi", 0)], state.get("page", 1)
            books, last = self._list(genre, page)
            if books:
                yield books
            if not books or page >= last:
                state.update(gi=state.get("gi", 0) + 1, page=1)
            else:
                state["page"] = page + 1
        state.update(full_done=True, gi=0, page=1)

    def details(self, book: dict) -> BookInfo:  # the lists already have everything
        raise NotImplementedError

    def _slug(self, book: dict) -> str:
        slug = (book.get("extra") or {}).get("slug")
        if not slug:
            m = re.search(r"/book/([^/?#]+)", book.get("url") or "")
            slug = m.group(1) if m else None
        if not slug:
            raise SiteError("book address unknown")
        return slug

    def chapters(self, book: dict) -> list[Chapter]:
        catalog = page_state(self._get(f"/book/{self._slug(book)}")).get("Catalog") or {}
        out = [Chapter(id=str(c["id"]), title=(c.get("chapterName") or "").strip() or f"Chapter {i + 1}", index=i,
                       free=bool(c.get("unlock")), extra={"path": c.get("chapterResourceUrl")})
               for i, c in enumerate(catalog.get("catalogs") or []) if c.get("id")]
        if not out:
            raise NotFound("no chapter list")
        return out

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        path = chapter.extra.get("path") or f"Chapter-{chapter.index + 1}_{chapter.id}"
        try:
            data = (page_state(self._get(f"/book/{self._slug(book)}/{path}")).get("bookCapter") or {})
        except NotFound:
            return ""
        ch = data.get("chapterData") or {}
        if ch.get("price") or ch.get("charge"):
            return ""
        return "\n".join(p.strip() for p in (ch.get("content") or "").split("\n") if p.strip())
