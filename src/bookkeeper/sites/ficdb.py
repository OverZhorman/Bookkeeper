"""Ficdb (ficdb.net): a search engine for web fiction on SpaceBattles, Sufficient Velocity, Questionable Questing,
AO3, FanFiction.net, Scribble Hub and Royal Road, with tags its users add.

Ficdb's search shows browsers a small JavaScript check, and gives programs a "limited search" instead: the same
results, without links on the tags (its owner added that because bots got stuck following tag links forever).
Bookkeeper uses that limited search as it is meant for programs: it reads only the tags you choose (Settings),
page by page, slowly, and never follows tag links. Highest-rated stories first; later passes read the latest updates.
Catalog only: the stories themselves are on the sites Ficdb links to."""
import html as _html
import re
from datetime import date, datetime

from .. import tags as T
from ..analysis.text import clean_text, detect_lang
from ..http import NotFound
from .base import BookInfo, Site, looks_adult

BASE = "https://ficdb.net"
DEFAULT_TAGS = "Original Work, LitRPG, Progression, GameLit, Isekai, Self-Insert, Reincarnation, Dungeon Crawler"
SOURCES = {"SB": "SpaceBattles", "SV": "Sufficient Velocity", "QQ": "Questionable Questing", "AO3": "AO3",
           "FFN": "FanFiction.net", "SH": "Scribble Hub", "RR": "Royal Road"}
MAX_PAGES = 200                              # Ficdb shows 200 pages (5,000 stories) of a search
_GROUP = re.compile(r'<div class="field is-grouped is-grouped-multiline">(.*?)</div>\s*(?=<div class="field|'
                    r'<div class="content)', re.S)


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))).strip()


def _count(s: str) -> int | None:
    """'74K' -> 74000, '4.9K' -> 4900, '1.2M' -> 1200000, '59' -> 59."""
    m = re.match(r"\s*([\d.,]+)\s*([KkMm]?)", s or "")
    if not m:
        return None
    n = float(m.group(1).replace(",", ""))
    return int(round(n * {"k": 1_000, "m": 1_000_000}.get(m.group(2).lower(), 1)))


def _date(s: str, today: date | None = None) -> str | None:
    """'Oct 11, 2026' -> 2026-10-11; 'Nov 17' (this year's dates have no year) -> this year, or last if ahead."""
    s, today = (s or "").strip(), today or date.today()
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    try:
        d = datetime.strptime(f"{s} {today.year}", "%b %d %Y").date()
    except ValueError:
        return None
    return (d.replace(year=d.year - 1) if d > today else d).isoformat()


def _fandom(name: str) -> str:
    """Ficdb's first tag group holds fandoms, but also things like Original Work or LitRPG: those stay plain labels."""
    categories = {(T.info(t) or {}).get("category") for t in T.canonical(name)}
    plain = "fandom" not in categories and categories - {None, "other"}
    return name if plain else f"fandom:{name}"


def parse_card(block: str, today: date | None = None) -> BookInfo | None:
    sid = re.search(r'href="/edit_story/(\d+)"', block)
    title = re.search(r'<p class="title[^"]*">\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
    if not sid or not title:
        return None
    sources = {code: url for url, code in re.findall(r'<a target="_blank" href="([^"]+)" class="tag">(\w+)</a>', block)}
    author = re.search(r'<p class="subtitle[^"]*">\s*by\s+(.*?)</p>', block, re.S)
    groups = [[_text(t) for t in re.findall(r'<span class="tag[^"]*">(.*?)</span>', g, re.S)] for g in _GROUP.findall(block)]
    fandoms, labels = (groups[0], [t for g in groups[1:] for t in g]) if groups else ([], [])
    summary = re.search(r'<div class="truncated-content"[^>]*>(.*?)</div>', block, re.S)
    stats = re.search(r'Word Count:(.*?)</small>', block, re.S)
    st = stats.group(1) if stats else ""

    def stat(name: str) -> str:
        m = re.search(name + r":\s*(?:<time[^>]*>)?([^<·]+)", st)
        return m.group(1).strip() if m else ""

    words = _count(_text(st.split("·")[0])) if st else None
    rating = _count(stat("Rating"))
    description = "\n".join(_text(p) for p in re.findall(r"<p>(.*?)</p>", summary.group(1), re.S)) if summary else ""
    name = _text(title.group(2))
    tags = list(dict.fromkeys([*(_fandom(f) for f in fandoms if f), *labels]))
    return BookInfo(
        sid=sid.group(1), url=_html.unescape(title.group(1)), title=name or sid.group(1),
        authors=[_text(author.group(1))] if author and _text(author.group(1)) else [],
        description=description or None, lang=detect_lang(f"{name}\n{description}"), is_translation=False,
        chapters=_count(stat("Chapters")), words=words, likes=rating, pop_raw=rating, adult=looks_adult(labels),
        access="free", created_at=_date(stat("Created"), today), updated_at=_date(stat("Updated"), today), tags=tags,
        extra={"sources": {SOURCES.get(k, k): v for k, v in sources.items()}, "fandoms": fandoms,
               "ficdb": f"{BASE}/edit_story/{sid.group(1)}"},
        complete=True,
    )


def parse_results(page: str, today: date | None = None) -> list[BookInfo]:
    blocks = page.split('<div class="card">')[1:]
    return [b for b in (parse_card(x, today) for x in blocks) if b]


def last_page(page: str) -> int:
    return max((int(n) for n in re.findall(r'class="pagination-link"[^>]*href=[^>]*[?&]page=(\d+)', page)), default=1)


class Ficdb(Site):
    id = "ficdb"
    name = "Ficdb"
    home = BASE
    lang = "en"
    min_interval = 6.0                        # a small volunteer-run site: slowly
    has_text = False
    note = ("Stories from SpaceBattles, Sufficient Velocity, Questionable Questing, AO3, FanFiction.net, Scribble Hub "
            "and Royal Road, with the tags Ficdb's users add. Bookkeeper reads the tags you choose (Settings), "
            "through the limited search Ficdb gives programs. Catalog only: the stories stay on those sites.")
    extra_settings = {
        "tags": {"label": "Ficdb tags or fandoms to collect, comma-separated (Isekai, Self-Insert, Progression, "
                          "LitRPG, Original Work, Worm...)", "default": DEFAULT_TAGS},
        "pages": {"label": "Pages to read per tag (25 stories each, highest rated first; Ficdb shows up to 200)",
                  "default": "40"},
    }

    def _tags(self) -> list[str]:
        raw = str(self.settings.get("tags", DEFAULT_TAGS) or "")
        return [t.strip() for t in raw.split(",") if t.strip()]

    def _search(self, tag: str, page: int, sort: str | None) -> tuple[list[BookInfo], int]:
        params = {"searchbox": tag, "safe_search": "y", "unverified": "1"}
        if sort:
            params["sortby"] = sort
        if page > 1:
            params["page"] = page
        try:
            p = self.http.get(f"{BASE}/search", params=params)
        except NotFound:
            return [], 0
        books = parse_results(p.text)
        return books, (last_page(p.text) if books else 0)

    def discover(self, state: dict):
        tags = self._tags()
        pages = min(MAX_PAGES, int(re.sub(r"\D", "", str(self.settings.get("pages") or "40")) or 40))
        if state.get("full_done"):
            for tag in tags:  # later passes: the latest updates (Ficdb's own default order)
                for page in range(1, 3):
                    books, last = self._search(tag, page, None)
                    if books:
                        yield books
                    if page >= last:
                        break
            return
        while state.get("ti", 0) < len(tags):
            tag, page = tags[state.get("ti", 0)], state.get("page", 1)
            books, last = self._search(tag, page, "rating")
            if books:
                yield books
            if page >= min(last, pages):
                state.update(ti=state.get("ti", 0) + 1, page=1)
            else:
                state["page"] = page + 1
        state.update(full_done=True, ti=0, page=1)

    def details(self, book: dict) -> BookInfo:
        raise NotImplementedError  # the search results already have everything
