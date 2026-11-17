"""Archive of Our Own (archiveofourown.org): fan fiction and original works in many languages.

There are millions of works, so Bookkeeper reads the tags you choose (Settings): each tag's list of works, most
recently updated first. AO3's robots.txt asks programs to stay off its search and filter pages (/works?...,
/works/search) and its download links, so Bookkeeper only reads tag lists, work pages and chapters, slowly.
Each card in a tag list already has everything Bookkeeper keeps (fandoms, rating, warnings, relationships,
characters, tags, summary, language, words, chapters, kudos, hits), so there's no separate details step.
Works rated Explicit are 18+; AO3 asks before showing Mature and Explicit works, which `view_adult=true` answers."""
import html as _html
import re
from datetime import datetime
from urllib.parse import quote

import httpx

from ..analysis.text import clean_text, html_to_text
from ..http import NotFound
from .base import BookInfo, Chapter, Site, SiteError, TemporaryError

BASE = "https://archiveofourown.org"
DEFAULT_TAGS = "Original Work, First Person, LitRPG, Isekai, Reincarnation, Transmigration, Time Travel Fix-It"
# AO3's ratings, in Bookkeeper's terms (Not Rated is left out: it says nothing).
RATINGS = {"General Audiences": "G", "Teen And Up Audiences": "PG-13", "Mature": "R", "Explicit": "NC-17"}
LANGS = {"en": "en", "ru": "ru", "uk": "uk"}
NO_LABEL = {"No Archive Warnings Apply", "Creator Chose Not To Use Archive Warnings", "Not Rated"}
# Chapter text: a chapter's "userstuff" block, or a one-chapter work's "Work Text"; it ends at AO3's markers (the
# text itself may hold <div>s from work skins, so the first </div> isn't the end).
_TEXT_START = re.compile(r'<div class="userstuff module" role="article">|<h3 class="landmark heading" id="work">'
                         r'Work Text:</h3>')
_TEXT_END = re.compile(r'<!--/main-->|<!-- end of cache -->|<!--afterword-->|<div class="afterword|<div id="feedback"'
                       r'|<div class="chapter preface group"')
MAX_PAGES = 5000                            # AO3 lists show at most 5,000 pages (100,000 works) of a tag
_BLURB = re.compile(r'<li id="work_(\d+)" class="work blurb group[^"]*" role="article">(.*?)</li>\s*(?=<li id="work_'
                    r'|</ol>)', re.S)


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


def _int(s: str | None) -> int | None:
    digits = re.sub(r"\D", "", s or "")
    return int(digits) if digits else None


def _original(name: str) -> bool:
    """AO3's "Original Work", SquidgeWorld's "Original Works - Novel", "No Fandom"...: not fandoms."""
    n = name.strip().lower()
    return n.startswith(("original work", "no fandom")) or n.endswith("[original work]")


def _fandom(name: str) -> str:
    """Fandoms go into the library's Fandoms category; original works aren't a fandom."""
    return "Original" if _original(name) else f"fandom:{name}"


def _date(s: str) -> str | None:
    s = (s or "").strip()
    for fmt in ("%d %b %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _stat(block: str, name: str) -> str:
    m = re.search(r'<dd class="' + name + r'"[^>]*>(.*?)</dd>', block, re.S)
    return _text(m.group(1)) if m else ""


def _labels(rating: str | None, warnings: list[str], categories: list[str], fandoms: list[str],
            rest: list[str]) -> list[str]:
    adult = ["18+"] if rating == "Explicit" else []
    keep = [x for x in (*warnings, *categories) if x and x not in NO_LABEL]
    return list(dict.fromkeys([*adult, *keep, *map(_fandom, fandoms), *rest]))


def _info(wid: str, title: str, authors: list[str], summary: str | None, rating: str | None, warnings: list[str],
          categories: list[str], fandoms: list[str], relationships: list[str], characters: list[str],
          freeforms: list[str], lang_code: str, block_stats: str, complete: bool | None, updated: str | None,
          published: str | None = None, base: str = BASE) -> BookInfo:
    chapters = _stat(block_stats, "chapters")
    done, _, total = chapters.partition("/")
    kudos, hits = _int(_stat(block_stats, "kudos")), _int(_stat(block_stats, "hits"))
    return BookInfo(
        sid=wid, url=f"{base}/works/{wid}", title=title or wid, authors=authors,
        description=summary or None, lang=LANGS.get(lang_code, lang_code or None),
        status="completed" if complete else ("ongoing" if complete is False else None),
        is_translation=False, chapters=_int(done), words=_int(_stat(block_stats, "words")),
        views=hits, likes=kudos, pop_raw=kudos, adult=rating == "Explicit", age_rating=RATINGS.get(rating or ""),
        access="free", created_at=published, updated_at=updated,
        tags=_labels(rating, warnings, categories, fandoms, [*relationships, *characters, *freeforms]),
        extra={"rating": rating, "fandoms": [f for f in fandoms if not _original(f)],
               "planned_chapters": None if total.strip() in ("", "?") else _int(total),
               "bookmarks": _int(_stat(block_stats, "bookmarks")), "comments": _int(_stat(block_stats, "comments"))},
        complete=True,
    )


def parse_blurb(wid: str, block: str, base: str = BASE) -> BookInfo | None:
    """One work's card in a tag list (or a series, a user's works...)."""
    head = re.search(r'<h4 class="heading">(.*?)</h4>', block, re.S)
    if not head:
        return None
    title = re.search(r'<a href="/works/' + wid + r'">(.*?)</a>', head.group(1), re.S)
    authors = [_text(a) for a in re.findall(r'<a rel="author"[^>]*>(.*?)</a>', head.group(1), re.S)]
    if not authors and re.search(r"\bby\s+Anonymous\b", _text(head.group(1))):
        authors = ["Anonymous"]
    fandoms_block = re.search(r'<h5 class="fandoms heading">(.*?)</h5>', block, re.S)
    fandoms = [_text(t) for t in re.findall(r'<a class="tag"[^>]*>(.*?)</a>', fandoms_block.group(1), re.S)] \
        if fandoms_block else []

    def symbol(kind: str) -> str | None:
        m = re.search(r'<span class="[^"]*\b' + kind + r'"[^>]*title="([^"]*)"', block)
        return _html.unescape(m.group(1)) if m else None

    rating, iswip = symbol("rating"), re.search(r'class="complete-(yes|no) iswip"', block)
    categories = [c.strip() for c in (symbol("category") or "").split(",") if c.strip() and c.strip() != "No category"]

    def tags(kind: str) -> list[str]:
        return [_text(t) for t in re.findall(r"<li class='" + kind + r"'>(?:<strong>)?<a class=\"tag\"[^>]*>(.*?)</a>",
                                             block, re.S)]

    summary = re.search(r'<blockquote class="userstuff summary">(.*?)</blockquote>', block, re.S)
    lang = re.search(r'<dd class="language" lang="([^"]*)"', block)
    stats = re.search(r'<dl class="stats">(.*?)</dl>', block, re.S)
    updated = re.search(r'<p class="datetime">(.*?)</p>', block)
    return _info(wid, _text(title.group(1)) if title else wid, authors,
                 html_to_text(summary.group(1)) if summary else None, rating, tags("warnings"), categories, fandoms,
                 tags("relationships"), tags("characters"), tags("freeforms"), lang.group(1) if lang else "",
                 stats.group(1) if stats else "", (iswip.group(1) == "yes") if iswip else None,
                 _date(updated.group(1)) if updated else None, base=base)


def parse_listing(page: str, base: str = BASE) -> list[BookInfo]:
    return [b for b in (parse_blurb(wid, block, base) for wid, block in _BLURB.findall(page)) if b]


def last_page(page: str) -> int:
    nums = [int(n) for n in re.findall(r'<a href="[^"]*[?&]page=(\d+)[^"]*">\d+</a>', page)]
    return max(nums, default=1)


class Ao3(Site):
    id = "ao3"
    name = "Archive of Our Own"
    home = BASE
    lang = "en"
    min_interval = 5.0                        # AO3 asks programs to go slowly and answers 429 to fast ones
    note = ("Fan fiction and original works. Too big to collect whole: Bookkeeper reads the tags you choose "
            "(Settings), most recently updated first. Its robots.txt keeps programs off search pages and download "
            "links, so books are put together from the chapters.")
    lists_adult = True
    extra_settings = {
        "tags": {"label": "Tags to collect, comma-separated, as AO3 names them (a fandom such as Original Work or "
                          "Harry Potter - J. K. Rowling, or a tag such as First Person or LitRPG)",
                 "default": DEFAULT_TAGS},
        "pages": {"label": "Pages to read per tag (20 works each, most recently updated first)", "default": "200"},
        "languages": {"label": "Languages to keep (en, ru, uk)", "default": "en, ru, uk"},
    }

    # ----- tag lists
    def _tags(self) -> list[str]:
        raw = str(self.settings.get("tags") or DEFAULT_TAGS)
        return [t.strip() for t in raw.split(",") if t.strip()]

    def _keep(self) -> set[str]:
        return {x.strip() for x in str(self.settings.get("languages") or "en, ru, uk").split(",") if x.strip()}

    @classmethod
    def tag_url(cls, tag: str) -> str:
        # AO3 writes / & . ? # in tag URLs as *s* *a* *d* *q* *h*.
        for ch, code in (("/", "*s*"), ("&", "*a*"), (".", "*d*"), ("?", "*q*"), ("#", "*h*")):
            tag = tag.replace(ch, code)
        return f"{cls.home}/tags/{quote(tag, safe='*')}/works"

    def _listing(self, tag: str, page: int) -> tuple[list[BookInfo], int]:
        try:
            p = self.http.get(self.tag_url(tag), params={"page": page} if page > 1 else None)
        except NotFound:
            return [], 0
        keep = self._keep()
        books = parse_listing(p.text, self.home)
        return [b for b in books if b.lang in keep], (last_page(p.text) if books else 0)

    def discover(self, state: dict):
        tags = self._tags()
        pages = min(MAX_PAGES, _int(str(self.settings.get("pages") or "200")) or 200)
        if state.get("full_done"):
            for tag in tags:  # later passes: the most recently updated works
                for page in range(1, 4):
                    books, last = self._listing(tag, page)
                    if books:
                        yield books
                    if page >= last:
                        break
            return
        while state.get("ti", 0) < len(tags):
            tag, page = tags[state.get("ti", 0)], state.get("page", 1)
            books, last = self._listing(tag, page)
            if books:
                yield books
            if page >= min(last, pages):
                state.update(ti=state.get("ti", 0) + 1, page=1)
            else:
                state["page"] = page + 1
        state.update(full_done=True, ti=0, page=1)

    # ----- the work page (for a book added another way, or details asked for again)
    def _get(self, path: str, **kw) -> str:
        try:
            p = self.http.get(f"{self.home}{path}", params={"view_adult": "true", **kw.pop("params", {})}, **kw)
        except httpx.TransportError as e:
            raise TemporaryError(f"AO3 didn't answer ({type(e).__name__})") from e
        except httpx.HTTPStatusError as e:
            if str(e).startswith("HTTP 5"):  # AO3's servers are often overloaded (HTTP 502, 503, 525)
                raise TemporaryError(f"AO3 is overloaded ({str(e).split(' for ')[0]})") from e
            raise
        if "/users/login" in p.url or "This work is only available to registered users" in p.text[:60000]:
            raise SiteError("this work is shown only to logged-in AO3 users")
        return p.text

    def details(self, book: dict) -> BookInfo:
        s = self._get(f"/works/{book['sid']}")
        meta = re.search(r'<dl class="work meta group">(.*?)</dl>\s*</div>', s, re.S)
        title = re.search(r'<h2 class="title heading">(.*?)</h2>', s, re.S)
        if not meta or not title:
            raise SiteError("unexpected page layout (no work details)")
        m = meta.group(1)

        def tags(kind: str) -> list[str]:
            dd = re.search(r'<dd class="' + kind + r' tags">(.*?)</dd>', m, re.S)
            return [_text(t) for t in re.findall(r'<a class="tag"[^>]*>(.*?)</a>', dd.group(1), re.S)] if dd else []

        byline = re.search(r'<h3 class="byline heading">(.*?)</h3>', s, re.S)
        authors = [_text(a) for a in re.findall(r'<a rel="author"[^>]*>(.*?)</a>', byline.group(1), re.S)] if byline else []
        summary = re.search(r'<div class="summary module">.*?<blockquote class="userstuff">(.*?)</blockquote>', s, re.S)
        lang = re.search(r'<dd class="language" lang="([^"]*)"', m)
        stats = re.search(r'<dl class="stats">(.*?)</dl>', m, re.S)
        st = stats.group(1) if stats else ""
        status = re.search(r'<dt class="status">(\w+):</dt>', st)
        chapters = _stat(st, "chapters")
        rating = (tags("rating") or [None])[0]
        complete = None
        if status:
            complete = status.group(1) == "Completed"
        elif chapters:
            done, _, total = chapters.partition("/")
            complete = done.strip() == total.strip()
        updated = _date(_stat(st, "status")) or _date(_stat(st, "published"))
        info = _info(book["sid"], _text(title.group(1)), authors or ["Anonymous"],
                     html_to_text(summary.group(1)) if summary else None, rating, tags("warning"),
                     tags("category"), tags("fandom"), tags("relationship"), tags("character"), tags("freeform"),
                     lang.group(1) if lang else "", st, complete, updated, _date(_stat(st, "published")),
                     base=self.home)
        info.extra["toc"] = [[c.id, c.title] for c in self._index(s)[:8]]
        return info

    # ----- chapters
    @staticmethod
    def _index(work_page: str) -> list[Chapter]:
        """Chapters from the work page's chapter menu (a one-chapter work has none: its text is on the work page)."""
        menu = re.search(r'<select[^>]*id="selected_id"[^>]*>(.*?)</select>', work_page, re.S)
        if not menu:
            return [Chapter(id="", title="Text", index=0)] if 'id="chapters"' in work_page else []
        return [Chapter(id=cid, title=re.sub(r"^\d+\.\s*", "", _text(t)) or f"Chapter {i + 1}", index=i)
                for i, (cid, t) in enumerate(re.findall(r'<option[^>]*value="(\d+)"[^>]*>(.*?)</option>', menu.group(1), re.S))]

    def chapters(self, book: dict) -> list[Chapter]:
        try:
            nav = self.http.get(f"{self.home}/works/{book['sid']}/navigate").text
        except NotFound:
            return []
        out = [Chapter(id=cid, title=re.sub(r"^\d+\.\s*", "", _text(t)) or f"Chapter {i + 1}", index=i)
               for i, (cid, t) in enumerate(re.findall(
                   r'<li><a href="/works/' + re.escape(book["sid"]) + r'/chapters/(\d+)">(.*?)</a>', nav, re.S))]
        if not out and "/users/login" in nav[:5000]:
            raise SiteError("this work is shown only to logged-in AO3 users")
        return out

    @staticmethod
    def _chapter_bodies(page: str) -> list[str]:
        """The text of each chapter on a page (a chapter page has one, a whole-work page several)."""
        out = []
        for m in _TEXT_START.finditer(page):
            end = _TEXT_END.search(page, m.end())
            if not end and out:  # the cut-off end of a long page
                break
            body = page[m.end():end.start() if end else len(page)]
            out.append(html_to_text(re.sub(r'<h3 class="landmark heading" id="work">.*?</h3>', "", body, flags=re.S)))
        return [t for t in out if t.strip()]

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        try:
            page = self._get(f"/works/{book['sid']}" + (f"/chapters/{chapter.id}" if chapter.id else ""))
        except NotFound:
            return ""
        bodies = self._chapter_bodies(page)
        return bodies[0] if bodies else ""

    def opening_text(self, book: dict, max_chapters: int = 3, enough_words: int = 6000) -> list[str]:
        # The whole work on one page: one request instead of one per chapter. Only its start is read.
        page = self._get(f"/works/{book['sid']}", params={"view_full_work": "true"}, max_bytes=400_000)
        out, words = [], 0
        for text in self._chapter_bodies(page)[:max_chapters]:
            out.append(text)
            words += len(text.split())
            if words >= enough_words:
                break
        return out
