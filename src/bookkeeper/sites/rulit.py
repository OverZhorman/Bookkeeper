"""RuLit (rulit.me): a big library (over a million books), published and self-published.

Catalog: the site-wide list, most popular first, 10 books per page (genre, title, author, rating, language, year,
status). Details: the book page (all genres, series, rating votes, annotation).
Text: the online reader, one short page at a time. For a download every reader page is read and the book is split
at its own section headings."""
import html as _html
import re

from ..analysis.text import clean_text, html_to_text, opening_pieces
from ..http import NotFound
from .base import BookInfo, Chapter, Site, SiteError, looks_adult

BASE = "https://www.rulit.me"
LANGS = {"русский": "ru", "английский": "en", "украинский": "uk"}
_CARD_LINK = re.compile(r'<a href="https://www\.rulit\.me/books/([a-z0-9-]+)-download-(\d+)\.html"[^>]*>(.{1,400}?)</a>', re.S)
_SECTION = re.compile(r'<span class="title" id="section_\d+"></span>\s*(?:<div class="title">(.*?)</div>)?', re.S)


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


def _status(text: str) -> str:
    t = text.lower()
    if "не закончена" in t:
        return "frozen" if "не будет" in t else "ongoing"
    return "completed" if "закончена" in t else "unknown"


class RuLit(Site):
    id = "rulit"
    name = "RuLit"
    home = BASE
    lang = "ru"
    min_interval = 2.0
    note = "A big library of published and self-published books (over a million), most popular first."
    extra_settings = {"pages": {"label": "Catalog pages to read (10 books each, most popular first)", "default": "3000"}}

    # ----- catalog
    def _list(self, page: int) -> list[BookInfo]:
        try:
            s = self.http.get(f"{BASE}/books/all/{page}/popular").text
        except NotFound:
            return []
        out, seen = [], set()
        for m in _CARD_LINK.finditer(s):
            slug, bid, title = m.group(1), m.group(2), _text(m.group(3))
            if bid in seen or not title:
                continue  # the cover link before the title link has no text
            seen.add(bid)
            prev = s[max(0, m.start() - 1200):m.start()]
            card = s[m.start(): m.start() + 1500]
            genre = re.findall(r'class="post-cat">([^<]+)</a>', prev)
            author = re.search(r'Автор:\s*<a href="https://www\.rulit\.me/authors?/[^"]+">([^<]+)</a>', card)
            rating = re.search(r"Рейтинг:\s*([\d.]+)", _text(card))
            lang = re.search(r"Язык:\s*(\w+)", _text(card))
            year = re.search(r"Год:\s*(\d{4})", _text(card))
            status = re.search(r"Статус:\s*([^\n<]{3,40}?)(?:\s+Жанр|\s+Добавил|\s*$|\n)", _text(card))
            labels = [_text(g) for g in genre[-1:]]
            out.append(BookInfo(
                sid=f"{slug}-{bid}", url=f"{BASE}/books/{slug}-download-{bid}.html", title=title or bid,
                authors=[_text(author.group(1))] if author else [], lang=LANGS.get((lang.group(1) if lang else "").lower()),
                rating=round(float(rating.group(1)) * 2, 2) if rating and float(rating.group(1)) else None,
                created_at=year.group(1) if year else None, status=_status(status.group(1) if status else ""),
                access="free", tags=labels, partial_tags=True, adult=looks_adult(labels),
                pop_raw=1_000_000_000 - (page - 1) * 10 - len(out),
                extra={"slug": slug, "id": bid},
            ))
        return out

    def discover(self, state: dict):
        if state.get("full_done"):
            for page in range(1, 6):
                books = self._list(page)
                if not books:
                    break
                yield books
            return
        limit = int(re.sub(r"\D", "", str(self.settings.get("pages") or "3000")) or 3000)
        page = state.get("page", 1)
        while page <= limit:
            books = self._list(page)
            if not books:
                break
            yield books
            page += 1
            state["page"] = page
        state.update(full_done=True, page=1)

    @staticmethod
    def _ids(book: dict) -> tuple[str, str]:
        extra = book.get("extra") or {}
        if extra.get("slug") and extra.get("id"):
            return extra["slug"], extra["id"]
        slug, _, bid = book["sid"].rpartition("-")
        return slug, bid

    def details(self, book: dict) -> BookInfo:
        slug, bid = self._ids(book)
        s = self.http.get(f"{BASE}/books/{slug}-download-{bid}.html").text
        t = re.sub(r"\s+", " ", _text(re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", s)))
        head = re.search(r'<h2 style="margin-top: 10px;">(.*?)</h2>\s*<article class="single-blog">(.*?)</article>', s, re.S)
        if not head:
            raise SiteError("unexpected page layout (no title)")
        box = head.group(2)
        genres = [_text(g) for g in re.findall(r'<a href="https://www\.rulit\.me/genre/[^"]+"[^>]*class="post-cat"[^>]*>(.*?)</a>', box, re.S)]
        rating = re.search(r"Рейтинг:\s*([\d.]+)\s*/5\s*\(Всего голосов:\s*(\d+)\)", t)
        ann = re.search(r"Аннотация\s+(.+?)\s+(?:Скачать книгу|Читать онлайн|Отзывы|Комментарии|Похожие книги|Перейти)", t)
        series = re.search(r'<a href="https://www\.rulit\.me/series/[^"]+"[^>]*>(.*?)</a>', box, re.S)
        authors = list(dict.fromkeys(_text(a) for a in re.findall(
            r'<a href="https://www\.rulit\.me/authors?/[^"]+"[^>]*>(.*?)</a>', box, re.S)))
        info_text = _text(box)
        lang = re.search(r"Язык:\s*(\w+)", info_text)
        year = re.search(r"Год:\s*(\d{4})", info_text)
        status = re.search(r"Статус:\s*([^\n]{3,40})", info_text)
        info = BookInfo(sid=book["sid"], url=f"{BASE}/books/{slug}-download-{bid}.html",
                        title=_text(head.group(1)), authors=[a for a in authors if a][:4],
                        lang=LANGS.get((lang.group(1) if lang else "").lower()),
                        created_at=year.group(1) if year else None,
                        status=_status(status.group(1)) if status else None,
                        description=ann.group(1)[:3000] if ann else None,
                        votes=int(rating.group(2)) if rating else None, access="free",
                        extra={"series": _text(series.group(1)) if series else None, "slug": slug, "id": bid})
        if genres:
            info.tags = list(dict.fromkeys(g for g in genres if g))
            info.adult = looks_adult(info.tags)
        if rating and int(rating.group(2)):
            info.rating = round(float(rating.group(1)) * 2, 2)
        return info

    # ----- the reader
    def _reader(self, book: dict, page: int) -> tuple[str, int]:
        slug, bid = self._ids(book)
        try:
            s = self.http.get(f"{BASE}/books/{slug}-read-{bid}-{page}.html").text
        except NotFound:
            return "", 0
        start = s.find('<article class="single-blog page-content">')
        if start < 0:
            return "", 0
        end = s.find("</article>", start)
        pages = [int(x) for x in re.findall(r"-read-" + re.escape(bid) + r"-(\d+)\.html", s)]
        return s[start:end if end > 0 else None], max(pages + [page])

    def chapters(self, book: dict) -> list[Chapter]:
        first, total = self._reader(book, 1)
        parts = [first]
        for n in range(2, total + 1):
            parts.append(self._reader(book, n)[0])
            if self.progress:
                self.progress(n)
        html = "".join(parts)
        marks = list(_SECTION.finditer(html))
        chapters, self._parts = [], {}
        bounds = [(m.start(), m.end(), _text(m.group(1) or "")) for m in marks] or [(0, 0, "")]
        if bounds[0][0] > 0:
            bounds.insert(0, (0, 0, ""))
        for i, (_, body_start, title) in enumerate(bounds):
            body_end = bounds[i + 1][0] if i + 1 < len(bounds) else len(html)
            body = html_to_text(html[body_start:body_end])
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
        html, total = self._reader(book, 1)
        text, n = html_to_text(html), 2
        while len(text.split()) < enough_words + 300 and n <= min(total, 12):
            text += "\n" + html_to_text(self._reader(book, n)[0])
            n += 1
        return opening_pieces(text, enough_words, max_chapters)
