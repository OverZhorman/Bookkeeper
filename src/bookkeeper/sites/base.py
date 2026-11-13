"""What every site connector looks like."""
import re
from dataclasses import dataclass, field
from typing import Iterator
from urllib.parse import urlparse

from ..http import Http


@dataclass
class BookInfo:
    sid: str                                  # the book's id on its site
    url: str
    title: str
    alt_titles: list[str] = field(default_factory=list)
    authors: list[str] = field(default_factory=list)
    description: str | None = None
    cover: str | None = None
    lang: str | None = None                   # ru / en / uk
    status: str | None = None                 # ongoing / completed / frozen / unknown
    is_translation: bool | None = None
    origin: str | None = None
    chapters: int | None = None
    words: int | None = None
    rating: float | None = None               # 0..10
    votes: int | None = None
    views: int | None = None
    likes: int | None = None
    pop_raw: float | None = None              # whatever this site counts popularity by
    adult: bool = False
    age_rating: str | None = None             # G / PG-13 / R / NC-17 / NC-21, when the site gives one
    access: str | None = None                 # free / partial / paid
    created_at: str | None = None
    updated_at: str | None = None
    tags: list[str] | None = None             # labels as written on the site (genres, tags, fandoms...)
    partial_tags: bool = False                # True: a listing page's short tag list; never replaces full tags
    add_tags: bool = False                    # True: just more labels for a book already listed (others stay)
    extra: dict = field(default_factory=dict)
    complete: bool = False                    # True: nothing more to fetch for the details step


@dataclass
class Chapter:
    id: str
    title: str
    index: int
    free: bool = True
    extra: dict = field(default_factory=dict)


class SiteError(Exception):
    """Something site-specific went wrong (changed layout, missing data...)."""


class TemporaryError(Exception):
    """A hiccup worth retrying later (a timeout, a slow page...)."""


ADULT_LABELS = re.compile(r"(?i)^(18\+|21\+|nc-17|nc-21|r-18|r18|adult|smut|hentai|смут|эротик|хентай|"
                          r"для взрослых|откровенные сцены|порн)")


def looks_adult(labels) -> bool:
    """True if a site's genres / tags / age label mark the book as 18+ (or 21+)."""
    return any(ADULT_LABELS.search((x or "").strip()) for x in labels or [])


def origin_from_title(original_title: str) -> str | None:
    """A translated book's original language (kr / jp / cn), from the script of its original title."""
    if re.search(r"[가-힣]", original_title or ""):
        return "kr"
    if re.search(r"[぀-ヿ]", original_title or ""):
        return "jp"
    if re.search(r"[一-鿿]", original_title or ""):
        return "cn"
    return None


class Site:
    id = ""
    name = ""
    home = ""
    lang = "ru"
    min_interval = 1.0                        # seconds between requests
    needs_browser_for_text = False            # chapter text is only readable in a real browser
    note = ""                                 # shown on the Sites page
    native_formats: tuple[str, ...] = ()      # formats the site can give us directly (fb2, epub...)
    lists_adult = False                       # the catalog marks 18+ books, so they used to be skipped there
    # Read the catalog once more from the start in 0.4, for the age ratings it lists (older versions didn't keep them).
    age_rescan = False
    # Raised when a connector changes how it walks its site: its listing then starts again, once (crawler.py).
    state_version = 0
    # Set by discover(): True while a batch comes from a downloaded file (the crawler then takes several batches at
    # once), and what to show on the Sites page meanwhile.
    batch_offline = False
    discover_activity: str | None = None
    # A huge, slow site: its first full listing gets all the requests (details and narration checks wait for it),
    # and afterwards the newest books come first for those.
    listing_first = False
    newest_first = False
    has_text = True                           # False: catalog only (no narration check, no downloads)
    # Browser extensions (in your own Waterfox) that can download this site's books, e.g. ExLoader.
    extension_downloads: tuple[str, ...] = ()

    # ----- accounts (see accounts.py). No login_url = no account support.
    login_url = ""
    login_benefit = ""                        # what logging in gives you, shown on the Sites page
    login_autofill = True                     # Bookkeeper can fill in a saved login and password
    login_import = True                       # the login lives in cookies, so it can be copied from your Waterfox
    login_form: dict = {}                     # optional CSS selectors: user, password, submit
    # JavaScript that is true on a page once you're logged in.
    logged_in_js = ("!/(log-?in|sign-?in|auth|вход)/i.test(location.pathname) && "
                    "![...document.querySelectorAll('input[type=password]')].some(e => e.offsetParent !== null)")
    token_js = ""                             # JavaScript returning an access token to keep (RanobeLib)
    user_js = ""                              # JavaScript returning your user name on the site
    session_token = None                      # set by accounts.apply()

    def __init__(self, http: Http, settings: dict | None = None, browser=None):
        self.http = http
        self.settings = settings or {}
        self.browser = browser
        self.progress = None                  # optional callback(n) while a slow chapter list is being built

    @classmethod
    def cookie_domains(cls) -> tuple[str, ...]:
        host = urlparse(cls.home).hostname or ""
        return (host[4:] if host.startswith("www.") else host,)

    # Is the saved session still logged in? True / False, or None when this site can't tell cheaply.
    def check_login(self) -> bool | None:
        return None

    # Walk the catalog. `state` is a dict you may update to resume later; yield batches of books.
    def discover(self, state: dict) -> Iterator[list[BookInfo]]:
        raise NotImplementedError

    # Full details for one book (tags, description, chapter count...).
    def details(self, book: dict) -> BookInfo:
        raise NotImplementedError

    # The book's chapter list in reading order.
    def chapters(self, book: dict) -> list[Chapter]:
        raise NotImplementedError

    # Plain text of one chapter, paragraphs separated by newlines.
    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        raise NotImplementedError

    # Opening text for narration analysis. Default: the first few free chapters.
    def opening_text(self, book: dict, max_chapters: int = 3, enough_words: int = 6000) -> list[str]:
        out, words = [], 0
        for ch in self.chapters(book):
            if not ch.free:
                continue
            text = self.chapter_text(book, ch)
            if not text.strip():
                continue
            out.append(text)
            words += len(text.split())
            if len(out) >= max_chapters or words >= enough_words:
                break
        return out

    # A ready-made file from the site (Flibusta gives fb2/epub). Returns (bytes, filename) or None.
    def native_download(self, book: dict, fmt: str):
        return None
