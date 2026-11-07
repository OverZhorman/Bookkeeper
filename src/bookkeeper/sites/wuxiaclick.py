"""Wuxia.click: English translations of Chinese, Korean and Japanese web novels.

Every page carries its data as JSON (Next.js), so we read that: the browse listing (24 novels per page),
each novel's page (genres, ~40 NovelUpdates-style tags, alternative titles), and chapter pages (paragraphs)."""
import json
import re

from ..http import NotFound
from .base import BookInfo, Chapter, Site, SiteError

BASE = "https://wuxia.click"
_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
STATUS = {"ONGOING": "ongoing", "COMPLETED": "completed", "HIATUS": "frozen", "DROPPED": "frozen"}
ORIGIN = {"chinese": "cn", "korean": "kr", "japanese": "jp", "zh": "cn", "ko": "kr", "ja": "jp"}


def _props(page_html: str) -> dict:
    m = _DATA.search(page_html)
    if not m:
        raise SiteError("page has no embedded data (layout changed?)")
    return json.loads(m.group(1)).get("props", {}).get("pageProps", {})


class WuxiaClick(Site):
    id = "wuxiaclick"
    name = "Wuxia.click"
    home = BASE
    lang = "en"
    min_interval = 1.5
    note = "English translations of Asian web novels, with NovelUpdates-style tags."

    def _cover(self, n: dict) -> str | None:
        if n.get("coverKey"):
            return f"{BASE}/api/media/{n['coverKey']}" if not str(n["coverKey"]).startswith("http") else n["coverKey"]
        return None

    def _base_info(self, n: dict) -> BookInfo:
        origin = ORIGIN.get(str(n.get("originalLanguage") or "").lower())
        return BookInfo(
            sid=n["slug"], url=f"{BASE}/novel/{n['slug']}", title=n.get("title") or n["slug"],
            authors=[n["authorName"]] if n.get("authorName") else [], lang="en",
            status=STATUS.get(str(n.get("status") or "").upper(), "unknown"), is_translation=True, origin=origin,
            chapters=n.get("chapterCount"), rating=round(float(n["ratingAvg"]) * 2, 2) if n.get("ratingAvg") else None,
            votes=n.get("ratingCount"), views=n.get("viewsTotal"), pop_raw=n.get("viewsTotal"),
            access="free", updated_at=(n.get("latestChapterAt") or "")[:10] or None,
            extra={"first": n.get("firstChapterNumber"), "latest": n.get("latestChapterNumber"),
                   "mtl": bool(n.get("isMtl"))},
        )

    def _browse(self, page: int) -> tuple[list[BookInfo], int]:
        p = self.http.get(f"{BASE}/browse", params={"order_by": "new", "page": page})
        listing = _props(p.text).get("listing") or {}
        return [self._base_info(n) for n in listing.get("items") or []], int(listing.get("totalPages") or 0)

    def discover(self, state: dict):
        if state.get("full_done"):
            for page in range(1, 4):
                books, _ = self._browse(page)
                if not books:
                    break
                yield books
            return
        page = state.get("page", 1)
        while True:
            books, pages = self._browse(page)
            if not books or (pages and page > pages):
                state.update(full_done=True, page=1)
                return
            yield books
            page += 1
            state["page"] = page

    def details(self, book: dict) -> BookInfo:
        p = self.http.get(f"{BASE}/novel/{book['sid']}")
        n = _props(p.text).get("novel")
        if not n:
            raise NotFound(book["sid"])
        info = self._base_info(n)
        info.alt_titles = [t for t in n.get("altTitles") or [] if isinstance(t, str)]
        info.authors = [(n.get("author") or {}).get("name")] if (n.get("author") or {}).get("name") else info.authors
        info.description = n.get("description")
        info.cover = self._cover(n)
        info.adult = bool(n.get("isAdult"))
        info.likes = n.get("libraryCount")
        info.created_at = (n.get("createdAt") or "")[:10] or None
        labels = [g.get("name") for g in n.get("genres") or []] + [t.get("name") for t in n.get("tags") or []]
        if n.get("isMtl"):
            labels.append("Machine translation")
        info.tags = [x for x in labels if x]
        info.extra["novelupdates"] = n.get("sourceUrl")
        return info

    def chapters(self, book: dict) -> list[Chapter]:
        extra = book.get("extra") or {}
        first, latest = extra.get("first") or 1, extra.get("latest")
        if not latest:
            info = self.details(book)
            first, latest = info.extra.get("first") or 1, info.extra.get("latest") or 0
        return [Chapter(id=str(n), title=f"Chapter {n}", index=i) for i, n in enumerate(range(first, latest + 1))]

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        try:
            p = self.http.get(f"{BASE}/chapter/{book['sid']}-{chapter.id}")
        except NotFound:
            return ""
        data = _props(p.text).get("data") or {}
        ch = data.get("chapter") or {}
        if ch.get("title"):
            chapter.title = ch["title"]
        paras = ch.get("paragraphs") or []
        return "\n".join(x if isinstance(x, str) else str(x.get("text", "")) for x in paras)
