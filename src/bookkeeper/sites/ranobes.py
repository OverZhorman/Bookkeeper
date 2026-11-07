"""Ranobes (ranobes.com): Russian translations of Chinese, Korean and Japanese web novels.

Catalog: /ranobe/page/N/, most recently updated first (title, rating, genres, views).
Details: the book page (status, authors, translators, genres, NovelUpdates-style tags in Russian, year,
original language, rating).
Chapter list: /chapters/<id>/page/N/, 25 chapters per page, newest first; the page carries its list as JSON.
Chapter text: the chapter page."""
import html as _html
import json
import re

from ..analysis.text import clean_text, html_to_text
from ..http import NotFound
from .base import BookInfo, Chapter, Site, SiteError, looks_adult

BASE = "https://ranobes.com"
ORIGIN = {"китайский": "cn", "корейский": "kr", "японский": "jp", "английский": "en"}
_DATA = re.compile(r"window\.__DATA__\s*=\s*")


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


def _int(s: str | None) -> int | None:
    digits = re.sub(r"\D", "", s or "")
    return int(digits) if digits else None


def _status(original: str, translation: str) -> str:
    t, o = translation.lower(), original.lower()
    if any(x in t for x in ("заморож", "брошен", "приостанов")):
        return "frozen"
    if ("заверш" in t or "complete" in t) and ("заверш" in o or "complete" in o or "end" in o):
        return "completed"
    return "ongoing" if (t or o) else "unknown"


class Ranobes(Site):
    id = "ranobes"
    name = "Ranobes"
    home = BASE
    lang = "ru"
    min_interval = 1.5
    note = "Russian translations of Asian novels, with NovelUpdates-style tags (in Russian)."

    # ----- catalog
    def _card(self, block: str) -> BookInfo | None:
        link = re.search(r'<h2 class="title"><a href="(https://ranobes\.com/ranobe/(\d+)-[^"]+\.html)">(.*?)</a>',
                         block, re.S)
        if not link:
            return None
        url, bid, title = link.group(1), link.group(2), _text(link.group(3))
        rating = re.search(r"<strong>([\d.]+)</strong>", block)
        votes = re.search(r'id="vote-num-id-\d+"[^>]*>(\d+)<', block)
        cover = re.search(r"background-image: url\(([^)]+)\)", block)
        desc = re.search(r'<div class="short-desc">(.*?)</div>', block, re.S)
        genres = re.search(r'<div class="grey ellipses small">(.*?)</div>', block, re.S)
        views = re.search(r'class="meta_author" title="[^"]*?([\d\s ]+)"', block)
        labels = [g.strip() for g in _text(genres.group(1)).split(",")] if genres else []
        return BookInfo(
            sid=bid, url=url, title=title, lang="ru", is_translation=True,
            description=_text(desc.group(1)) or None if desc else None,
            cover=cover.group(1).strip("'\"") if cover else None,
            rating=round(float(rating.group(1)) * 2, 2) if rating else None,
            votes=int(votes.group(1)) if votes else None, views=_int(views.group(1)) if views else None,
            pop_raw=_int(views.group(1)) if views else None,
            tags=[x for x in labels if x], partial_tags=True, adult=looks_adult(labels), extra={"url": url},
        )

    def _catalog(self, page: int) -> list[BookInfo]:
        url = f"{BASE}/ranobe/" if page == 1 else f"{BASE}/ranobe/page/{page}/"
        try:
            p = self.http.get(url)
        except NotFound:
            return []
        blocks = p.text.split('<article class="block story shortstory')[1:]
        return [b for b in (self._card(x) for x in blocks) if b]

    def discover(self, state: dict):
        if state.get("full_done"):
            for page in range(1, 6):
                books = self._catalog(page)
                if not books:
                    break
                yield books
            return
        page = state.get("page", 1)
        while True:
            books = self._catalog(page)
            if not books:
                state.update(full_done=True, page=1)
                return
            yield books
            page += 1
            state["page"] = page

    # ----- details
    def _book_url(self, book: dict) -> str:
        return (book.get("extra") or {}).get("url") or f"{BASE}/ranobe/{book['sid']}-.html"

    def details(self, book: dict) -> BookInfo:
        p = self.http.get(self._book_url(book))
        s = p.text
        h1 = re.search(r'<h1 class="title">(.*?)</h1>', s, re.S)
        if not h1:
            raise SiteError("unexpected page layout (no title)")
        sub = re.search(r'<span class="subtitle">(.*?)</span>', h1.group(1), re.S)
        title = _text(re.sub(r"<span.*", "", h1.group(1), flags=re.S))
        alt = [x.strip() for x in _text(sub.group(1)).split("•") if x.strip()] if sub else []
        spec_m = re.search(r'<div class="r-fullstory-spec">(.*?)<div class="fs-tab-pane"', s, re.S)
        spec = {}
        for li in re.findall(r"<li[^>]*>(.*?)</li>", spec_m.group(1) if spec_m else "", re.S):
            text = _text(li)
            if ":" in text:
                k, v = text.split(":", 1)
                spec[k.strip().lower()] = (v.strip(), li)
        authors = [_text(a) for a in re.findall(r'href="https://ranobes\.com/tags/authors/[^"]*"[^>]*>(.*?)</a>',
                                                 spec.get("авторы", ("", ""))[1], re.S)]
        translators = [_text(a) for a in re.findall(r"<a[^>]*>(.*?)</a>", spec.get("переводчик", ("", ""))[1], re.S)]
        genre_box = re.search(r'id="mc-fs-genre"(.*?)</div>\s*</div>', s, re.S)
        genres = [_text(g) for g in re.findall(r'href="https://ranobes\.com/tags/genre/[^"]*"[^>]*>(.*?)</a>',
                                                genre_box.group(1) if genre_box else "", re.S)]
        keyw = s[s.find('id="mc-fs-keyw"'):] if 'id="mc-fs-keyw"' in s else ""
        tags = [_text(t) for t in re.findall(r'class="tv-chip__name"[^>]*>(.*?)</a>', keyw[:200000], re.S)]
        desc = re.search(r'class="moreless__full">(.*?)(?:<a [^>]*moreless__toggle|</div>)', s, re.S)
        cover = re.search(r'<meta property="og:image" content="([^"]+)"', s)
        rating = re.search(r'"ratingValue":\s*"([\d.]+)"', s)
        votes = re.search(r'"ratingCount":\s*"(\d+)"', s)
        lang = spec.get("язык оригинала", ("", ""))[0].lower()
        year = re.search(r"\d{4}", spec.get("год издания", ("", ""))[0])
        labels = list(dict.fromkeys(x for x in genres + tags if x))
        return BookInfo(
            sid=book["sid"], url=p.url, title=title, alt_titles=alt, authors=authors,
            description=html_to_text(desc.group(1)) if desc else None,
            cover=cover.group(1) if cover else None, lang="ru", is_translation=True,
            origin=ORIGIN.get(lang), status=_status(spec.get("статус оригинала", ("", ""))[0],
                                                     spec.get("перевод", ("", ""))[0]),
            chapters=_int(spec.get("переведено", ("", ""))[0]),
            rating=round(float(rating.group(1)) * 2, 2) if rating else None,
            votes=int(votes.group(1)) if votes else None,
            views=_int(spec.get("просмотров", ("", ""))[0]), pop_raw=_int(spec.get("просмотров", ("", ""))[0]),
            created_at=year.group(0) if year else None, tags=labels, adult=looks_adult(labels),
            extra={"url": p.url, "translators": translators},
        )

    # ----- chapters
    def _chapter_page(self, sid: str, page: int) -> dict:
        url = f"{BASE}/chapters/{sid}/" if page == 1 else f"{BASE}/chapters/{sid}/page/{page}/"
        s = self.http.get(url).text
        m = _DATA.search(s)
        if not m:
            raise SiteError("the chapter list has no data (layout changed?)")
        return json.JSONDecoder().raw_decode(s, m.end())[0]

    def _list(self, raw: list, start_index: int = 0) -> list[Chapter]:
        return [Chapter(id=str(c["id"]), title=(c.get("title") or "").strip() or f"Глава {i + 1}",
                        index=start_index + i, extra={"link": c.get("link")}) for i, c in enumerate(raw)]

    def chapters(self, book: dict) -> list[Chapter]:
        first = self._chapter_page(book["sid"], 1)
        raw = list(first.get("chapters") or [])
        for page in range(2, int(first.get("pages_count") or 1) + 1):
            raw += self._chapter_page(book["sid"], page).get("chapters") or []
            if self.progress:
                self.progress(len(raw))
        raw.reverse()  # the site lists newest first
        return self._list(raw)

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        url = chapter.extra.get("link") or f"{BASE}/chapters/{book['sid']}/{chapter.id}.html"
        try:
            s = self.http.get(url).text
        except NotFound:
            return ""
        start = s.find('id="arrticle"')
        if start < 0:
            return ""
        end = min([i for i in (s.find('class="category grey ellipses rd-foot-book"', start),
                               s.find('class="story_tools', start)) if i > 0] or [len(s)])
        end = s.rfind("<", start, end)
        return html_to_text(s[s.find(">", start) + 1:end])

    def opening_text(self, book: dict, max_chapters: int = 3, enough_words: int = 6000) -> list[str]:
        # The oldest chapters are on the last page of the list.
        first = self._chapter_page(book["sid"], 1)
        pages = int(first.get("pages_count") or 1)
        raw = list((self._chapter_page(book["sid"], pages) if pages > 1 else first).get("chapters") or [])
        raw.reverse()
        out, words = [], 0
        for ch in self._list(raw)[:max_chapters + 3]:
            text = self.chapter_text(book, ch)
            if not text.strip():
                continue
            out.append(text)
            words += len(text.split())
            if len(out) >= max_chapters or words >= enough_words:
                break
        return out
