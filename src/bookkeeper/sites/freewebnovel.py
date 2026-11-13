"""FreeWebNovel (freewebnovel.com): English web novels, translations of Chinese, Korean and Japanese ones and
originals (about 16,000).

Catalog: every listing shows at most 50 pages of 20 novels, so Bookkeeper walks many of them (newest, latest
updates, most popular, completed, by original language, then every genre, finished and not) to reach as much of the
catalog as it can. Details: the novel page (author, genres, status, original language, summary, rating).
Text: chapter pages (/novel/<name>/chapter-N)."""
import html as _html
import re

from ..analysis.text import clean_text, html_to_text
from ..http import NotFound
from .base import BookInfo, Chapter, Site, looks_adult

BASE = "https://freewebnovel.com"
ORIGIN = {"chinese": "cn", "korean": "kr", "japanese": "jp", "english": "en"}
STATUS = {"ongoing": "ongoing", "completed": "completed", "hiatus": "frozen"}
LISTINGS = [
    "sort/latest-novel", "sort/latest-release", "sort/most-popular", "sort/completed-novel",
    "sort/most-popular/completed", "sort/most-popular/collected", "sort/most-popular/collected/completed",
    "sort/most-popular/recommended", "sort/most-popular/recommended/completed", "sort/most-popular/monthvisit",
    "sort/latest-release/completed",
    *[f"sort/latest-release/{lang}-novel{done}" for lang in ("chinese", "korean", "japanese", "english")
      for done in ("", "/completed")],
]
GENRES = ["Action", "Adult", "Adventure", "Comedy", "Drama", "Eastern", "Ecchi", "Fan-fic", "Fantasy", "Game",
          "Gender+Bender", "Harem", "Historical", "Horror", "Josei", "Martial+Arts", "Mature", "Mecha", "Mystery",
          "Psychological", "Reincarnation", "Romance", "School+Life", "Sci-fi", "Seinen", "Shoujo", "Shounen",
          "Shounen+Ai", "Slice+of+Life", "Smut", "Sports", "Supernatural", "System", "Tragedy", "Wuxia", "Xianxia",
          "Xuanhuan", "Yaoi"]
MAX_PAGES = 50  # the site never shows more
# Lines the site adds to chapters: "This chapter is updated by f r e e w e b n o v e l . c o m" and the like.
_NOTICE = re.compile(r"(?i)f\W{0,3}r\W{0,3}e\W{0,3}e\W{0,3}w\W{0,3}e\W{0,3}b\W{0,3}n\W{0,3}o\W{0,3}v\W{0,3}e\W{0,3}l")


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


def _meta(s: str, name: str) -> str:
    m = re.search(r'<meta property="og:novel:' + re.escape(name) + r'" content="([^"]*)"', s)
    return _html.unescape(m.group(1)).strip() if m else ""


class FreeWebNovel(Site):
    id = "freewebnovel"
    name = "FreeWebNovel"
    home = BASE
    lang = "en"
    min_interval = 2.5
    note = ("English web novels, translated (Chinese, Korean, Japanese) and original, about 16,000. Its lists show "
            "only 1,000 novels each, so Bookkeeper reads many of them, every genre included.")

    # ----- catalog
    def _card(self, row: str) -> BookInfo | None:
        link = re.search(r'<h3 class="tit"><a href="/novel/([^"/]+)" title="([^"]*)"', row)
        if not link:
            return None
        slug = link.group(1)
        rating = re.search(r'<div class="core">\s*<span>([\d.]+)</span>', row)
        origin = re.search(r'title="(\w+) Novel">', row)
        genres = [_text(g) for g in re.findall(r'href="/genre/[^"]+" class="novel" title="[^"]*">(.*?)</a>', row)]
        count = re.search(r'<span class="s1">(\d+) Chapters?</span>', row)
        last = re.search(r'href="/novel/' + re.escape(slug) + r'/chapter-(\d+)"', row)
        cover = re.search(r'<img src="(/files/article/image/[^"]+)"', row)
        lang = ORIGIN.get(origin.group(1).lower()) if origin else None
        return BookInfo(
            sid=slug, url=f"{BASE}/novel/{slug}", title=_text(link.group(2)) or slug, lang="en",
            origin=lang, is_translation=None if not lang else lang != "en",
            rating=round(float(rating.group(1)) * 2, 2) if rating and float(rating.group(1)) else None,
            chapters=int(count.group(1)) if count else None, cover=BASE + cover.group(1) if cover else None,
            access="free", adult=looks_adult(genres), tags=list(dict.fromkeys(g for g in genres if g)),
            partial_tags=True, extra={"last": int(last.group(1)) if last else None},
        )

    def _listing(self, path: str, page: int) -> tuple[list[BookInfo], int]:
        """One page of a listing: its novels, and the number of its last page."""
        try:
            s = self.http.get(f"{BASE}/{path}" + (f"/{page}" if page > 1 else "")).text
        except NotFound:
            return [], 0
        pages = [int(x) for x in re.findall(r'href="(?:https://freewebnovel\.com)?/' + re.escape(path) + r'/(\d+)"', s)]
        return [b for b in (self._card(r) for r in s.split('<div class="li-row">')[1:]) if b], max(pages + [page])

    def discover(self, state: dict):
        if state.get("full_done"):
            # Later passes: the newest novels and the latest updates.
            for path in ("sort/latest-novel", "sort/latest-release"):
                for page in range(1, 4):
                    books, _ = self._listing(path, page)
                    if not books:
                        break
                    yield books
            return
        if "queue" not in state:
            state["queue"] = LISTINGS + [f"genre/{g}{done}" for g in GENRES for done in ("", "/completed")]
            state["i"], state["page"] = 0, 1
        while state["i"] < len(state["queue"]):
            books, last = self._listing(state["queue"][state["i"]], state["page"])
            if books:
                yield books
            if not books or state["page"] >= min(last, MAX_PAGES):
                state["i"] += 1
                state["page"] = 1
            else:
                state["page"] += 1
        state["full_done"] = True

    def details(self, book: dict) -> BookInfo:
        s = self.http.get(f"{BASE}/novel/{book['sid']}").text
        title = _meta(s, "novel_name") or _text((re.search(r'<h1 class="tit">(.*?)</h1>', s, re.S) or ["", ""])[1])
        genres = [g.strip() for g in _meta(s, "genre").split(",") if g.strip()]
        origin = ORIGIN.get(_meta(s, "category").split(" ")[0].lower())
        last = re.search(r"/chapter-(\d+)$", _meta(s, "lastest_chapter_url"))
        vote = re.search(r'<p class="vote">\s*([\d.]+)\s*/\s*5\s*\(\s*(\d+)\s*votes?', s)
        summary = re.search(r'<div class="inner">(.*?)</div>', s, re.S)
        source = re.search(r'title="Source"></span>\s*<div class="right">.*?title="([^"]*)"', s, re.S)
        # "Moon Like Fire, 月如火, Yuè Rú Huǒ": one author's names, in English, Chinese and pinyin
        names = [a.strip() for a in re.split(r",\s*", _meta(s, "author")) if a.strip()]
        return BookInfo(
            sid=book["sid"], url=f"{BASE}/novel/{book['sid']}", title=title or book.get("title") or book["sid"],
            authors=names[:1], description=html_to_text(summary.group(1)).strip() if summary else None, lang="en",
            status=STATUS.get(_meta(s, "status").lower()), origin=origin,
            is_translation=None if not origin else origin != "en",
            chapters=int(last.group(1)) if last else None,
            rating=round(float(vote.group(1)) * 2, 2) if vote and float(vote.group(1)) else None,
            votes=int(vote.group(2)) if vote else None, access="free", adult=looks_adult(genres),
            updated_at=_meta(s, "update_time")[:10] or None, tags=genres or None,
            extra={"last": int(last.group(1)) if last else None, "source": source.group(1) if source else None,
                   "author_names": names},
        )

    # ----- text
    def chapters(self, book: dict) -> list[Chapter]:
        last = (book.get("extra") or {}).get("last") or book.get("chapters")
        if not last:
            last = self.details(book).extra.get("last") or 0
        return [Chapter(id=str(n), title=f"Chapter {n}", index=n - 1) for n in range(1, int(last) + 1)]

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        try:
            s = self.http.get(f"{BASE}/novel/{book['sid']}/chapter-{chapter.id}").text
        except NotFound:
            return ""
        start = s.find('<div id="article">')
        if start < 0:
            return ""
        end = s.find("<!--bg-->", start)
        title = re.search(r'<span class="chapter">(.*?)</span>', s, re.S)
        if title and _text(title.group(1)):
            chapter.title = _text(title.group(1))
        paras = [html_to_text(p).strip() for p in re.findall(r"<p[^>]*>(.*?)</p>", s[start:end if end > 0 else None], re.S)]
        return "\n".join(p for p in paras if p and not _NOTICE.search(p))
