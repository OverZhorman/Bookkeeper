"""NovelFire (novelfire.net): English web novels, mostly translations of Chinese, Korean and Japanese ones, about
23,000, with NovelUpdates-style tags (Weak to Strong, Transmigration, Male Protagonist...).

Catalog: the site-wide list, most popular first (24 novels per page). Details: the novel page (authors, often with the
original-language name, genres, tags, summary, rating, views, bookmarks, status). Catalog only: its chapter pages
send readers on to other sites now, so Bookkeeper doesn't read chapters there. robots.txt only keeps programs off its
API and search."""
import html as _html
import re

from ..analysis.text import clean_text, html_to_text
from ..http import NotFound
from .base import BookInfo, Site, SiteError, looks_adult, origin_from_title

BASE = "https://novelfire.net"
LIST = "genre-all/sort-popular/status-all/all-novel"
STATUS = {"completed": "completed", "ongoing": "ongoing", "hiatus": "frozen"}


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


def _count(s: str) -> int | None:
    """"17.3M", "19K", "1432" as numbers."""
    m = re.match(r"([\d.,]+)\s*([KMB]?)", (s or "").strip(), re.I)
    if not m:
        return None
    n = float(m.group(1).replace(",", ""))
    return int(n * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2).upper()])


def parse_list(page: str) -> tuple[list[BookInfo], int]:
    """One page of a novel list: its novels, and the number of its last page."""
    out = []
    for block in page.split('<li class="novel-item">')[1:]:
        link = re.search(r'<a title="([^"]*)" href="(?:https://novelfire\.net)?/book/([^"/?]+)"', block)
        if not link:
            continue
        cover = re.search(r'data-src="([^"]+)"', block)
        rating = re.search(r'icon-star"></i>([\d.]+)', block)
        chapters = re.search(r"([\d,]+) Chapters", block)
        rank = re.search(r'icon-award"></i>R ([\d,]+)', block)
        out.append(BookInfo(
            sid=link.group(2), url=f"{BASE}/book/{link.group(2)}", title=_text(link.group(1)) or link.group(2),
            cover=(BASE + cover.group(1) if cover.group(1).startswith("/") else cover.group(1)) if cover else None,
            lang="en", rating=round(float(rating.group(1)) * 2, 2) if rating and float(rating.group(1)) else None,
            chapters=_count(chapters.group(1)) if chapters else None, access="free",
            extra={"rank": _count(rank.group(1)) if rank else None},
        ))
    pages = [int(n) for n in re.findall(r"[?&]page=(\d+)", page)]
    return out, max(pages, default=1)


def parse_novel(slug: str, s: str) -> BookInfo:
    title = re.search(r'<h1 itemprop="name" class="novel-title[^"]*">(.*?)</h1>', s, re.S)
    if not title:
        raise SiteError("unexpected page layout (no novel title)")
    author_block = re.search(r'<div class="author">(.*?)</div>', s, re.S)
    names = [_text(a) for a in re.findall(r'<span itemprop="author">(.*?)</span>', author_block.group(1), re.S)] \
        if author_block else []
    latin = [n for n in names if not origin_from_title(n)]
    origin = next((o for o in map(origin_from_title, names) if o), None)
    stats = {small.lower(): strong for strong, small in re.findall(
        r"<strong[^>]*>(?:<i[^>]*></i>)?\s*([^<]*?)\s*</strong>\s*<small>([^<]+)</small>", s)}
    genres = [_text(g) for g in re.findall(r'<a href="/genre-[^"]+" title="[^"]*" class="property-item">(.*?)</a>', s)]
    tags = [_text(t) for t in re.findall(r'<a class="tag" href="/tags/[^"]+"[^>]*>(.*?)</a>', s)]
    rating = re.search(r'<strong class="nub">([\d.]+)</strong>', s)
    reviews = re.search(r"Reviews from ([\d,]+) readers", s)
    summary = re.search(r'<div class="summary">.*?<div class="content[^"]*">(.*?)<div class="expand">', s, re.S)
    cover = re.search(r'<meta property="og:image" content="([^"]+)"', s)
    labels = list(dict.fromkeys(x for x in genres + tags if x))
    return BookInfo(
        sid=slug, url=f"{BASE}/book/{slug}", title=_text(title.group(1)), authors=(latin or names)[:2],
        description=html_to_text(summary.group(1)).strip() or None if summary else None,
        cover=cover.group(1) if cover else None, lang="en", origin=origin,
        is_translation=True if origin else None, status=STATUS.get(stats.get("status", "").lower()),
        chapters=_count(stats.get("chapters", "")), views=_count(stats.get("views", "")),
        likes=_count(stats.get("bookmarked", "")), pop_raw=_count(stats.get("bookmarked", "")),
        rating=round(float(rating.group(1)) * 2, 2) if rating and float(rating.group(1)) else None,
        votes=_count(reviews.group(1)) if reviews else None, adult=looks_adult(labels), access="free",
        tags=labels or None, extra={"author_names": names},
    )


class NovelFire(Site):
    id = "novelfire"
    name = "NovelFire"
    home = BASE
    lang = "en"
    min_interval = 2.5
    has_text = False
    note = ("English translations of Chinese, Korean and Japanese web novels, about 23,000, with NovelUpdates-style "
            "tags. Catalog only: its chapter pages send readers on to other sites.")

    def _page(self, page: int) -> tuple[list[BookInfo], int]:
        try:
            s = self.http.get(f"{BASE}/{LIST}", params={"page": page} if page > 1 else None).text
        except NotFound:
            return [], 0
        return parse_list(s)

    def discover(self, state: dict):
        if state.get("full_done"):
            new = "genre-all/sort-new/status-all/all-novel"  # later passes: the newest novels
            for page in range(1, 4):
                try:
                    books, _ = parse_list(self.http.get(f"{BASE}/{new}", params={"page": page}).text)
                except NotFound:
                    break
                if not books:
                    break
                yield books
            return
        page = state.get("page", 1)
        while True:
            books, last = self._page(page)
            if books:
                yield books
            if not books or page >= last:
                state.update(full_done=True, page=1)
                return
            page += 1
            state["page"] = page

    def details(self, book: dict) -> BookInfo:
        return parse_novel(book["sid"], self.http.get(f"{BASE}/book/{book['sid']}").text)
