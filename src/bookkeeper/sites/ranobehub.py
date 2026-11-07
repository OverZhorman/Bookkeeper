"""RanobeHub (ranobehub.org): Russian translations of Japanese, Chinese and Korean web novels and light novels.

The site is built with Next.js: each page carries its data as a JSON stream (the page's "flight" data), which we read.
Catalog: /ranobe?page=N, 24 books per page, most recently updated first (genres, status, rating, views, chapters).
Details: the book page (authors, country, every tag, length, the chapter list).
Chapter text: the chapter page. For long books the book page lists only some chapters, so during a download the
rest are found by following each chapter's "next chapter" link (each of those pages is the chapter we need anyway)."""
import html as _html
import json
import re
import urllib.parse

from ..analysis.text import clean_text, html_to_text
from ..http import NotFound
from .base import BookInfo, Chapter, Site, SiteError, looks_adult

BASE = "https://ranobehub.org"
_PUSH = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
STATUS = {"В процессе": "ongoing", "Завершено": "completed", "Заморожено": "frozen", "Брошено": "frozen",
          "Анонс": "ongoing", "Приостановлено": "frozen"}
ORIGIN = {"Япония": "jp", "Китай": "cn", "Корея": "kr", "Южная Корея": "kr", "США": "en", "Англия": "en",
          "Великобритания": "en", "Канада": "en", "Австралия": "en", "Тайвань": "cn", "Россия": "ru"}
_NEIGHBOURS = re.compile(r'"previous":(null|\{[^{}]*\}),"next":(null|\{[^{}]*\})')


def flight(page_html: str) -> str:
    """The page's own data stream, as one string."""
    return "".join(json.loads(m.group(1)) for m in _PUSH.finditer(page_html))


def json_after(text: str, key: str, start: int = 0):
    i = text.find(key, start)
    if i < 0:
        return None
    try:
        return json.JSONDecoder().raw_decode(text, i + len(key))[0]
    except ValueError:
        return None


def _date(value) -> str | None:
    s = str(value or "").lstrip("$D")
    return s[:10] or None


def _num(value) -> int | None:
    try:
        return int(float(value)) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


class RanobeHub(Site):
    id = "ranobehub"
    name = "RanobeHub"
    home = BASE
    lang = "ru"
    min_interval = 1.5
    note = ("Russian translations of Japanese, Chinese and Korean novels. For long books the chapter list is "
            "completed during a download, by following each chapter's link to the next one.")

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._cache: dict[str, str] = {}      # chapter id -> text, filled while walking a long book

    # ----- catalog
    def _info(self, it: dict) -> BookInfo:
        bid = str(it["id"])
        tags = [t for t in it.get("tags") or [] if isinstance(t, str) and t]
        poster = it.get("posterUrl")
        return BookInfo(
            sid=bid, url=f"{BASE}/ranobe/{bid}-{urllib.parse.quote(it.get('slug') or '')}".rstrip("-"),
            title=(it.get("title") or "").strip() or f"#{bid}",
            alt_titles=[it["originalTitle"]] if it.get("originalTitle") else [],
            description=clean_text(it.get("description") or "") or it.get("shortDescription") or None,
            cover=BASE + poster if poster and poster.startswith("/") else poster, lang="ru",
            status=STATUS.get(it.get("status"), "unknown"), is_translation=not it.get("isOriginalWork"),
            chapters=_num(it.get("chapters")), rating=float(it["rating"]) if it.get("rating") else None,
            votes=_num(it.get("votes")) or None, views=_num(it.get("views")), pop_raw=_num(it.get("views")),
            created_at=str(it["year"]) if it.get("year") else None, updated_at=_date(it.get("updatedAt")),
            adult=looks_adult(tags), tags=tags, partial_tags=True,
            extra={"slug": it.get("slug"), "volumes": it.get("volumes")},
        )

    def _catalog(self, page: int) -> tuple[list[BookInfo], int]:
        p = self.http.get(f"{BASE}/ranobe", params={"page": page})
        f = flight(p.text)
        data = json_after(f, '"result":')
        if not isinstance(data, dict) or "items" not in data:
            raise SiteError("the catalog page has no book list (layout changed?)")
        return [self._info(it) for it in data["items"] if isinstance(it, dict) and it.get("id")], int(data.get("pages") or 0)

    def discover(self, state: dict):
        if state.get("full_done"):
            for page in range(1, 6):  # later passes: the most recently updated books again
                books, _ = self._catalog(page)
                if not books:
                    break
                yield books
            return
        page = state.get("page", 1)
        while True:
            books, pages = self._catalog(page)
            if not books or (pages and page > pages):
                state.update(full_done=True, page=1)
                return
            yield books
            page += 1
            state["page"] = page

    # ----- book page
    def _book_page(self, sid: str) -> tuple[str, str]:
        p = self.http.get(f"{BASE}/ranobe/{sid}")
        return p.text, flight(p.text)

    def details(self, book: dict) -> BookInfo:
        page, f = self._book_page(book["sid"])
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
        if not h1:
            raise SiteError("unexpected page layout (no title)")
        info = BookInfo(sid=book["sid"], url=f"{BASE}/ranobe/{book['sid']}", title=_text(h1.group(1)), lang="ru",
                        is_translation=True)
        orig = re.search(r'<p class="book-original-title">(.*?)</p>', page, re.S)
        if orig:
            info.alt_titles = [_text(orig.group(1))]
        info.authors = [_text(a) for a in re.findall(
            r'class="book-credit-chip is-author"[^>]*>.*?<strong[^>]*>(.*?)</strong>', page, re.S)]
        translators = [_text(a) for a in re.findall(
            r'class="book-credit-chip is-translator"[^>]*>.*?<strong[^>]*>(.*?)</strong>', page, re.S)]
        country = re.search(r'href="/country/\d+"[^>]*>(.*?)</a>', page, re.S)
        country_name = re.sub(r"[^\w\s-]", "", _text(country.group(1))).strip() if country else ""
        info.origin = ORIGIN.get(country_name)
        if info.origin == "ru":
            info.is_translation, info.origin = False, None
        tax_start = page.find('class="book-hero-taxonomy"')
        tax_end = page.find('id="book-description"', tax_start)
        taxonomy = page[tax_start:tax_end] if tax_start >= 0 else ""
        labels = [_text(x) for x in re.findall(r'href="/tag/\d+"[^>]*>(.*?)</a>', taxonomy, re.S)]
        info.tags = list(dict.fromkeys(x for x in labels if x))
        info.adult = looks_adult(info.tags)
        symbols = re.search(r'"symbols":(\d+)', f)
        if symbols:
            info.words = int(int(symbols.group(1)) / 7.2)
        count = re.search(r'aria-label="(\d+) глав', page)
        info.chapters = int(count.group(1)) if count else None
        # (the description is left alone: the catalog's is the full one, the book page shows a short summary)
        listed, complete = self._listed_chapters(f)
        info.extra = {"translators": translators, "country": country_name or None, "toc_complete": complete,
                      "toc": [[c.id, c.title] for c in listed[:8]]}
        return info

    def _listed_chapters(self, f: str) -> tuple[list[Chapter], bool]:
        """The chapters the book page lists, and whether that's all of them."""
        vols = json_after(f, '"volumes":')
        if not isinstance(vols, list):
            return [], False
        many_volumes = len(vols) > 1
        out, complete = [], True
        for v in vols:
            if not isinstance(v, dict):
                complete = False
                continue
            chapters = [c for c in v.get("chapters") or [] if isinstance(c, dict)]
            if len(chapters) < (v.get("chapterCount") or 0) or len(chapters) != len(v.get("chapters") or []):
                complete = False
            for c in chapters:
                out.append(self._chapter(c, many_volumes, len(out)))
        return out, complete

    @staticmethod
    def _chapter(c: dict, many_volumes: bool, index: int) -> Chapter:
        title = (c.get("title") or "").strip() or f"Глава {c.get('number')}"
        if many_volumes and c.get("volume"):
            title = f"Том {c['volume']}. {title}"
        return Chapter(id=str(c["id"]), title=title, index=index, free=not c.get("scheduledFor"),
                       extra={"volume": c.get("volume"), "number": c.get("number")})

    def chapters(self, book: dict) -> list[Chapter]:
        _, f = self._book_page(book["sid"])
        listed, complete = self._listed_chapters(f)
        if complete or not listed:
            return listed
        # Long book: walk the reader from the first chapter, keeping each chapter's text for the download
        # (so no page is fetched twice).
        vols = json_after(f, '"volumes":') or []
        many_volumes = len(vols) > 1
        titles = {c.id: c.title for c in listed}
        out, seen = [], set()
        cid = listed[0].id
        while cid and cid not in seen and len(out) < 20000:
            seen.add(cid)
            text, nxt = self._read(book["sid"], cid)
            self._cache[cid] = text
            out.append(Chapter(id=cid, title=titles.get(cid) or f"Глава {len(out) + 1}", index=len(out)))
            if self.progress:
                self.progress(len(out))
            if not nxt or not nxt.get("id"):
                break
            cid = str(nxt["id"])
            titles.setdefault(cid, self._chapter(nxt, many_volumes, 0).title)
        return out

    # ----- chapter text
    def _read(self, sid: str, cid: str) -> tuple[str, dict | None]:
        try:
            p = self.http.get(f"{BASE}/ranobe/{sid}/chapter/{cid}")
        except NotFound:
            return "", None
        page = p.text
        start = page.find(f'id="reader-content-{cid}"')
        if start < 0:
            start = page.find('class="reader-content"')
        text = ""
        if start >= 0:
            end = page.find('class="chapter-engagement"', start)
            end = page.rfind("<", start, end) if end > 0 else -1
            body = page[page.find(">", start) + 1: end if end > 0 else None]
            body = re.sub(r"(?is)<aside\b.*?</aside>", " ", body)
            text = html_to_text(body)
        m = _NEIGHBOURS.search(flight(page))
        nxt = json.loads(m.group(2)) if m and m.group(2) != "null" else None
        return text, nxt

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        if chapter.id in self._cache:
            return self._cache.pop(chapter.id)
        return self._read(book["sid"], chapter.id)[0]

    def opening_text(self, book: dict, max_chapters: int = 3, enough_words: int = 6000) -> list[str]:
        toc = (book.get("extra") or {}).get("toc")
        if toc:
            chapters = [Chapter(id=str(cid), title=t, index=i) for i, (cid, t) in enumerate(toc)]
        else:
            _, f = self._book_page(book["sid"])
            chapters = self._listed_chapters(f)[0]
        out, words = [], 0
        for ch in chapters[:max_chapters + 3]:
            text = self.chapter_text(book, ch)
            if not text.strip():
                continue
            out.append(text)
            words += len(text.split())
            if len(out) >= max_chapters or words >= enough_words:
                break
        return out
