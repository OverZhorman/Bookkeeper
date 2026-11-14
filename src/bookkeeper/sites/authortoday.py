"""Author.Today: Russian original web fiction.

Catalog: listing pages (25 books each). The site shows at most 400 pages per listing, so we walk several
listings (all books by likes / views / recent, then every genre by likes) to reach as much of the catalog
as possible, adding new genres as they show up on book cards.
Details: the book page (tags, chapters). Chapter text: read through a browser, see browser.py."""
import html as _html
import re
import urllib.parse

from ..analysis.text import clean_text, html_to_text
from ..browser import BrowserUnavailable
from ..http import NotFound
from .base import BookInfo, Chapter, Site, SiteError, TemporaryError

BASE = "https://author.today"
# Text the reader shows instead of a chapter you can't read (paid, or needs a login / age check).
LOCKED = "платном доступе|войдите в свой аккаунт|приобрести|купите книгу|доступно только|подтвердите возраст"
START_LISTINGS = [["all", "likes"], ["all", "views"], ["all", "comments"], ["all", "trending"], ["all", "recent"]]
KNOWN_GENRES = [
    "litrpg", "realrpg", "popadantsy", "popadantsy-v-magicheskie-miry", "popadantsy-vo-vremeni", "sf-history",
    "fantasy", "sci-fi", "adventure", "dark-fantasy", "epic-fantasy", "heroic-fantasy", "fantasy-action",
    "magic-school", "historical-fantasy", "everyday-fantasy", "back-to-ussr", "sf-action", "boyar-anime",
    "urban-fantasy", "sf-space", "sf-social", "sf-humor", "romantic-fantasy", "historical-adventure", "action",
    "rusreal", "humor", "dorama", "postapocalyptic", "cyberpunk", "ironical-fantasy", "wuxia",
]
_NUM = re.compile(r"[\d\s ]+")


def _int(text: str | None) -> int | None:
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    return int(digits) if digits else None


def _unescape(s: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", s or "")))


def _parse_common(block: str) -> dict:
    """Fields that look the same on listing cards and on the book page."""
    out = {}
    m = re.search(r'class="book-genres">(.*?)</div>', block, re.S)
    if m:
        names = [_unescape(x) for x in re.findall(r"<a[^>]*>(.*?)</a>", m.group(1), re.S)]
        out["genres"] = [n for n in names if n]
        out["genre_slugs"] = re.findall(r'href="/work/genre/([a-z0-9-]+)"', m.group(1))
    m = re.search(r"([\d\s ]{3,})\s*(?:<noindex>)?\s*зн\.", block)
    if m:
        out["chars"] = _int(m.group(1))
    if "весь текст" in block:
        out["status"] = "completed"
    elif "в процессе" in block:
        out["status"] = "ongoing"
    m = re.search(r'data-hint="Просмотры · ([\d\s ]+)"', block)
    out["views"] = _int(m.group(1)) if m else None
    m = re.search(r'data-hint="Понравилось · ([\d\s ]+)"', block) or re.search(r"likeCount:\s*(\d+)", block)
    out["likes"] = _int(m.group(1)) if m else None
    m = re.search(r'data-time="(\d{4}-\d\d-\d\d)T', block)
    out["updated"] = m.group(1) if m else None
    m = re.search(r'Цикл:\s*</span>\s*<a[^>]*>(.*?)</a>', block, re.S)
    out["series"] = _unescape(m.group(1)) if m else None
    if re.search(r'"price":\s*[1-9]|>Цена<|text-success">Цена', block):
        out["access"] = "paid"
    elif "Подписка" in block or "подписк" in block[:2000]:
        out["access"] = "partial"
    else:
        out["access"] = "free"
    out["adult"] = "label-adult-only" in block or "18+</span>" in block
    return out


class AuthorToday(Site):
    id = "authortoday"
    name = "Author.Today"
    home = BASE
    lang = "ru"
    min_interval = 1.5
    needs_browser_for_text = True
    note = ("Tags come from each book's page. Chapter text is read through Microsoft Edge on your computer, "
            "because the site scrambles it for anything that isn't a browser.")
    lists_adult = True
    extension_downloads = ("ExLoader",)
    login_url = f"{BASE}/account/login"
    login_benefit = ("18+ books, and the chapters you bought: Bookkeeper's downloads then include them "
                     "(only what your account can read).")
    login_form = {"user": "#Login", "password": "#Password, input[name=Password]"}
    logged_in_js = r"/isAuthenticated:\s*true/.test(document.documentElement.innerHTML)"

    def check_login(self) -> bool | None:
        page = self.http.get(f"{BASE}/").text
        if re.search(r"isAuthenticated:\s*true", page):
            return True
        if re.search(r"isAuthenticated:\s*false", page):
            return False
        return None

    def _card(self, block: str) -> BookInfo | None:
        m = re.search(r'href="/work/(\d+)"', block)
        if not m:
            return None
        wid = m.group(1)
        t = re.search(r'<div class="book-title">\s*<a[^>]*>(.*?)</a>', block, re.S)
        authors = [_unescape(x) for x in re.findall(
            r'<a[^>]*href="/u/[^"]+/works"[^>]*>(.*?)</a>', re.search(r'class="book-author">(.*?)</div>', block, re.S).group(1)
        )] if re.search(r'class="book-author">', block) else []
        cover = re.search(r'<img src="([^"]+)"', block)
        ann = re.search(r'class="annotation[^"]*">(.*?)</div>', block, re.S)
        c = _parse_common(block)
        info = BookInfo(
            sid=wid, url=f"{BASE}/work/{wid}", title=_unescape(t.group(1)) if t else f"#{wid}",
            authors=authors, description=html_to_text(ann.group(1)) if ann else None,
            cover=_html.unescape(cover.group(1)).split("?")[0] if cover else None, lang="ru",
            status=c.get("status"), is_translation=False, words=int(c["chars"] / 7.2) if c.get("chars") else None,
            views=c.get("views"), likes=c.get("likes"), pop_raw=c.get("likes"), access=c.get("access"),
            updated_at=c.get("updated"), adult=c.get("adult", False),
            tags=c.get("genres"), partial_tags=True,  # genres only; the book page adds the real tags
            extra={"series": c.get("series"), "genre_slugs": c.get("genre_slugs", [])},
        )
        return info

    def _listing(self, genre: str, sorting: str, page: int) -> list[BookInfo]:
        p = self.http.get(f"{BASE}/work/genre/{genre}", params={"sorting": sorting, "page": page})
        blocks = p.text.split('<div class="book-row">')[1:]
        return [b for b in (self._card(x) for x in blocks) if b]

    def discover(self, state: dict):
        if state.get("full_done"):
            # Later passes: the 5 newest pages of recently updated books.
            for page in range(1, 6):
                books = self._listing("all", "recent", page)
                if not books:
                    break
                yield books
            return
        if "queue" not in state:
            state["queue"] = [list(x) for x in START_LISTINGS] + [[g, "likes"] for g in KNOWN_GENRES]
            state["i"], state["page"] = 0, 1
        while state["i"] < len(state["queue"]):
            genre, sorting = state["queue"][state["i"]]
            try:
                books = self._listing(genre, sorting, state["page"])
            except NotFound:
                if state["page"] > 1:
                    books = []  # past the list's last page: that's how the site says there are no more
                else:
                    # A genre the site dropped, or a moment's "not found": the first page is tried three times
                    # (five minutes apart) before moving on.
                    at = [state["i"], state["page"]]
                    miss = state.get("missing") or {}
                    state["missing"] = {"at": at, "n": miss.get("n", 0) + 1 if miss.get("at") == at else 1}
                    if state["missing"]["n"] < 3:
                        raise
                    books = []
            state.pop("missing", None)
            if books:
                known = {g for g, _ in state["queue"]}
                for b in books:
                    for slug in b.extra.pop("genre_slugs", []):
                        if slug not in known and slug != "all":
                            state["queue"].append([slug, "likes"])
                            known.add(slug)
                yield books
            if not books or state["page"] >= 400:  # the site never shows more than 400 pages
                state["i"] += 1
                state["page"] = 1
            else:
                state["page"] += 1
        state["full_done"] = True

    def _work_page(self, wid: str) -> str:
        return self.http.get(f"{BASE}/work/{wid}").text

    def details(self, book: dict) -> BookInfo:
        wid = book["sid"]
        s = self._work_page(wid)
        if 'class="book-title"' not in s:
            raise SiteError("unexpected page layout (no title)")
        panel_m = re.search(r'<div class="book-meta-panel">(.*?)<div class="tab-pane fade" id="tab-chapters"', s, re.S)
        panel = panel_m.group(1) if panel_m else s
        title = _unescape(re.search(r'<h1 class="book-title"[^>]*>(.*?)</h1>', s, re.S).group(1))
        authors = re.findall(r'<meta content="([^"]+)" itemprop="name">', panel)
        tags_m = re.search(r'<span class="tags">(.*?)</span>', s, re.S)
        tags = [_unescape(x) for x in re.findall(r"<a[^>]*>(.*?)</a>", tags_m.group(1), re.S)] if tags_m else []
        c = _parse_common(panel + s[s.find("buy-button"):s.find("buy-button") + 400] if "buy-button" in s else panel)
        cover = re.search(r'<img class="cover-image"[^>]*src="([^"]+)"', s)
        ann = re.search(r'<div class="annotation">\s*<div class="rich-content[^"]*">(.*?)</div>', s, re.S)
        desc = html_to_text(ann.group(1)) if ann else None
        if not desc:
            og = re.search(r'<meta property="og:description" content="([^"]*)"', s)
            desc = _html.unescape(og.group(1)) if og else None
        toc = re.findall(r'<a href="/reader/\d+/(\d+)"[^>]*>(.*?)</a>', s, re.S)
        toc_block = re.search(r'<ul class="list-unstyled table-of-content">(.*?)</ul>', s, re.S)
        total_chapters = len(re.findall(r"<li", toc_block.group(1))) if toc_block else len(toc)
        return BookInfo(
            sid=wid, url=f"{BASE}/work/{wid}", title=title, authors=[_html.unescape(a) for a in authors],
            description=desc, cover=_html.unescape(cover.group(1)) if cover else None, lang="ru",
            status=c.get("status"), is_translation=False,
            words=int(c["chars"] / 7.2) if c.get("chars") else None, chapters=total_chapters or None,
            views=c.get("views"), likes=c.get("likes"), pop_raw=c.get("likes"), access=c.get("access"),
            updated_at=c.get("updated"), adult=c.get("adult", False),
            tags=(c.get("genres") or []) + tags,
            extra={"series": c.get("series"), "free_chapters": len(toc),
                   "toc": [[cid, _unescape(t)] for cid, t in toc[:8]]},
        )

    def chapters(self, book: dict) -> list[Chapter]:
        """Free chapters have a link; locked ones are plain text with a lock icon."""
        s = self._work_page(book["sid"])
        block = re.search(r'<ul class="list-unstyled table-of-content">(.*?)</ul>', s, re.S)
        out = []
        for i, item in enumerate(re.findall(r"<li[^>]*>(.*?)</li>", block.group(1), re.S) if block else []):
            link = re.search(r'<a href="/reader/\d+/(\d+)"[^>]*>(.*?)</a>', item, re.S)
            if link:
                out.append(Chapter(id=link.group(1), title=_unescape(link.group(2)), index=i))
            else:
                title = re.search(r"<span>(.*?)</span>", item, re.S)
                out.append(Chapter(id="", title=_unescape(title.group(1)) if title else f"#{i + 1}", index=i, free=False))
        return out

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        """Visible chapter text, or "" for a chapter that is paid / needs a login."""
        if self.browser is None:
            raise BrowserUnavailable("Author.Today text needs the browser helper")
        url = f"{BASE}/reader/{book['sid']}/{chapter.id}"
        self.http._pace()  # keep the same polite pace for browser page loads
        try:
            text = self.browser.text(url, "#text-container", min_chars=100, locked_pattern=LOCKED)
        except BrowserUnavailable:
            raise
        except Exception as e:  # mostly timeouts: worth another try later
            raise TemporaryError(f"{type(e).__name__}: {str(e).splitlines()[0][:150]}") from e
        return clean_text(text or "")

    def opening_text(self, book: dict, max_chapters: int = 3, enough_words: int = 6000) -> list[str]:
        toc = (book.get("extra") or {}).get("toc")
        chapters = [Chapter(id=cid, title=t, index=i) for i, (cid, t) in enumerate(toc)] if toc else self.chapters(book)
        out, words = [], 0
        for ch in chapters:
            try:
                text = self.chapter_text(book, ch)
            except TemporaryError:
                if not out:
                    raise  # nothing read yet: let the crawler retry this book later
                break
            if not text.strip():
                break  # the first locked chapter: the rest is paid too
            out.append(text)
            words += len(text.split())
            if len(out) >= max_chapters or words >= enough_words:
                break
        return out


def tag_url(tag: str) -> str:
    return f"{BASE}/work/tag/{urllib.parse.quote(tag)}"
