"""FanMTL (fanmtl.com): machine translations of Chinese web novels into English, many of them fan fiction (Naruto,
One Piece, Douluo, Marvel, Pokémon, Hogwarts...), plus some English originals: about 165,000 novels.

Catalog: the site's full list of novels, first by popularity (that order gives every novel its rank) and then by date
added, which catches anything the popularity order skipped while it shifted. Later passes read the newest novels until
they reach ones seen before, and the latest updates. Details: the novel page (author, original title, categories,
tags, status, summary). Text: chapter pages (/novel/<id>_<n>.html), numbered from 1."""
import html as _html
import re

from ..analysis.text import clean_text, html_to_text
from ..http import NotFound
from .base import BookInfo, Chapter, Site, SiteError, looks_adult, origin_from_title

BASE = "https://www.fanmtl.com"
PER_PAGE = 30
BATCH_PAGES = 5         # list pages read per batch while walking the whole list
NEW_PAGES = 200         # later passes: at most this many pages of new novels
STATUS = {"ongoing": "ongoing", "completed": "completed"}
MTL = "Machine translation"
# Categories that are fandoms, as Bookkeeper names them.
FANDOMS = {"douluo": "Douluo Dalu", "dragon ball": "Dragon Ball", "marvel": "Marvel", "pokemon": "Pokemon",
           "hogwarts": "Harry Potter", "naruto": "Naruto", "one piece": "One Piece"}
# Categories that say nothing about the story: the site it was copied from, the site's own picks.
SKIP = {"faloo", "hot", "other", "all", "new"}
SPLIT = {"wuxia xianxia": ["Wuxia", "Xianxia"]}  # one category on the source site, two genres here
UNKNOWN_AUTHOR = {"佚名", "未知", "unknown", "anonymous"}
_ITEM = re.compile(r'<li class="novel-item">\s*<a href="/novel/([^"/]+)\.html" title="([^"]*)"(.*?)</li>', re.S)
_NOTICE = re.compile(r"(?i)fanmtl\W*com|f\W?a\W?n\W?m\W?t\W?l\W*c\W?o\W?m|^\(?end of (this )?chapter\)?\.?$")
# Lists show the number of a novel's newest chapter. Most novels number their chapters from 1, so that's also how
# many there are, but some old ones use site-wide numbers (522356, 522357...), which say nothing about the count.
MAX_CHAPTERS = 100_000


def _text(fragment: str) -> str:
    s = _html.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))
    if re.search(r"&(#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);", s):  # some titles are escaped twice ("&amp;#039;")
        s = _html.unescape(s)
    return clean_text(s)


def _labels(category: str) -> list[str]:
    return [f"fandom:{FANDOMS[x.lower()]}" if x.lower() in FANDOMS else x
            for x in SPLIT.get(category.lower(), [category])]


class FanMtl(Site):
    id = "fanmtl"
    name = "FanMTL"
    home = BASE
    lang = "en"
    min_interval = 2.5
    note = ("Machine translations of Chinese web novels, many of them fan fiction (Naruto, One Piece, Douluo, "
            "Marvel, Pokémon), about 165,000. Its whole list is read twice at first: by popularity, then by date.")

    # ----- catalog
    def _card(self, sid: str, title: str, rest: str, rank: int | None) -> BookInfo:
        count = re.search(r"(\d+) Chapters?\s*</span>", rest)
        status = re.search(r'<span class="status[^"]*">([^<]+)</span>', rest)
        cover = re.search(r'data-src="(/d/file/[^"]+)"', rest)
        n = int(count.group(1)) if count else None
        return BookInfo(
            sid=sid, url=f"{BASE}/novel/{sid}.html", title=_text(title) or sid, lang="en", access="free",
            status=STATUS.get(status.group(1).strip().lower()) if status else None,
            chapters=n if n and n <= MAX_CHAPTERS else None,
            cover=BASE + cover.group(1) if cover else None, pop_raw=1_000_000 - rank if rank else None,
            extra={"last": n} if n else {},
        )

    def _list(self, sort: str, page: int) -> tuple[list[BookInfo], int]:
        """One page of the list of all novels (sort: onclick = popular, newstime = added, lastdotime = updated):
        its novels and the number of the list's last page (pages count from 0)."""
        try:
            s = self.http.get(f"{BASE}/list/all/all-{sort}-{page}.html").text
        except NotFound:
            return [], page
        pages = [int(n) for n in re.findall(r"/list/all/all-" + sort + r"-(\d+)\.html", s)]
        start = s.find('<ul class="novel-list')
        if start < 0:
            raise SiteError("list page without its list of novels (layout changed?)")
        items = _ITEM.findall(s[start:s.find("</ul>", start)])
        books = [self._card(sid, title, rest, page * PER_PAGE + i + 1 if sort == "onclick" else None)
                 for i, (sid, title, rest) in enumerate(items)]
        return books, max(pages + [page])

    def discover(self, state: dict):
        if state.get("full_done"):
            yield from self._newest(state)
            return
        # First pass: the whole list by popularity, then by date added (a few pages per batch: it's 5,500 pages).
        while state.setdefault("stage", "onclick") != "done":
            sort, batch = state["stage"], []
            while len(batch) < BATCH_PAGES * PER_PAGE:
                page = state.get("page", 0)
                books, last = self._list(sort, page)
                state["last"] = max(last, state.get("last") or 0) if page else last
                if sort == "newstime" and page == 0 and books:
                    state["top"] = [b.sid for b in books]
                batch += books
                if page >= state["last"]:
                    state.update(stage="newstime" if sort == "onclick" else "done", page=0, last=0)
                    break
                state["page"] = page + 1
            if batch:
                yield batch
        state["full_done"] = True

    def _newest(self, state: dict):
        """Later passes: new novels until the ones that were newest last time, then the latest updates."""
        seen, first = set(state.get("top") or []), None
        for page in range(NEW_PAGES):
            books, last = self._list("newstime", page)
            if books:
                first = first or [b.sid for b in books]
                yield books
            if not books or page >= last or seen & {b.sid for b in books}:
                break
        if first:
            state["top"] = first
        for page in range(3):
            books, last = self._list("lastdotime", page)
            if books:
                yield books
            if not books or page >= last:
                break

    def details(self, book: dict) -> BookInfo:
        url = f"{BASE}/novel/{book['sid']}.html"
        s = self.http.get(url).text
        h1 = re.search(r'<h1[^>]*class="novel-title[^"]*">(.*?)</h1>', s, re.S)
        if not h1:
            raise NotFound(url)
        title = _text(h1.group(1)) or book.get("title") or book["sid"]
        alt = re.search(r'<h2 class="alternative-title[^"]*">(.*?)</h2>', s, re.S)
        raw_title = _text(alt.group(1)) if alt else ""
        author = re.search(r'<span itemprop="author">(.*?)</span>', s, re.S)
        author = _text(author.group(1)) if author else ""
        count = re.search(r'<i class="fas fa-book"></i>\s*(\d+)', s)  # the newest chapter's number
        first = re.search(r'id="readchapterbtn" href="/novel/' + re.escape(book["sid"]) + r'_(\d+)\.html"', s)
        last = re.search(r"Latest Release:.*?/novel/" + re.escape(book["sid"]) + r"_(\d+)\.html", s, re.S)
        status = re.search(r"<strong[^>]*>\s*(\w+)\s*</strong>\s*<small>Status</small>", s)
        cover = re.search(r'<figure class="cover">\s*<img[^>]*data-src="(/d/file/[^"]+)"', s)
        categories = [_text(c) for c in re.findall(r'class="property-item">(.*?)</a>', s, re.S)]
        info = s.find('<section id="info"')
        tags = [_text(t) for t in re.findall(r'<a class="tag"\s+href=\'/tags/\d+-\d+\.html\'>(.*?)</a>',
                                             s[info:] if info >= 0 else s, re.S)]
        summary = re.search(r'<div class="summary">.*?<div class="content">(.*?)</div>', s, re.S)
        description = "\n".join(line for line in html_to_text(summary.group(1)).split("\n")
                                if not line.lower().startswith("novel keywords")) if summary else ""
        origin = origin_from_title(raw_title)
        labels = [x for c in categories if c and c.lower() not in SKIP for x in _labels(c)] + [t for t in tags if t]
        source = next((c for c in categories if c.lower() == "faloo"), None)
        n = int(last.group(1)) if last else int(count.group(1)) if count else None
        one = int(first.group(1)) if first else 1
        return BookInfo(
            sid=book["sid"], url=url, title=title, alt_titles=[raw_title] if raw_title and raw_title != title else [],
            authors=[author] if author and author.lower() not in UNKNOWN_AUTHOR else [],
            description=description or None, cover=BASE + cover.group(1) if cover else None, lang="en",
            status=STATUS.get(status.group(1).lower()) if status else None,
            is_translation=True if origin else None, origin=origin,
            chapters=n - one + 1 if n and n >= one else None, access="free", adult=looks_adult(labels),
            tags=list(dict.fromkeys(labels + ([MTL] if origin else []))),
            extra={"first": one, "last": n, "raw_title": raw_title or None, "source": source},
        )

    # ----- text
    def chapters(self, book: dict) -> list[Chapter]:
        extra = book.get("extra") or {}
        first, last = extra.get("first"), extra.get("last")
        if not first or not last:  # listed but not looked at yet: the novel page says where its chapters start
            extra = self.details(book).extra
            first, last = extra.get("first") or 1, extra.get("last") or 0
        return [Chapter(id=str(n), title=f"Chapter {i + 1}", index=i)
                for i, n in enumerate(range(int(first), int(last) + 1))]

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        try:
            s = self.http.get(f"{BASE}/novel/{book['sid']}_{chapter.id}.html").text
        except NotFound:
            return ""
        start = s.find('<div class="chapter-content">')
        if start < 0:
            return ""
        end = s.find('<div class="chapternav', start)
        title = re.search(r'<header class="chapter-header.*?<h2>(.*?)</h2>', s, re.S)
        if title and _text(title.group(1)):
            chapter.title = _text(title.group(1))
        text = html_to_text(s[start:end if end > 0 else None])
        lines = [line for line in text.split("\n") if not _NOTICE.search(line)]
        if lines and len(lines[0]) < 200 and re.match(r"(?i)chapter\s*\d+\b", lines[0]):
            lines = lines[1:]  # the chapter's heading again (it's kept as the chapter's title)
        return "\n".join(lines)
