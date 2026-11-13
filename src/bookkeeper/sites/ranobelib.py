"""RanobeLIB (ranobelib.me): Russian translations of Asian and English web novels, plus original works.

The site's pages are built from its own JSON data feed (api.lib.social), which we read directly."""
import urllib.parse

from ..analysis.text import clean_text, html_to_text
from ..http import Blocked, NotFound
from .base import BookInfo, Chapter, Site

API_HOSTS = ["https://api.lib.social/api", "https://api.cdnlibs.org/api"]
SITE_ID = "3"  # 1 = MangaLib, 3 = RanobeLIB on the shared backend

STATUS = {"Онгоинг": "ongoing", "Завершён": "completed", "Анонс": "ongoing", "Приостановлен": "frozen",
          "Выпуск прекращён": "frozen"}
ORIGIN = {"Япония": ("jp", True), "Корея": ("kr", True), "Китай": ("cn", True), "Английский": ("en", True),
          "Авторский": (None, False), "Фанфик": (None, False)}
DETAIL_FIELDS = ["summary", "genres", "tags", "authors", "otherNames", "chap_count", "format", "publisher",
                 "teams", "releaseDate"]


def _doc_text(node, out: list):
    """Text from the editor's JSON document format (the site stores descriptions and chapters this way)."""
    if isinstance(node, list):
        for x in node:
            _doc_text(x, out)
    elif isinstance(node, dict):
        if node.get("type") == "text":
            out.append(node.get("text", ""))
        if "content" in node:
            _doc_text(node["content"], out)
        if node.get("type") in ("paragraph", "heading", "hardBreak", "horizontalRule"):
            out.append("\n")


def rich_text(value) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return html_to_text(value) if "<" in value else clean_text(value)
    out: list[str] = []
    _doc_text(value, out)
    return clean_text("".join(out))


class RanobeLib(Site):
    id = "ranobelib"
    name = "RanobeLIB"
    home = "https://ranobelib.me"
    lang = "ru"
    min_interval = 2.5  # the site blocked faster reading (DDoS-Guard, 2026-11)
    note = "Reads the site's own data feed. The site shows some 18+ titles only to logged-in readers."
    lists_adult = True
    age_rescan = True
    # The site logs you in through a pop-up from its own login service, so Bookkeeper can't fill in a password
    # for you: press "Log in…" and log in in the window that opens.
    login_url = "https://ranobelib.me/ru"
    login_benefit = "18+ titles that the site shows only to logged-in readers. In the window, press «Войти»."
    login_autofill = False
    login_import = False  # the login is kept in the browser's storage, not in cookies
    _AUTH = "(() => { try { return JSON.parse(localStorage.getItem('auth') || '{}') } catch (e) { return {} } })()"
    logged_in_js = f"!!(({_AUTH}).token || {{}}).access_token"
    token_js = f"(({_AUTH}).token || {{}}).access_token || null"
    user_js = f"(({_AUTH}).auth || {{}}).username || null"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.api = self.settings.get("api") or API_HOSTS[0]

    @classmethod
    def cookie_domains(cls) -> tuple[str, ...]:
        return ("ranobelib.me", "lib.social", "cdnlibs.org")

    def check_login(self) -> bool | None:
        if not self.session_token:
            return False
        p = self.http.get(self.api + "/auth/me", ok_status=(401, 403),
                          headers={"Site-Id": SITE_ID, "Accept": "application/json",
                                   "Authorization": f"Bearer {self.session_token}"})
        return p.status == 200

    def _get(self, path: str, params=None):
        hosts = [self.api] + [h for h in API_HOSTS if h != self.api]
        last = None
        headers = {"Site-Id": SITE_ID, "Accept": "application/json", "Referer": self.home + "/"}
        if self.session_token:
            headers["Authorization"] = f"Bearer {self.session_token}"
        for host in hosts:
            try:
                data = self.http.get_json(host + path, params=params, headers=headers)
                self.api = host
                return data
            except Blocked as e:  # try the other address of the same data feed
                last = e
        raise last

    def _info_from(self, b: dict) -> BookInfo:
        slug = b.get("slug_url") or f"{b['id']}--{b.get('slug', '')}"
        rating = b.get("rating") or {}
        votes = int(rating.get("votes") or 0) or None
        type_label = (b.get("type") or {}).get("label")
        origin, translated = ORIGIN.get(type_label, (None, None))
        age = (b.get("ageRestriction") or {}).get("label") or ""
        cover = b.get("cover") or {}
        alt = [b.get("eng_name"), b.get("name"), *(b.get("otherNames") or [])]
        return BookInfo(
            sid=slug,
            url=f"{self.home}/ru/book/{slug}",
            title=b.get("rus_name") or b.get("name") or slug,
            alt_titles=[x for x in alt if x],
            cover=cover.get("md") or cover.get("default") or cover.get("thumbnail"),
            lang="ru",
            status=STATUS.get((b.get("status") or {}).get("label"), "unknown"),
            is_translation=translated,
            origin=origin,
            rating=float(rating["average"]) if rating.get("average") else None,
            votes=votes,
            pop_raw=votes,
            adult=age.startswith("18"), age_rating=age or None,
            created_at=(b.get("releaseDateString") or "").replace(" г.", "") or None,
            extra={"type": type_label},
        )

    # The whole catalog, oldest first (a stable order, so paging never skips anything); afterwards
    # each pass re-reads the most recently updated titles.
    def discover(self, state: dict):
        mode = state.get("mode", "full")
        page = state.get("page", 1)
        while True:
            if mode == "full":
                params = {"site_id[]": SITE_ID, "page": page, "sort_by": "created_at", "sort_type": "asc"}
            else:
                params = {"site_id[]": SITE_ID, "page": page, "sort_by": "last_chapter_at", "sort_type": "desc"}
            data = self._get("/manga", params=params)
            items = data.get("data") or []
            if items:
                yield [self._info_from(b) for b in items]
            has_next = (data.get("meta") or {}).get("has_next_page")
            if mode == "full":
                if not items or not has_next:
                    state.update(mode="updates", page=1, full_done=True)
                    return
                page += 1
                state["page"] = page
            else:
                page += 1
                if not items or not has_next or page > 5:  # the newest 300 titles per pass
                    state.update(page=1)
                    return
                state["page"] = page

    def details(self, book: dict) -> BookInfo:
        slug = book["sid"]
        params = [("fields[]", f) for f in DETAIL_FIELDS]
        data = self._get(f"/manga/{urllib.parse.quote(slug)}", params=params)
        b = data.get("data") or {}
        if not b:
            raise NotFound(slug)
        info = self._info_from(b)
        info.authors = [a.get("name") for a in b.get("authors") or [] if a.get("name")]
        info.description = rich_text(b.get("summary"))
        count = b.get("items_count") or {}
        info.chapters = count.get("uploaded") if isinstance(count, dict) else count
        labels = [g.get("name") for g in b.get("genres") or []] + [t.get("name") for t in b.get("tags") or []]
        if info.extra.get("type"):
            labels.append(info.extra["type"])
        labels += [f.get("name") for f in b.get("format") or [] if isinstance(f, dict)]
        info.tags = [x for x in labels if x]
        return info

    def chapters(self, book: dict) -> list[Chapter]:
        data = self._get(f"/manga/{urllib.parse.quote(book['sid'])}/chapters")
        out = []
        for i, ch in enumerate(data.get("data") or []):
            branches = ch.get("branches") or []
            branch = branches[0].get("branch_id") if branches else None
            name = ch.get("name") or ""
            title = f"Том {ch.get('volume')} Глава {ch.get('number')}" + (f" — {name}" if name else "")
            out.append(Chapter(id=str(ch.get("id")), title=title, index=i,
                               extra={"number": ch.get("number"), "volume": ch.get("volume"), "branch": branch}))
        return out

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        params = {"number": chapter.extra["number"], "volume": chapter.extra["volume"]}
        if chapter.extra.get("branch"):
            params["branch_id"] = chapter.extra["branch"]
        try:
            data = self._get(f"/manga/{urllib.parse.quote(book['sid'])}/chapter", params=params)
        except NotFound:
            return ""
        return rich_text((data.get("data") or {}).get("content"))
