"""Sufficient Velocity (forums.sufficientvelocity.com): an English writing forum, stories posted as threads with
threadmarks (chapters) and tags in categories: setting (the fandom, or original), genre, content, character, format,
warning.

Catalog: the fiction forums you choose (Settings), most recently active first. Each thread in a forum list already
has its title, author, words in threadmarks, views, reactions, dates and tags; threads without threadmarks (talk,
indexes) are skipped. Details: the thread's reader page, for the story's description, how many threadmarks it has
and its watchers. Text: the reader shows ten threadmarks a page, and each reader page becomes a chapter.
robots.txt lets programs read threads (only search and "what's new" are off-limits)."""
import html as _html
import re
from datetime import datetime

from ..analysis.text import clean_text, html_to_text
from ..http import NotFound
from .base import BookInfo, Chapter, Site, SiteError, looks_adult

BASE = "https://forums.sufficientvelocity.com"
DEFAULT_FORUMS = "user-fiction.2, original-fiction.157, worm.94, weird-history.95"
CATEGORIES = {"setting", "genre", "content", "character", "format", "warning"}
_ITEM = '<div class="structItem structItem--thread'
_POST = re.compile(r'<article class="message message--post[^"]*"[^>]*>(.*?)</article>', re.S)


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


def _count(s: str | None) -> int | None:
    """"101k", "1.8m", "50K", "179" as numbers."""
    m = re.match(r"([\d.,]+)\s*([kKmM]?)", (s or "").strip())
    if not m:
        return None
    return int(float(m.group(1).replace(",", "")) * {"": 1, "k": 1e3, "m": 1e6}[m.group(2).lower()])


def _day(iso: str | None) -> str | None:
    try:
        return datetime.strptime((iso or "")[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _labels(block: str) -> tuple[list[str], list[str]]:
    """(labels, settings) from a thread's tags: settings become fandoms, the rest stay as they are."""
    labels, settings = [], []
    for cat, name in re.findall(r'<a[^>]*class="[^"]*tagItem[^"]*"[^>]*>\s*<i[^>]*title="([^"]+)"[^>]*></i>\s*(.*?)\s*</a>',
                                block, re.S):
        name = " ".join(_text(name).split())  # "worm<br>(web serial)" -> "worm (web serial)"
        if not name:
            continue
        if cat.lower() == "setting":
            settings.append(name)
            labels.append("Original" if name.lower().startswith("original") else f"fandom:{name}")
        else:
            labels.append(name)
    return list(dict.fromkeys(labels)), settings


def parse_forum(page: str) -> tuple[list[BookInfo], int]:
    out = []
    for block in page.split(_ITEM)[1:]:
        link = re.search(r'<div class="structItem-title">.*?<a href="/threads/([^"/]+)\.(\d+)/"[^>]*>(.*?)</a>', block, re.S)
        words = re.search(r'/threadmarks" data-xf-click="overlay">Words: ([^<]+)<', block)
        if not link or not words or "structItem-status--sticky" in block:
            continue
        labels, settings = _labels(block)
        if "meta" in labels:
            continue
        author = re.search(r'data-author="([^"]*)"', block)
        started = re.search(r'<li class="structItem-startDate">.*?datetime="([^"]+)"', block, re.S)
        latest = re.search(r'structItem-latestDate[^>]*datetime="([^"]+)"', block)
        views = re.search(r"<dt>Views</dt>\s*<dd>([^<]+)</dd>", block)
        replies = re.search(r"<dt>Replies</dt>\s*<dd>([^<]+)</dd>", block)
        score = re.search(r'title="Thread reaction score: ([\d,]+)"', block)
        slug, tid = link.group(1), link.group(2)
        reactions = _count(score.group(1)) if score else None
        out.append(BookInfo(
            sid=tid, url=f"{BASE}/threads/{slug}.{tid}/", title=_text(link.group(3)),
            authors=[_html.unescape(author.group(1))] if author and author.group(1) else [], lang="en",
            words=_count(words.group(1)), views=_count(views.group(1)) if views else None, likes=reactions,
            pop_raw=reactions, adult=looks_adult(labels), access="free", is_translation=False,
            status="completed" if "complete" in labels else None,
            created_at=_day(started.group(1)) if started else None, updated_at=_day(latest.group(1)) if latest else None,
            tags=labels or None, partial_tags=True, extra={"slug": slug, "settings": settings,
                                        "replies": _count(replies.group(1)) if replies else None},
        ))
    pages = [int(n) for n in re.findall(r'href="/forums/[^"/]+/page-(\d+)"', page)]
    return out, max(pages, default=1)


def parse_reader(page: str) -> dict:
    """A reader page: the story's description, its stats, its threadmarked posts and how many reader pages."""
    about = re.search(r'<article class="threadmarkListingHeader-extraInfoChild[^"]*">.*?<div class="bbWrapper">(.*?)</div>\s*'
                      r'</article>', page, re.S)
    stat = lambda name: _count((re.search(r"<dt>" + name + r"</dt>\s*<dd>\s*([^<]+?)\s*</dd>", page) or [None, ""])[1])
    posts = []
    for body in _POST.findall(page):
        label = re.search(r'<span[^>]*class="threadmarkLabel[^"]*"[^>]*>(.*?)</span>', body, re.S)
        text = re.search(r'<div class="bbWrapper">(.*)</div>', body, re.S)
        posts.append((_text(label.group(1)) if label else "", html_to_text(text.group(1)).strip() if text else ""))
    pages = [int(n) for n in re.findall(r'href="/threads/[^"]+/reader/page-(\d+)"', page)]
    return {"description": html_to_text(about.group(1)).strip() if about else None, "threadmarks": stat("Threadmarks"),
            "watchers": stat("Watchers"), "readers": stat("Recent readers"), "posts": posts,
            "pages": max(pages, default=1)}


class SufficientVelocity(Site):
    id = "sufficientvelocity"
    name = "Sufficient Velocity"
    home = BASE
    lang = "en"
    min_interval = 2.5
    note = ("An English writing forum: stories with threadmarks and tags (setting, genre, content, character). "
            "Bookkeeper reads the fiction forums you choose (Settings), most recently active first.")
    extra_settings = {
        "forums": {"label": "Forums to read, comma-separated, as they appear in the forum's address (user-fiction.2, "
                            "original-fiction.157, worm.94, weird-history.95, quests.29...)", "default": DEFAULT_FORUMS},
        "pages": {"label": "Pages to read per forum (about 20 threads each, most recently active first)",
                  "default": "600"},
    }

    def _forums(self) -> list[str]:
        raw = str(self.settings.get("forums") or DEFAULT_FORUMS)
        return [f.strip().strip("/") for f in raw.split(",") if re.fullmatch(r"[a-z0-9-]+\.\d+", f.strip().strip("/"))]

    def _list(self, forum: str, page: int) -> tuple[list[BookInfo], int]:
        try:
            s = self.http.get(f"{BASE}/forums/{forum}/" + (f"page-{page}" if page > 1 else "")).text
        except NotFound:
            return [], 0
        return parse_forum(s)

    def discover(self, state: dict):
        forums = self._forums()
        limit = _count(str(self.settings.get("pages") or "600")) or 600
        if state.get("full_done"):
            for forum in forums:  # later passes: the most recently active threads
                for page in range(1, 4):
                    books, last = self._list(forum, page)
                    if books:
                        yield books
                    if page >= last:
                        break
            return
        while state.get("fi", 0) < len(forums):
            forum, page = forums[state.get("fi", 0)], state.get("page", 1)
            books, last = self._list(forum, page)
            if books:
                yield books
            if page >= min(last, limit):
                state.update(fi=state.get("fi", 0) + 1, page=1)
            else:
                state["page"] = page + 1
        state.update(full_done=True, fi=0, page=1)

    def _thread(self, book: dict) -> str:
        slug = (book.get("extra") or {}).get("slug")
        if slug:
            return f"{BASE}/threads/{slug}.{book['sid']}/"
        if book.get("url"):
            return book["url"].split("#")[0].rstrip("/") + "/"
        return f"{BASE}/threads/{book['sid']}/"

    def _reader(self, book: dict, page: int) -> dict:
        r = parse_reader(self.http.get(self._thread(book) + "reader/" + (f"page-{page}" if page > 1 else "")).text)
        if not r["posts"] and page == 1:
            raise NotFound("no threadmarks")
        return r

    def details(self, book: dict) -> BookInfo:
        url = self._thread(book)
        s = self.http.get(url + "reader/").text
        r = parse_reader(s)
        title = re.search(r'<h1 class="p-title-value">(.*?)</h1>', s, re.S)
        if not title:
            raise SiteError("unexpected page layout (no thread title)")
        labels, settings = _labels(s[:s.find('<article class="message message--post')] if r["posts"] else s)
        return BookInfo(
            sid=book["sid"], url=url, title=_text(re.sub(r'<span class="label[^"]*"[^>]*>.*?</span>', "",
                                                         title.group(1), flags=re.S)),
            description=r["description"], lang="en", chapters=r["threadmarks"], is_translation=False,
            adult=looks_adult(labels), tags=labels or None,
            extra={"watchers": r["watchers"], "recent_readers": r["readers"], "settings": settings},
        )

    # ----- text: reader pages of ten threadmarks
    def chapters(self, book: dict) -> list[Chapter]:
        r = self._reader(book, 1)
        return [Chapter(id=str(p), title=f"Threadmarks {10 * (p - 1) + 1}–{10 * p}", index=p - 1)
                for p in range(1, r["pages"] + 1)]

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        try:
            posts = self._reader(book, int(chapter.id))["posts"]
        except NotFound:
            return ""
        return "\n\n".join((f"{label}\n{text}" if label else text) for label, text in posts if text)

    def opening_text(self, book: dict, max_chapters: int = 3, enough_words: int = 6000) -> list[str]:
        # The first reader page holds the first ten threadmarks: plenty for the narration check.
        out, words = [], 0
        for _, text in self._reader(book, 1)["posts"]:
            if not text.strip():
                continue
            out.append(text)
            words += len(text.split())
            if len(out) >= max_chapters or words >= enough_words:
                break
        return out
