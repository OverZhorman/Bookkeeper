"""LitMir (litmir.club): a big library (about 860,000 books), published books and self-published (СИ) ones.

Catalog: the site-wide book list, most popular first, 30 books per page; each card has the title, authors, every
genre, rating and votes, language, page count and whether the book is finished.
Text: the online reader (/br/?b=ID&p=N). For a download every reader page is read and the book is split at its
own chapter headings."""
import html as _html
import re

from ..analysis.text import clean_text, html_to_text, opening_pieces
from ..http import NotFound
from .base import BookInfo, Chapter, Site, looks_adult

BASE = "https://litmir.club"
LANGS = {"русский": "ru", "английский": "en", "украинский": "uk"}


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


def _box(card: str, name: str) -> str:
    m = re.search(r'<span class="desc1"[^>]*>' + re.escape(name) + r':</span>\s*<span[^>]*class="desc2"[^>]*>(.*?)</span>\s*(?:<span class="desc1"|</div>)', card, re.S)
    return m.group(1) if m else ""


class LitMir(Site):
    id = "litmir"
    name = "LitMir"
    home = BASE
    lang = "ru"
    min_interval = 2.0
    note = "A big library of published and self-published books (about 860,000), most popular first."
    extra_settings = {"pages": {"label": "Catalog pages to read (30 books each, most popular first)", "default": "1000"}}

    # ----- catalog
    def _card(self, card: str) -> BookInfo | None:
        link = re.search(r'<div class="book_name"><a href="/bd/\?b=(\d+)"><span itemprop="name">(.*?)</span>', card, re.S)
        if not link:
            return None
        bid = link.group(1)
        rating = re.search(r'class="orange_desc">([\d.]+)</span>&nbsp;\((\d+)\)', card)
        cover = re.search(r'data-src="(/data/Book/[^"]+)"', card)
        authors = [_text(a) for a in re.findall(r'<a href="/a/\?id=\d+">(.*?)</a>', _box(card, "Автор"), re.S)]
        genres = [_text(g) for g in re.findall(r'<a href="/bs/\?g=sg\d+[^"]*">(.*?)</a>', card, re.S)]
        lang = _text(re.sub(r"<span.*", "", _box(card, "Язык книги"), flags=re.S)).lower()
        pages = re.search(r"Страниц:</span>\s*<span[^>]*>\s*(\d+)", card)
        finished = "Книга закончена" in card
        votes = int(rating.group(2)) if rating else None
        title = _text(link.group(2))
        return BookInfo(
            sid=bid, url=f"{BASE}/bd/?b={bid}", title=title or f"#{bid}", authors=authors,
            cover=BASE + cover.group(1) if cover else None, lang=LANGS.get(lang, lang or None),
            status="completed" if finished else "ongoing" if "Книга не закончена" in card else "unknown",
            rating=float(rating.group(1)) if rating else None, votes=votes, pop_raw=votes,
            words=int(pages.group(1)) * 280 if pages else None, access="free",
            adult=looks_adult(genres), tags=list(dict.fromkeys(g for g in genres if g)), complete=True,
            extra={"pages": int(pages.group(1)) if pages else None, "self_published": "(СИ)" in title},
        )

    def _list(self, page: int) -> list[BookInfo]:
        try:
            p = self.http.get(f"{BASE}/bs/", params={"rs": "5|1|0", "p": page})
        except NotFound:
            return []
        cards = re.split(r'<table itemscope="" itemtype="http://schema.org/Book"', p.text)[1:]
        return [b for b in (self._card(c) for c in cards) if b]

    def discover(self, state: dict):
        if state.get("full_done"):
            for page in range(1, 6):
                books = self._list(page)
                if not books:
                    break
                yield books
            return
        limit = int(re.sub(r"\D", "", str(self.settings.get("pages") or "1000")) or 1000)
        page = state.get("page", 1)
        while page <= limit:
            books = self._list(page)
            if not books:
                break
            yield books
            page += 1
            state["page"] = page
        state.update(full_done=True, page=1)

    def details(self, book: dict) -> BookInfo:
        raise NotImplementedError  # the catalog card has everything we use

    # ----- the reader
    def _reader(self, sid: str, page: int) -> tuple[str, int]:
        """(HTML of one reader page's text, number of reader pages)."""
        try:
            s = self.http.get(f"{BASE}/br/", params={"b": sid, "p": page}).text
        except NotFound:
            return "", 0
        start = s.find('class="page_text"')
        if start < 0:
            return "", 0
        end = s.find('<div class="BookText"', start)
        pages = [int(x) for x in re.findall(r'href="/br/\?b=' + re.escape(sid) + r'&(?:amp;)?p=(\d+)"', s)]
        return s[s.find(">", start) + 1: end if end > 0 else None], max(pages + [page])

    def chapters(self, book: dict) -> list[Chapter]:
        first, total = self._reader(book["sid"], 1)
        parts = [first]
        for n in range(2, total + 1):
            parts.append(self._reader(book["sid"], n)[0])
            if self.progress:
                self.progress(n)
        # Split at the book's own headings (FB2 section titles); the first one is the book's title.
        pieces = re.split(r'<a name="section_\d+" class="fb2-title[^"]*"[^>]*>', "".join(parts))
        chapters, self._parts = [], {}
        for piece in pieces:
            head = re.match(r"\s*(.*?)</a>", piece, re.S)
            title = _text(head.group(1)) if head else ""
            body = html_to_text(piece[head.end():] if head else piece)
            if len(body.split()) < 30:
                continue
            cid = str(len(chapters))
            self._parts[cid] = body
            chapters.append(Chapter(id=cid, title=title or f"Часть {len(chapters) + 1}", index=len(chapters)))
        return chapters

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        if not getattr(self, "_parts", None) or chapter.id not in self._parts:
            self.chapters(book)
        return self._parts.get(chapter.id, "")

    def opening_text(self, book: dict, max_chapters: int = 3, enough_words: int = 6000) -> list[str]:
        html, total = self._reader(book["sid"], 1)
        text = html_to_text(html)
        n = 2
        while len(text.split()) < enough_words + 500 and n <= min(total, 4):
            text += "\n" + html_to_text(self._reader(book["sid"], n)[0])
            n += 1
        return opening_pieces(text, enough_words, max_chapters)
