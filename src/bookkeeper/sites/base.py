"""What every site connector looks like."""
from dataclasses import dataclass, field
from typing import Iterator

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
    access: str | None = None                 # free / partial / paid
    created_at: str | None = None
    updated_at: str | None = None
    tags: list[str] | None = None             # labels as written on the site (genres, tags, fandoms...)
    partial_tags: bool = False                # True: a listing page's short tag list; never replaces full tags
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


class Site:
    id = ""
    name = ""
    home = ""
    lang = "ru"
    min_interval = 1.0                        # seconds between requests
    needs_browser_for_text = False            # chapter text is only readable in a real browser
    note = ""                                 # shown on the Sites page
    native_formats: tuple[str, ...] = ()      # formats the site can give us directly (fb2, epub...)

    def __init__(self, http: Http, settings: dict | None = None, browser=None):
        self.http = http
        self.settings = settings or {}
        self.browser = browser

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
