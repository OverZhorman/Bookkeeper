"""Litnet (litnet.com): Russian and Ukrainian web fiction.

Catalog: the "top" listing, 20 books per page with all the details we need (genres, tags, stats, status, price),
read from the data the page carries for its own app (no separate details step).
Chapter list and text: the reader page; later pages of a long chapter come from the reader's own page request."""
import html as _html
import json
import re

from ..analysis.text import clean_text, detect_lang, html_to_text
from ..http import NotFound
from .base import BookInfo, Chapter, Site, SiteError

BASE = "https://litnet.com"
_STATE = re.compile(r'<script id="ng-state" type="application/json">(.*?)</script>', re.S)
_TEXT_BLOCK = re.compile(r'<div class="reader-text[^"]*"[^>]*>(.*?)</div>\s*(?:<div class="reader-pagination|'
                         r'<div class="navigation|<div class="reader-footer|<script)', re.S)


def _state(page_html: str) -> dict:
    m = _STATE.search(page_html)
    if not m:
        raise SiteError("page has no embedded data (layout changed?)")
    return json.loads(m.group(1))


def _api(state: dict, suffix: str):
    for v in state.values():
        if isinstance(v, dict) and str(v.get("u", "")).endswith(suffix):
            return v.get("b")
    return None


class Litnet(Site):
    id = "litnet"
    name = "Litnet"
    home = BASE
    lang = "ru"
    min_interval = 1.5
    note = "Russian and Ukrainian web fiction. Everything except the chapter text comes from the catalog pages."
    lists_adult = True
    login_url = f"{BASE}/ru/auth/login"
    # Litnet's login is several steps (phone or e-mail, then a code or password), so you log in yourself once;
    # Bookkeeper keeps the session.
    login_autofill = False
    login_benefit = ("18+ books, and the chapters you bought (Bookkeeper's downloads then include them). "
                     "In the window, press «Вход».")
    logged_in_js = "(document.querySelector('#ga-isLoggedIn') || {getAttribute: () => '0'}).getAttribute('value') === '1'"

    def check_login(self) -> bool | None:
        m = re.search(r'id="ga-isLoggedIn" value="(\d)"', self.http.get(f"{BASE}/ru").text)
        return (m.group(1) == "1") if m else None

    def _info(self, it: dict) -> BookInfo:
        authors = [a["name"].strip() for a in (it.get("author"), it.get("co_author")) if a and a.get("name")]
        flags, stats, prices = it.get("flags") or {}, it.get("stats") or {}, it.get("prices") or {}
        status = "completed" if flags.get("is_finished") else "frozen" if flags.get("is_frozen") else "ongoing"
        price = prices.get("price") or 0
        description = html_to_text(it.get("annotation") or "")
        labels = [g.get("name") for g in it.get("genres") or []] + [t.get("name") for t in it.get("tags") or []]
        cycle = it.get("cycle") or {}
        return BookInfo(
            sid=str(it["id"]), url=f"{BASE}/ru/book/{it['alias']}", title=(it.get("title") or "").strip(),
            authors=authors, description=description or None, cover=it.get("image"),
            lang=detect_lang(f"{it.get('title', '')} {description}") or None, status=status, is_translation=False,
            words=int(it["total_chr_length"] / 7.2) if it.get("total_chr_length") else None,
            views=stats.get("count_views"), likes=stats.get("count_likes"), pop_raw=stats.get("rating"),
            adult=bool(flags.get("is_adult_only") or it.get("adult_label") == 18),
            access="partial" if price else "free", created_at=it.get("published_at"),
            updated_at=it.get("updated_at"), tags=[x for x in labels if x],
            extra={"alias": it["alias"], "series": cycle.get("title"), "price": price}, complete=True,
        )

    def _top(self, page: int) -> tuple[list[BookInfo], int]:
        p = self.http.get(f"{BASE}/ru/top/all", params={"page": page})
        body = _api(_state(p.text), "/v2/genres/top") or {}
        return [self._info(it) for it in body.get("items") or []], int(body.get("total") or 0)

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
            books, total = self._top(page)
            state["total"] = total
            if not books:
                state.update(full_done=True, page=1)
                return
            yield books
            page += 1
            state["page"] = page

    def details(self, book: dict) -> BookInfo:  # the catalog already has everything
        raise NotImplementedError

    def _reader(self, book: dict, chapter_id: str | None = None):
        alias = (book.get("extra") or {}).get("alias")
        if not alias:
            raise SiteError("book alias unknown")
        params = {"c": chapter_id} if chapter_id else None
        return self.http.get(f"{BASE}/ru/reader/{alias}", params=params)

    def chapters(self, book: dict) -> list[Chapter]:
        page = self._reader(book).text
        select = re.search(r"<select[^>]*>(.*?)</select>", page, re.S)
        if not select:
            raise NotFound("no chapter list")
        out = []
        for i, (cid, attrs, title) in enumerate(re.findall(r'<option[^>]*value="(\d+)"([^>]*)>(.*?)</option>',
                                                          select.group(1), re.S)):
            locked = "disabled" in attrs
            out.append(Chapter(id=cid, title=clean_text(_html.unescape(re.sub(r"<[^>]+>", "", title))), index=i,
                               free=not locked))
        return out

    def _first_page(self, book: dict, chapter: Chapter) -> tuple[str, str]:
        page = self._reader(book, chapter.id)
        m = _TEXT_BLOCK.search(page.text)
        text = html_to_text(m.group(1)) if m else ""
        token = re.search(r'<meta name="csrf-token" content="([^"]+)"', page.text)
        return text, token.group(1) if token else ""

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        """The whole chapter: page 1 from the reader page, the rest from the reader's page request."""
        first, token = self._first_page(book, chapter)
        parts = []
        for n in range(1, 200):
            r = self.http.post(f"{BASE}/reader/get-page",
                               data={"chapterId": chapter.id, "page": str(n), "_csrf": token},
                               headers={"X-Requested-With": "XMLHttpRequest", "X-CSRF-Token": token})
            try:
                d = r.json()
            except ValueError:
                break
            if d.get("status") != 1 or not d.get("data"):
                break
            parts.append(html_to_text(d["data"]))
            if d.get("isLastPage"):
                break
        text = "\n".join(parts) if parts else first
        return re.sub(r"^(Глава[^\n]{0,80}\n)", "", text) if text.startswith("Глава") else text

    def opening_text(self, book: dict, max_chapters: int = 3, enough_words: int = 6000) -> list[str]:
        # The first page of each opening chapter is plenty for the narration check.
        out, words = [], 0
        for ch in self.chapters(book)[:max_chapters + 2]:
            if not ch.free:
                break
            text, _ = self._first_page(book, ch)
            if not text.strip():
                break
            out.append(text)
            words += len(text.split())
            if len(out) >= max_chapters or words >= enough_words:
                break
        return out
