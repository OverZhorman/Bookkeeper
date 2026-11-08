"""Ficbook (ficbook.net): Russian fanfiction and original works (ориджиналы).

There are millions of works, so Bookkeeper reads the catalogs you choose (Settings): by default original works,
most recently updated first. Each listing card has nearly everything (direction, rating, status, likes, fandom,
size, tags); the work's page adds the description and the list of parts. Works rated NC-17 / NC-21 are 18+.
ExLoader (a Waterfox extension) can download Ficbook works too."""
import html as _html
import re

from ..analysis.text import clean_text, html_to_text
from ..http import NotFound
from .base import BookInfo, Chapter, Site, SiteError

BASE = "https://ficbook.net"
DEFAULT_CATALOGS = "no_fandom/originals"
STATUS = {"in-progress": "ongoing", "finished": "completed", "frozen": "frozen"}
RATING_LABELS = {"NC-17": ["18+"], "NC-21": ["18+"], "R": ["Зрелая тематика"]}
# Spam that gets posted as "original works" (account and money selling), skipped when it has no likes.
SPAM = re.compile(r"(?i)\b(buy|verified|accounts?|telegram|whatsapp|casino|betting|paypal|cash ?app|crypto|"
                  r"vcc|usdt|bitcoin|seo|escort)\b|@\w*(store|shop)\b|\+\d{1,3}\s?\(\d{3}\)|seller|^Без названия\b")
_TAG = re.compile(r'class="tag(?:\s[^"]*)?"[^>]*>(.*?)</a>', re.S)


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


def _dd(block: str, name: str) -> str:
    m = re.search(r"<dt>\s*" + re.escape(name) + r":?\s*</dt>\s*<dd>(.*?)</dd>", block, re.S)
    return m.group(1) if m else ""


def _badges(block: str) -> dict:
    direction = re.search(r'class="[^"]*direction-[a-z]+[^"]*"[^>]*>\s*<span[^>]*>(.*?)</span>', block, re.S)
    rating = re.search(r"ds-label-rating-([A-Za-z0-9-]+)", block)
    status = re.search(r"ds-label-status-([a-z-]+)", block)
    likes = re.search(r'class="js-like-count"[^>]*>\s*([\d\s ]+)<', block)
    return {"direction": _text(direction.group(1)) if direction else None,
            "rating": rating.group(1).upper() if rating else None,
            "status": STATUS.get(status.group(1)) if status else None,
            "likes": int(re.sub(r"\D", "", likes.group(1))) if likes and re.sub(r"\D", "", likes.group(1)) else None}


def _fandom(name: str) -> str:
    """Fandoms go into the library's Fandoms category; «Ориджиналы» (original works) isn't a fandom."""
    return name if name.strip().lower().startswith("ориджинал") else f"fandom:{name}"


def _size(text: str) -> tuple[int | None, int | None]:
    words = re.search(r"([\d\s ]+)\s*слов", text)
    parts = re.search(r"(\d+)\s*част", text)
    w = int(re.sub(r"\D", "", words.group(1))) if words and re.sub(r"\D", "", words.group(1)) else None
    return w, (int(parts.group(1)) if parts else (1 if w else None))


class Ficbook(Site):
    id = "ficbook"
    name = "Ficbook"
    home = BASE
    lang = "ru"
    min_interval = 2.0
    note = ("Fanfiction and original works. Too big to collect whole: Bookkeeper reads the catalogs you choose "
            "(Settings), most recently updated first.")
    lists_adult = True
    extension_downloads = ("ExLoader",)
    login_url = f"{BASE}/login"
    login_benefit = ("Works rated NC-21, and the lists the site shows only to logged-in readers. Ficbook's login page "
                     "keeps showing Cloudflare checks to Bookkeeper's window: log in in your own Waterfox, then press "
                     "“Use my Waterfox login”.")
    login_form = {"user": "#login-login, input[name=login]", "password": "input[type=password]"}
    logged_in_js = r"/isLoggedIn:\s*true/.test(document.documentElement.innerHTML)"
    extra_settings = {
        "catalogs": {"label": "Catalogs to collect, comma-separated (the part after ficbook.net/fanfiction/, e.g. "
                              "no_fandom/originals, anime_and_manga/naruto, books/rouling_dzhoan___garri_potter)",
                     "default": DEFAULT_CATALOGS},
        "pages": {"label": "Pages to read per catalog (20 works each, most recently updated first)", "default": "300"},
    }

    def check_login(self) -> bool | None:
        page = self.http.get(f"{BASE}/").text
        m = re.search(r"isLoggedIn:\s*(true|false)", page)
        return (m.group(1) == "true") if m else None

    # ----- catalog
    def _card(self, block: str) -> BookInfo | None:
        link = re.search(r'<h3 class="fanfic-inline-title">\s*<a[^>]*href="/readfic/([^"#?/]+)"[^>]*>(.*?)</a>', block, re.S)
        if not link or "from_promo" in block[:3000]:
            return None
        fid = link.group(1)
        b = _badges(block)
        authors = [_text(a) for a in re.findall(r'<a href="/authors/[^"]+"[^>]*>(.*?)</a>', _dd(block, "Автор"), re.S)]
        fandoms = [_text(a) for a in re.findall(r"<a[^>]*>(.*?)</a>", _dd(block, "Фэндом"), re.S)]
        words, parts = _size(_text(_dd(block, "Размер")))
        updated = re.search(r"(\d\d)\.(\d\d)\.(\d{4})", _text(_dd(block, "Дата обновления")))
        tags = [_text(t) for t in _TAG.findall(block)]
        cover = re.search(r'<img src="([^"]+)"[^>]*alt=', block)
        desc = re.search(r'class="[^"]*fanfic-description[^"]*"[^>]*>(.*?)</div>', block, re.S)
        labels = [x for x in [b["direction"], *RATING_LABELS.get(b["rating"] or "", []), *map(_fandom, fandoms), *tags] if x]
        title = _text(link.group(2)) or fid
        if not b["likes"] and SPAM.search(f"{title} {_text(desc.group(1)) if desc else ''} {' '.join(authors)}"):
            return None
        return BookInfo(
            sid=fid, url=f"{BASE}/readfic/{fid}", title=title, authors=authors,
            description=html_to_text(desc.group(1)) or None if desc else None,
            cover=_html.unescape(cover.group(1)) if cover else None, lang="ru", status=b["status"],
            is_translation=False, chapters=parts, words=words, likes=b["likes"], pop_raw=b["likes"],
            adult=b["rating"] in ("NC-17", "NC-21"), age_rating=b["rating"], access="free",
            updated_at=f"{updated.group(3)}-{updated.group(2)}-{updated.group(1)}" if updated else None,
            tags=labels, partial_tags=True, extra={"rating": b["rating"], "fandoms": fandoms},
        )

    def _catalogs(self) -> list[str]:
        raw = str(self.settings.get("catalogs") or DEFAULT_CATALOGS)
        return [c.strip().strip("/").removeprefix("fanfiction/") for c in raw.split(",") if c.strip()]

    def _listing(self, catalog: str, page: int) -> list[BookInfo]:
        try:
            p = self.http.get(f"{BASE}/fanfiction/{catalog}", params={"p": page})
        except NotFound:
            return []
        if "/login" in p.url:
            return []
        blocks = re.split(r'<article class="\s*fanfic-inline', p.text)[1:]
        return [b for b in (self._card(x) for x in blocks) if b]

    def discover(self, state: dict):
        catalogs = self._catalogs()
        pages = int(re.sub(r"\D", "", str(self.settings.get("pages") or "300")) or 300)
        if state.get("full_done"):
            for catalog in catalogs:  # later passes: the most recently updated works
                for page in range(1, 4):
                    books = self._listing(catalog, page)
                    if not books:
                        break
                    yield books
            return
        while state.get("ci", 0) < len(catalogs):
            catalog, page = catalogs[state.get("ci", 0)], state.get("page", 1)
            books = self._listing(catalog, page)
            if books:
                yield books
            if not books or page >= pages:
                state.update(ci=state.get("ci", 0) + 1, page=1)
            else:
                state["page"] = page + 1
        state.update(full_done=True, ci=0, page=1)

    # ----- the work page
    def _page(self, fid: str, part: str | None = None) -> str:
        p = self.http.get(f"{BASE}/readfic/{fid}" + (f"/{part}" if part else ""))
        if "/login" in p.url:
            raise SiteError("this work is shown only to logged-in readers (log in on the Sites page)")
        return p.text

    def details(self, book: dict) -> BookInfo:
        s = self._page(book["sid"])
        h1 = re.search(r'<h1[^>]*itemprop="name"[^>]*>(.*?)</h1>', s, re.S) or re.search(r"<h1[^>]*>(.*?)</h1>", s, re.S)
        if not h1:
            raise SiteError("unexpected page layout (no title)")
        head = s[:s.find('class="list-of-fanfic-parts') if 'class="list-of-fanfic-parts' in s else 60000]
        b = _badges(head)
        authors = list(dict.fromkeys(_text(a) for a in re.findall(
            r'<a href="/authors/[^"]+"[^>]*class="[^"]*creator-username[^"]*"[^>]*>(.*?)</a>', head, re.S)))
        if not authors:
            authors = list(dict.fromkeys(_text(a) for a in re.findall(r'<a href="/authors/[^"]+"[^>]*>(.*?)</a>', head, re.S)))[:3]
        fandoms = [_text(a) for a in re.findall(r'<a href="/fanfiction/[^"]+"[^>]*>(.*?)</a>', _dd(head, "Фэндом") or head[:20000], re.S)][:5]
        tags = [_text(t) for t in _TAG.findall(head)]
        authors = [a for a in authors if a]
        size_text = _text(_dd(head, "Размер"))
        if not size_text:
            m = re.search(r"Размер:(.{0,300})", _text(head))
            size_text = m.group(1) if m else ""
        words, parts = _size(size_text)
        desc = re.search(r'itemprop="description">(.*?)</div>', head, re.S)
        labels = [x for x in [b["direction"], *RATING_LABELS.get(b["rating"] or "", []), *map(_fandom, fandoms), *tags] if x]
        chapters = self._parts(s, book["sid"])
        return BookInfo(
            sid=book["sid"], url=f"{BASE}/readfic/{book['sid']}", title=_text(h1.group(1)), authors=authors,
            description=html_to_text(desc.group(1)) or None if desc else None, lang="ru", status=b["status"],
            is_translation=bool(re.search(r"<dt>\s*Оригинал", head)),  # translations name their original
            chapters=len(chapters) or parts, words=words, likes=b["likes"], pop_raw=b["likes"],
            adult=b["rating"] in ("NC-17", "NC-21"), age_rating=b["rating"], access="free", tags=list(dict.fromkeys(labels)),
            extra={"rating": b["rating"], "fandoms": fandoms, "toc": [[c.id, c.title] for c in chapters[:8]]},
        )

    @staticmethod
    def _parts(page: str, fid: str) -> list[Chapter]:
        block = re.search(r'class="list-of-fanfic-parts(.*?)</ul>', page, re.S)
        if not block:  # a single-part work: the text is on the work's own page
            return [Chapter(id="", title="Текст", index=0)] if 'id="content"' in page else []
        out = []
        for part, title in re.findall(r'<a href="/readfic/' + re.escape(fid) + r'/(\d+)[^"]*"[^>]*>.*?<h3>(.*?)</h3>',
                                       block.group(1), re.S):
            if all(c.id != part for c in out):
                out.append(Chapter(id=part, title=_text(title) or f"Часть {len(out) + 1}", index=len(out)))
        return out

    def chapters(self, book: dict) -> list[Chapter]:
        return self._parts(self._page(book["sid"]), book["sid"])

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        try:
            s = self._page(book["sid"], chapter.id or None)
        except NotFound:
            return ""
        m = re.search(r'<div id="content"[^>]*>(.*?)</div>', s, re.S)
        return html_to_text(m.group(1).replace("\n", "<br>")) if m else ""

    def opening_text(self, book: dict, max_chapters: int = 3, enough_words: int = 6000) -> list[str]:
        toc = (book.get("extra") or {}).get("toc")
        chapters = [Chapter(id=str(c), title=t, index=i) for i, (c, t) in enumerate(toc)] if toc else self.chapters(book)
        out, words = [], 0
        for ch in chapters[:max_chapters + 2]:
            text = self.chapter_text(book, ch)
            if not text.strip():
                continue
            out.append(text)
            words += len(text.split())
            if len(out) >= max_chapters or words >= enough_words:
                break
        return out
