"""WebNovel (webnovel.com): English web novels, original and translated.

Catalog only: Bookkeeper reads the site's own catalog feed (20 books per page, most popular first) for titles, authors,
categories, tags, ratings and chapter counts. WebNovel protects its chapter text (an encrypted chapter list and a
scrambled per-chapter font), so Bookkeeper doesn't read chapters there: no narration check and no downloads.
Copies of the same book on other sites still share their narration with it. To read a book, open it on WebNovel."""
import re

from .base import BookInfo, Chapter, Site

BASE = "https://www.webnovel.com"


class WebNovel(Site):
    id = "webnovel"
    name = "WebNovel"
    home = BASE
    lang = "en"
    min_interval = 2.0
    note = ("Catalog only (titles, tags, ratings): WebNovel protects its chapter text, so there's no narration check "
            "or download here. Copies of a book on other sites share their narration with it.")
    lists_adult = True
    has_text = False
    extra_settings = {"language": {"label": "Catalog language (en or ru)", "default": "en"},
                      "pages": {"label": "Catalog pages to read (20 books each, most popular first)", "default": "500"}}

    def _token(self) -> str:
        token = self.http.client.cookies.get("_csrfToken")
        if not token:
            self.http.get(f"{BASE}/stories/novel", params={"orderBy": 1})
            token = self.http.client.cookies.get("_csrfToken") or ""
        return token

    def _info(self, it: dict, rank: int) -> BookInfo:
        bid = str(it["bookId"])
        tags = [t.get("tagName") for t in it.get("tagInfo") or [] if t.get("tagName")]
        labels = [x for x in [it.get("categoryName"), *[t.title() if t.isupper() else t for t in tags]] if x]
        score = it.get("totalScore")
        lang = (self.settings.get("language") or "en").strip()
        return BookInfo(
            sid=bid, url=f"{BASE}/{'ru/' if lang == 'ru' else ''}book/{bid}", title=(it.get("bookName") or "").strip() or bid,
            authors=[it["authorName"].replace("﻿", "").strip()] if (it.get("authorName") or "").strip("﻿ ") else [],
            description=(it.get("description") or "").strip() or None,
            cover=f"https://book-pic.webnovel.com/bookcover/{bid}?imageMogr2/thumbnail/300x",
            lang=lang, is_translation=bool(it.get("translateMode")), chapters=it.get("chapterNum") or None,
            rating=round(float(score) * 2, 2) if score else None, pop_raw=1_000_000 - rank,
            adult=any(t.upper() in ("R18", "R-18", "MATURE") for t in tags), access="partial",
            tags=labels, complete=True, extra={"first_chapter": it.get("firstChapterId")},
        )

    def _page(self, page: int) -> tuple[list[BookInfo], bool]:
        lang = (self.settings.get("language") or "en").strip()
        data = self.http.get_json(f"{BASE}/go/pcm/category/categoryAjax", params={
            "_csrfToken": self._token(), "language": lang, "categoryId": 0, "categoryType": 1, "orderBy": 1,
            "pageIndex": page, "bookStatus": 0}, headers={"Accept": "application/json", "Referer": f"{BASE}/stories/novel"})
        d = data.get("data") or {}
        items = d.get("items") or []
        return [self._info(it, (page - 1) * 20 + i) for i, it in enumerate(items) if it.get("bookId")], bool(d.get("isLast"))

    def discover(self, state: dict):
        limit = int(re.sub(r"\D", "", str(self.settings.get("pages") or "500")) or 500)
        if state.get("full_done"):
            state.update(page=1, full_done=False)  # each pass re-reads the ranking (it changes)
        page = state.get("page", 1)
        while page <= limit:
            books, last = self._page(page)
            if books:
                yield books
            page += 1
            state["page"] = page
            if last or not books:
                break
        state.update(full_done=True, page=1)

    def details(self, book: dict) -> BookInfo:
        raise NotImplementedError  # the catalog feed already has everything we use

    def chapters(self, book: dict) -> list[Chapter]:
        return []

    def opening_text(self, book: dict, max_chapters: int = 3, enough_words: int = 6000) -> list[str]:
        return []
