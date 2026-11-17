"""Hardcover (hardcover.app): a book catalog where readers add genres, moods, content warnings and tags.

Hardcover's website asks programs to stay off it, but it has an official API for personal tools. It needs your own
API token: make one on Hardcover (Account -> Hardcover API -> New API Key) with only "read:catalog" ticked, which can
read the public catalog and nothing in your account, and paste it into Settings. Bookkeeper keeps it encrypted with
your Windows account, like saved passwords.
Bookkeeper reads the book categories (Web Novel, Light Novel...) and tags you choose, the most shelved books first,
100 books per request (the free API allows 5,000 requests a day). Catalog only: Hardcover has no text."""
import json
import re

from .. import __version__
from ..analysis.text import detect_lang
from ..http import Blocked
from .base import BookInfo, Site, SiteError, TemporaryError, looks_adult

API = "https://api.hardcover.app/v1/graphql"
BASE = "https://hardcover.app"
TOKEN_URL = f"{BASE}/account/api/keys/new?scope=read:catalog"
CATEGORIES = {"book": 1, "novella": 2, "short story": 3, "graphic novel": 4, "fan fiction": 5, "research paper": 6,
              "poetry": 7, "collection": 8, "web novel": 9, "light novel": 10}
CATEGORY_NAMES = {v: k.title() for k, v in CATEGORIES.items()}
DEFAULT_CATEGORIES = "Web Novel, Light Novel"
DEFAULT_TAGS = "LitRPG, Progression Fantasy, GameLit, Cultivation, Isekai, Portal Fantasy, Dungeon Core"
PER_PAGE = 100
FIELDS = ("id title subtitle slug description release_date pages rating ratings_count users_count users_read_count "
          "book_category_id cached_tags cached_contributors cached_image alternative_titles")
BOOKS = ("query Books($where: books_bool_exp!, $offset: Int!, $order: [books_order_by!]) { books(where: $where, "
         f"order_by: $order, limit: {PER_PAGE}, offset: $offset) {{ {FIELDS} }} }}")
TAGS = "query Tags($names: [String!]!) { tags(where: {tag: {_in: $names}}) { id tag } }"
POPULAR = [{"users_count": "desc"}, {"id": "asc"}]
NEWEST = [{"created_at": "desc"}, {"id": "desc"}]


def _names(value) -> list[str]:
    """Hardcover's cached JSON comes as lists of strings or of objects; take the names either way."""
    out = []
    for x in value or []:
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, dict):
            name = x.get("tag") or x.get("name") or x.get("title")
            if name and (x.get("spoilerRatio") or 0) < 0.5:  # tags most readers mark as spoilers are left out
                out.append(str(name))
    return out


def _tags(cached) -> list[str]:
    if isinstance(cached, str):
        try:
            cached = json.loads(cached)
        except ValueError:
            return []
    if isinstance(cached, dict):  # {"Genre": [...], "Mood": [...], "Content Warning": [...], "Tag": [...]}
        order = ["Genre", "Tag", "Mood", "Content Warning"]
        keys = sorted(cached, key=lambda k: order.index(k) if k in order else len(order))
        return [n for k in keys for n in _names(cached.get(k))]
    return _names(cached)


def _contributors(cached) -> tuple[list[str], bool]:
    """(authors, is a translation) from cached_contributors: [{"author": {"name": ...}, "contribution": None}]."""
    authors, translated = [], False
    for c in cached if isinstance(cached, list) else []:
        if not isinstance(c, dict):
            continue
        role = (c.get("contribution") or "").strip().lower()
        name = (c.get("author") or {}).get("name") if isinstance(c.get("author"), dict) else c.get("name")
        if role == "translator":
            translated = True
        elif name and role in ("", "author"):
            authors.append(" ".join(str(name).split()))
    return list(dict.fromkeys(authors)), translated


def book_info(b: dict) -> BookInfo:
    authors, translated = _contributors(b.get("cached_contributors"))
    category = CATEGORY_NAMES.get(b.get("book_category_id"))
    labels = list(dict.fromkeys(([category] if category and category != "Book" else []) + _tags(b.get("cached_tags"))))
    image = b.get("cached_image")
    alt = [a for a in _names(b.get("alternative_titles")) if a and a != b.get("title")]
    rating = b.get("rating")
    description = (b.get("description") or "").strip() or None
    title = (b.get("title") or "").strip() or str(b["id"])
    return BookInfo(
        sid=str(b["id"]), url=f"{BASE}/books/{b.get('slug') or b['id']}", title=title,
        alt_titles=([b["subtitle"]] if b.get("subtitle") else []) + alt, authors=authors, description=description,
        cover=(image.get("url") if isinstance(image, dict) else image) or None,
        lang=detect_lang(f"{title}\n{description or ''}"), is_translation=translated,
        rating=round(float(rating) * 2, 2) if rating else None, votes=b.get("ratings_count"),
        likes=b.get("users_read_count"), pop_raw=b.get("users_count"), adult=looks_adult(labels),
        created_at=b.get("release_date"), tags=labels,
        extra={"pages": b.get("pages"), "category": category, "readers": b.get("users_count")}, complete=True,
    )


class Hardcover(Site):
    id = "hardcover"
    name = "Hardcover"
    home = BASE
    lang = "en"
    min_interval = 1.5                        # the free API allows 60 requests a minute
    has_text = False
    note = ("Published books with readers' genres, moods, content warnings and tags, through Hardcover's official "
            "API. Needs your own Hardcover API token (Settings). Catalog only.")
    extra_settings = {
        "token": {"label": "Your Hardcover API token. Make one with only “read:catalog” ticked (it can't see or change "
                           "your account) and paste it here; it's encrypted with your Windows account.",
                  "default": "", "secret": True, "link": TOKEN_URL, "link_label": "Make a read-only token on Hardcover"},
        "categories": {"label": "Book categories to collect, comma-separated (Web Novel, Light Novel, Fan Fiction, "
                                "Novella, Book...)", "default": DEFAULT_CATEGORIES},
        "tags": {"label": "Tags to collect, comma-separated, as Hardcover names them (LitRPG, Progression Fantasy...)",
                 "default": DEFAULT_TAGS},
        "pages": {"label": "Requests per category or tag (100 books each, the most shelved first)", "default": "30"},
    }

    def _token(self) -> str:
        token = str(self.settings.get("token") or "").strip()
        if not token:
            raise SiteError("paste your Hardcover API token in this site's Settings (a read-only one is enough)")
        return token

    def _query(self, query: str, variables: dict) -> dict:
        token = self._token()
        if not token.lower().startswith("bearer "):
            token = f"Bearer {token}"
        try:
            p = self.http.post(API, json_body={"query": query, "variables": variables}, ok_status=(400, 403, 408),
                               headers={"Authorization": token, "Content-Type": "application/json",
                                        "User-Agent": f"Bookkeeper/{__version__} (personal book catalog)"})
        except Blocked as e:
            if "401" in str(e):
                raise SiteError("Hardcover didn't accept the API token (expired or deleted?): make a new one and "
                                "paste it in Settings") from e
            raise
        if p.status == 408:
            raise TemporaryError("Hardcover took too long to answer")
        data = p.json()
        if p.status != 200 or data.get("errors") or data.get("error"):
            err = data.get("errors") or data.get("error_description") or data.get("error") or p.status
            if isinstance(err, list):
                err = "; ".join(str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in err)
            raise SiteError(f"Hardcover API: {err}")
        return data.get("data") or {}

    def _lists(self) -> list[tuple[str, dict]]:
        base = {"book_status_id": {"_eq": 1}, "canonical_id": {"_is_null": True}}
        out = []
        for name in str(self.settings.get("categories", DEFAULT_CATEGORIES) or "").split(","):
            cid = CATEGORIES.get(name.strip().lower())
            if cid:
                out.append((f"category {name.strip()}", {**base, "book_category_id": {"_eq": cid}}))
        tags = [t.strip() for t in str(self.settings.get("tags", DEFAULT_TAGS) or "").split(",") if t.strip()]
        if tags:
            found: dict[str, list[int]] = {}
            for t in self._query(TAGS, {"names": tags}).get("tags") or []:
                found.setdefault(t["tag"].lower(), []).append(t["id"])
            for t in tags:
                if found.get(t.lower()):
                    out.append((f"tag {t}", {**base, "taggings": {"tag_id": {"_in": found[t.lower()]}}}))
        return out

    def _page(self, where: dict, page: int, order: list) -> tuple[list[BookInfo], int]:
        """The books on one page, and how many rows the API gave (fewer than PER_PAGE: the list's end)."""
        rows = self._query(BOOKS, {"where": where, "offset": (page - 1) * PER_PAGE, "order": order}).get("books") or []
        return [book_info(b) for b in rows if b.get("id")], len(rows)

    def discover(self, state: dict):
        self._token()
        lists = self._lists()
        pages = int(re.sub(r"\D", "", str(self.settings.get("pages") or "30")) or 30)
        if state.get("full_done"):
            for _, where in lists:  # later passes: the books added to Hardcover since
                books, _ = self._page(where, 1, NEWEST)
                if books:
                    yield books
            return
        while state.get("li", 0) < len(lists):
            _, where = lists[state.get("li", 0)]
            page = state.get("page", 1)
            books, rows = self._page(where, page, POPULAR)
            if books:
                yield books
            if rows < PER_PAGE or page >= pages:
                state.update(li=state.get("li", 0) + 1, page=1)
            else:
                state["page"] = page + 1
        state.update(full_done=True, li=0, page=1)

    def details(self, book: dict) -> BookInfo:
        raise NotImplementedError  # the lists already have everything
