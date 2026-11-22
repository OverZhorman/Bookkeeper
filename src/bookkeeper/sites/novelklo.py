"""NovelKlo (novelklo.com): a young Ukrainian platform for original fiction and fan fiction, about 1,300 books, with
genres, tags and fandoms.

Catalog: the sitemap lists every book; Bookkeeper reads each book page (its data block: title, author, genres,
annotation, length, dates; and the tag and fandom links on the page), ten at a time. 18+ books hide their tags until
a reader confirms their age, so those come with genres only. Catalog only for now."""
import html as _html
import json
import re

from ..analysis.text import clean_text
from ..http import NotFound
from .base import BookInfo, Site, SiteError, looks_adult

BASE = "https://novelklo.com"
PER_BATCH = 10
_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


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
    # Tag and fandom links of the book itself: after its title (the site menu before it lists fandoms too), and
    # before the comments and the footer (which the page may send before the title).
    h1 = s.find("<h1")
    stops = [i for i in (s.find("<footer", h1), s.find('id="comments"', h1)) if h1 >= 0 and i > h1]
    main = s[h1:min(stops)] if stops else (s[h1:] if h1 >= 0 else "")
    tags = [_text(t) for t in re.findall(r'<a[^>]*href="/tag/[^"]+"[^>]*>(.*?)</a>', main, re.S)]
    fandoms = [_text(f) for f in re.findall(r'<a[^>]*href="/fandom/[^"]+"[^>]*>(.*?)</a>', main, re.S)]
    genres = [g for g in data.get("genre") or [] if g]
    words = ((data.get("additionalProperty") or {}) if isinstance(data.get("additionalProperty"), dict) else {})
    chapters = re.search(r"<p[^>]*>(\d+)<!-- --> <!-- -->розділ", s)
    gated = "Ця книга має вікове обмеження" in s or "контент для дорослих (18+)" in s
    labels = list(dict.fromkeys(genres + [t for t in tags if t] + [f"fandom:{f}" for f in fandoms if f]))
    authors = data.get("author") or []
    authors = authors if isinstance(authors, list) else [authors]
    return BookInfo(
        sid=sid, url=f"{BASE}/book/{sid}", title=_text(data.get("name") or ""),
        authors=[_text(a["name"]) for a in authors if isinstance(a, dict) and a.get("name")],
        description=(data.get("description") or "").strip() or None, cover=data.get("image") or None, lang="uk",
        is_translation=False, chapters=int(chapters.group(1)) if chapters else None,
        words=int(words["value"]) if words.get("name") == "wordCount" and words.get("value") else None,
        adult=gated or looks_adult(labels), age_rating="18+" if gated else None,
        created_at=(data.get("datePublished") or "")[:10] or None,
        updated_at=(data.get("dateModified") or "")[:10] or None, tags=labels or None, access="free",
        extra={"fandoms": fandoms}, complete=True,
    )


class NovelKlo(Site):
    id = "novelklo"
    name = "NovelKlo"
    home = BASE
    lang = "uk"
    min_interval = 2.5
    has_text = False
    note = ("A young Ukrainian platform for original fiction and fan fiction, about 1,300 books, with genres, tags and "
            "fandoms. Catalog only for now.")

    def _ids(self) -> list[str]:
        s = self.http.get(f"{BASE}/sitemap.xml").text
        return list(dict.fromkeys(re.findall(r"<loc>https://novelklo\.com/book/(\d+)</loc>", s)))

    def _book(self, sid: str) -> BookInfo | None:
        try:
            return parse_book(sid, self.http.get(f"{BASE}/book/{sid}").text)
        except NotFound:
            return None

    def discover(self, state: dict):
        ids = self._ids()
        if state.get("full_done"):  # later passes: books newer than any seen so far
            ids = [i for i in ids if int(i) > state.get("max_id", 0)]
            state["offset"] = 0
        while state.get("offset", 0) < len(ids):
            chunk = ids[state.get("offset", 0):state.get("offset", 0) + PER_BATCH]
            books = [b for b in map(self._book, chunk) if b]
            state["offset"] = state.get("offset", 0) + len(chunk)
            state["max_id"] = max([state.get("max_id", 0)] + [int(i) for i in chunk])
            if books:
                yield books
        state.update(full_done=True, offset=0)

    def details(self, book: dict) -> BookInfo:
        info = self._book(book["sid"])
        if not info:
            raise NotFound(book["sid"])
        return info
