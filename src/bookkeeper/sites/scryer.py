"""Scryer (scryer.darklordpotter.net): the DLP community's search engine for FanFiction.net.

FanFiction.net itself blocks programs like Bookkeeper with Cloudflare, but Scryer lists its stories with everything
FanFiction.net shows (summary, rating, genres, characters, pairings, words, chapters, reviews, favorites, follows,
status, dates) plus content tags of its own (time travel, self insert, harem...). Bookkeeper reads the fandoms you
choose (Settings): the most favorited stories first, then the latest updates on later passes. The stories themselves
stay on FanFiction.net, so this is a catalog only (no narration check, no downloads).
Logged out, Scryer shows 50 pages (1,250 stories) of each list; logged in, 200 pages (5,000)."""
import html as _html
import re

from ..analysis.text import clean_text
from .base import BookInfo, Site, looks_adult

BASE = "https://scryer.darklordpotter.net"
FFN = "https://www.fanfiction.net"
DEFAULT_FANDOMS = ("Harry Potter, Naruto, Pokémon, Percy Jackson and the Olympians, My Hero Academia, Worm, "
                   "Star Wars, Avengers, One Piece, RWBY")
RATINGS = {"K": "G", "K+": "G", "T": "PG-13", "M": "R"}
STATUS = {"Complete": "completed", "In-Progress": "ongoing"}
LANGS = {"english": "en", "russian": "ru", "русский": "ru", "ukrainian": "uk", "українська": "uk"}
GENRES = {"Adventure", "Angst", "Crime", "Drama", "Family", "Fantasy", "Friendship", "General", "Horror", "Humor",
          "Hurt/Comfort", "Mystery", "Parody", "Poetry", "Romance", "Sci-Fi", "Spiritual", "Supernatural", "Suspense",
          "Tragedy", "Western"}
MAX_PAGES = 200
# Scryer's content tags come from Harry Potter fan fiction; these only mean something there.
HP_ONLY = {"dark harry", "grey harry", "powerful harry", "independent harry", "wrong boy who lived", "marauders era",
           "evil manipulative dumbledore", "founders era", "marriage law", "next gen", "master of death"}
_CARD = re.compile(r'<div class="panel panel-default">\s*<div class="panel-heading">(.*?)'
                   r'(?=<div class="panel panel-default">\s*<div class="panel-heading">|<div class="text-right">|\Z)', re.S)


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


def _int(s: str | None) -> int | None:
    digits = re.sub(r"\D", "", s or "")
    return int(digits) if digits else None


def _genres(token: str) -> list[str] | None:
    """'Adventure/Hurt/Comfort' -> ['Adventure', 'Hurt/Comfort']; None if the token isn't a genre list."""
    parts = token.replace("Hurt/Comfort", "Hurt\x00Comfort").split("/")
    parts = [p.replace("\x00", "/").strip() for p in parts]
    return parts if parts and all(p in GENRES for p in parts) else None


def parse_card(block: str, fandom: str, lang: str | None) -> BookInfo | None:
    link = re.search(r'class="story-link"[^>]*data-story-id="(\d+)"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
    if not link:
        return None
    sid = link.group(1)
    author = re.search(r'class="author-link"[^>]*>(.*?)</a>', block, re.S)
    summary_block = re.search(r'<div class="story-summary panel-body">(.*?)<div>', block, re.S)
    labels = [_text(t) for t in re.findall(r'<span class="label label-default">(.*?)</span>', block, re.S)]
    foot = re.search(r'<div class="panel-footer small">(.*)', block, re.S)
    foot = foot.group(1) if foot else ""
    partner = re.search(r'<i class="fa fa-random"></i>(.*?)<span class="pull-right', foot, re.S)
    fandoms = [fandom] + ([_text(partner.group(1)).rstrip(" -").strip()] if partner else [])
    if "harry potter" not in {f.lower() for f in fandoms}:
        labels = [x for x in labels if x.lower() not in HP_ONLY]
    updated = re.search(r'<time datetime="(\d{4}-\d\d-\d\d)', foot)
    status = re.search(r'<strong title="Published: (\d{4}-\d\d-\d\d)[^"]*">\s*(.*?)\s*</strong>(.*)', foot, re.S)
    pairings = ["/".join(n.strip() for n in _text(p).split(",") if n.strip())
                for p in re.findall(r'<i class="fa fa-margin fa-angle-left"></i>(.*?)<i class="fa fa-margin fa-angle-right">',
                                    foot, re.S)]
    rest = re.sub(r"\s+", " ", _text(status.group(3))) if status else ""
    # "- M - Romance/Supernatural - Hermione G., Lucius M. - 20,578 words - ...": split on the lone hyphens
    tokens = [t.strip() for t in re.split(r"(?<!\S)-(?!\S)", rest) if t.strip()]
    rating = tokens.pop(0) if tokens and tokens[0] in RATINGS else None
    genres = _genres(tokens[0]) if tokens else None
    if genres:
        tokens.pop(0)
    characters = []
    if tokens and not re.match(r"[\d,]+ (words|chapters?)$", tokens[0]):
        characters = list(dict.fromkeys(c.strip() for c in tokens[0].split(",") if c.strip()))

    def count(name: str) -> int | None:
        m = re.search(r"([\d,]+) " + name, rest)
        return _int(m.group(1)) if m else None

    favorites = count("favorites?")
    tags = list(dict.fromkeys([*(genres or []), *(f"fandom:{f}" for f in fandoms if f), *labels,
                               *(p for p in pairings if "/" in p), *characters]))
    return BookInfo(
        sid=sid, url=f"{FFN}/s/{sid}/1/", title=_text(link.group(3)) or sid,
        authors=[_text(author.group(1))] if author else [],
        description=_text(summary_block.group(1)) or None if summary_block else None, lang=lang,
        status=STATUS.get(status.group(2).strip()) if status else None, is_translation=False,
        chapters=count("chapters?"), words=count("words"), likes=favorites, pop_raw=favorites,
        adult=looks_adult(labels), age_rating=RATINGS.get(rating or ""), access="free",
        created_at=status.group(1) if status else None, updated_at=updated.group(1) if updated else None,
        tags=tags, extra={"rating": rating, "fandoms": fandoms, "reviews": count("reviews?"),
                          "follows": count("follows?"), "scryer": f"{BASE}/stories/{sid}/related"},
        complete=True,
    )


def parse_results(page: str, fandom: str, lang: str | None) -> list[BookInfo]:
    return [b for b in (parse_card(m.group(1), fandom, lang) for m in _CARD.finditer(page)) if b]


def last_page(page: str) -> int:
    nums = [int(n) for n in re.findall(r'href="/search\?[^"]*page=(\d+)', page)]
    return max(nums, default=1)


def fandom_ids(home: str) -> dict[str, str]:
    """Fandom name (lower case) -> Scryer id, from the search form (main fandoms, then every crossover fandom)."""
    out: dict[str, str] = {}
    for name in ("search[crossovers][]", "search[fandoms][]"):
        sel = re.search(r'name="' + re.escape(name) + r'"[^>]*>(.*?)</select>', home, re.S)
        for fid, label in re.findall(r'<option[^>]*value="(\d+)"[^>]*>([^<]*)', sel.group(1) if sel else ""):
            out[re.sub(r"\s*\(\d+\)$", "", _html.unescape(label)).strip().lower()] = fid
    return out


class Scryer(Site):
    id = "scryer"
    name = "Scryer (FanFiction.net)"
    home = BASE
    lang = "en"
    min_interval = 4.0
    has_text = False
    note = ("FanFiction.net's stories, through the DLP community's search engine (FanFiction.net itself blocks "
            "Bookkeeper). Catalog only: the stories stay on FanFiction.net. Bookkeeper reads the fandoms you choose "
            "(Settings); log in to Scryer to read 5,000 stories per fandom instead of 1,250.")
    login_url = f"{BASE}/login"
    login_benefit = "Longer lists: 200 pages (5,000 stories) per fandom instead of 50."
    login_form = {"user": "#user_email", "password": "#user_password"}
    logged_in_js = ("!/login|sign_in/.test(location.pathname) && !document.querySelector('a[href=\"/login\"]')")
    extra_settings = {
        "fandoms": {"label": "Fandoms to collect, comma-separated, as Scryer names them (Harry Potter, Naruto, "
                             "Pokémon, Worm...)", "default": DEFAULT_FANDOMS},
        "pages": {"label": "Pages to read per fandom (25 stories each, most favorited first; Scryer shows 50 pages "
                           "logged out, 200 logged in)", "default": "200"},
        "languages": {"label": "Languages, comma-separated, as Scryer names them (english, russian...)",
                      "default": "english"},
    }

    def check_login(self) -> bool | None:
        return 'href="/login"' not in self.http.get(f"{BASE}/").text

    def _fandoms(self) -> list[str]:
        raw = str(self.settings.get("fandoms") or DEFAULT_FANDOMS)
        return [f.strip() for f in raw.split(",") if f.strip()]

    def _languages(self) -> list[str]:
        raw = str(self.settings.get("languages") or "english")
        return [x.strip().lower() for x in raw.split(",") if x.strip()]

    def _search(self, fid: str, fandom: str, language: str, sort: str, page: int) -> tuple[list[BookInfo], int]:
        params = {"search[fandoms][]": fid, "search[language]": language, "search[sort_by]": sort,
                  "search[order_by]": "desc"}
        if page > 1:
            params["page"] = page
        p = self.http.get(f"{BASE}/search", params=params, ok_status=(401,))
        if p.status == 401:  # "You must be logged in to view more results"
            return [], 0
        books = parse_results(p.text, fandom, LANGS.get(language))
        return books, (last_page(p.text) if books else 0)

    def discover(self, state: dict):
        ids = fandom_ids(self.http.get(f"{BASE}/").text)
        lists = [(f, ids[f.lower()], lang) for f in self._fandoms() if f.lower() in ids for lang in self._languages()]
        if not lists:
            return
        pages = min(MAX_PAGES, _int(str(self.settings.get("pages") or "200")) or MAX_PAGES)
        if state.get("full_done"):
            for fandom, fid, lang in lists:  # later passes: the latest updates
                for page in range(1, 4):
                    books, last = self._search(fid, fandom, lang, "updated", page)
                    if books:
                        yield books
                    if page >= last:
                        break
            return
        while state.get("li", 0) < len(lists):
            fandom, fid, lang = lists[state.get("li", 0)]
            page = state.get("page", 1)
            books, last = self._search(fid, fandom, lang, "meta.favs", page)
            if books:
                yield books
            if page >= min(last, pages):
                state.update(li=state.get("li", 0) + 1, page=1)
            else:
                state["page"] = page + 1
        state.update(full_done=True, li=0, page=1)

    def details(self, book: dict) -> BookInfo:
        raise NotImplementedError  # the search results already have everything
