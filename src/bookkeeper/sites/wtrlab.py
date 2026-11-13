"""WTR-LAB (wtr-lab.com): machine translations of Chinese, Korean and Japanese web novels into English (about
100,000 novels), with genres and NovelUpdates-style tags.

Catalog only. The site's robots.txt asks programs not to read its chapter pages, its novel lists or its API, so
Bookkeeper reads the list of novels from the site's sitemaps (2,000 novels each) and then each novel's page, whose
embedded data (Next.js) has the title, author, original title, genres, tags, rating and chapter count. There's no
narration check or download for this site."""
import base64
import binascii
import html as _html
import json
import re

from ..http import NotFound
from .base import BookInfo, Chapter, Site, SiteError, looks_adult

BASE = "https://wtr-lab.com"
_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
_SITEMAP = re.compile(r"<loc>https://wtr-lab\.com/novels/sitemap/(\d+)\.xml</loc>")
_NOVEL = re.compile(r"<loc>(https://wtr-lab\.com/en/novel/(\d+)/([^<]+))</loc>")
_GENRE = re.compile(r'href="/en/novel-list\?genre=\d+"><span[^>]*>([^<]+)</span>')
STATUS = {"ongoing": "ongoing", "completed": "completed", "hiatus": "frozen", "dropped": "frozen"}
MTL = "Machine translation"


def _origin(raw_title: str) -> str | None:
    """The original language, from the script of the original title."""
    if re.search(r"[가-힣]", raw_title):
        return "kr"
    if re.search(r"[぀-ヿ]", raw_title):
        return "jp"
    if re.search(r"[一-鿿]", raw_title):
        return "cn"
    return None


def _raw_title(data: dict) -> str:
    try:
        title = base64.b64decode(data.get("raw_title_b64") or "").decode("utf-8")
    except (binascii.Error, ValueError):
        title = ""
    return (title or (data.get("raw") or {}).get("title") or "").strip()


class WtrLab(Site):
    id = "wtrlab"
    name = "WTR-LAB"
    home = BASE
    lang = "en"
    min_interval = 2.5
    note = ("Machine translations of Asian web novels (about 100,000), with NovelUpdates-style tags. Catalog only: "
            "the site asks programs not to read its chapters, so there's no narration check or download there.")
    has_text = False

    # ----- catalog
    def _sitemaps(self) -> list[int]:
        return sorted({int(n) for n in _SITEMAP.findall(self.http.get(f"{BASE}/novels/index.xml").text)})

    def _novels(self, n: int) -> list[BookInfo]:
        try:
            s = self.http.get(f"{BASE}/novels/sitemap/{n}.xml").text
        except NotFound:
            return []
        return [BookInfo(sid=sid, url=_html.unescape(url), title=_html.unescape(slug).replace("-", " ").strip().title() or f"#{sid}",
                         lang="en", is_translation=True, access="free", extra={"slug": slug})
                for url, sid, slug in _NOVEL.findall(s)]

    def discover(self, state: dict):
        maps = self._sitemaps()
        # Later passes: new novels are added at the end, so the last two sitemaps.
        todo = maps[-2:] if state.get("full_done") else [m for m in maps if m >= state.get("next", 0)]
        for m in todo:
            books = self._novels(m)
            if books:
                yield books
            if not state.get("full_done"):
                state["next"] = m + 1
        state.update(full_done=True, next=0)

    def details(self, book: dict) -> BookInfo:
        extra = book.get("extra") or {}
        url = book.get("url") or f"{BASE}/en/novel/{book['sid']}/{extra.get('slug') or ''}"
        s = self.http.get(url).text
        m = _DATA.search(s)
        if not m:
            raise SiteError("page has no embedded data (layout changed?)")
        props = json.loads(m.group(1)).get("props", {}).get("pageProps", {})
        serie = props.get("serie") or {}
        sd = serie.get("serie_data") or {}
        if not sd:
            raise NotFound(url)
        data = sd.get("data") or {}
        raw_title = _raw_title(data)
        title = (data.get("title") or "").strip() or book.get("title") or f"#{book['sid']}"
        names = [x.get("title") for x in serie.get("names") or [] if isinstance(x, dict)]
        # (the site also tags a novel with its own title, under "Adaptations": that one says nothing)
        tags = [t["title"] for t in props.get("tags") or [] if isinstance(t, dict) and t.get("title")
                and t["title"].strip().lower() != title.lower()]
        genres = [_html.unescape(g).strip() for g in _GENRE.findall(s)]
        status = re.search(r">(Ongoing|Completed|Hiatus|Dropped)<", s)
        rating = sd.get("rating")
        author = (data.get("author") or "").strip() or (data.get("raw") or {}).get("author") or sd.get("author")
        return BookInfo(
            sid=book["sid"], url=url, title=title,
            alt_titles=[t for t in dict.fromkeys([*names, raw_title]) if t and t != title],
            authors=[author] if author else [], description=(data.get("description") or "").strip() or None,
            cover=data.get("image"), lang="en", status=STATUS.get(status.group(1).lower()) if status else None,
            is_translation=True, origin=_origin(raw_title), chapters=sd.get("chapter_count"),
            rating=round(float(rating) * 2, 2) if rating else None, votes=sd.get("total_rate"),
            views=sd.get("view"), likes=sd.get("in_library"), pop_raw=sd.get("view"), access="free",
            adult=looks_adult([*genres, *tags]), created_at=(sd.get("created_at") or "")[:10] or None,
            tags=list(dict.fromkeys([*genres, *tags, MTL])),
            extra={"slug": sd.get("slug") or extra.get("slug"), "raw_title": raw_title,
                   "raw_author": (data.get("raw") or {}).get("author"), "rank": (serie.get("ranks") or {}).get("all")},
        )

    # ----- no text: the site's robots.txt rules out chapter pages
    def chapters(self, book: dict) -> list[Chapter]:
        return []

    def opening_text(self, book: dict, max_chapters: int = 3, enough_words: int = 6000) -> list[str]:
        return []
