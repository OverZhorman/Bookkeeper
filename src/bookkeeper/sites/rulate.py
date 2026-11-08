"""Rulate (tl.rulate.ru): Russian translations of web novels and light novels, plus original works and fanfiction.
Many translations sell their newer chapters; logged in, Bookkeeper reads the ones your account has bought.

Catalog: the search listing, 20 books per page, most viewed first (chapters total / paid, rating, likes, status).
Details and chapter list: the book page (author, genres, tags, fandom; the list is 100 chapters per page).
Chapter text: the chapter page."""
import html as _html
import re

from ..analysis.text import clean_text, html_to_text
from ..http import NotFound
from .base import BookInfo, Chapter, Site, SiteError, looks_adult

BASE = "https://tl.rulate.ru"
CATEGORY_ORIGIN = {"Китайские": "cn", "Корейские": "kr", "Японские": "jp", "Английские": "en"}
_THANKS = re.compile(r"(?m)^(https?://tl\.rulate\.ru/\S*|Сказали спасибо \d+ читател\S*)\s*$")


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


def _label(block: str, title: str) -> str:
    m = re.search(r'title="' + re.escape(title) + r'"><i class="[^"]*"></i>\s*([^<]*)<', block)
    return m.group(1).strip() if m else ""


def _pair(text: str) -> tuple[float | None, int | None]:
    """'4.4 / 2 781' -> (4.4, 2781). The site groups thousands with (thin) spaces."""
    m = re.match(r"([\d.]+)/(\d+)", re.sub(r"\s", "", text or ""))
    return (float(m.group(1)), int(m.group(2))) if m else (None, None)


def _num(text: str) -> int | None:
    digits = re.sub(r"\D", "", text or "")
    return int(digits) if digits else None


def _status(state: str) -> str:
    s = state.lower()
    if "заверш" in s:
        return "completed"
    if any(x in s for x in ("заморож", "брошен", "неактив", "приостанов")):
        return "frozen"
    return "ongoing" if s else "unknown"


class Rulate(Site):
    id = "rulate"
    name = "Rulate"
    home = BASE
    lang = "ru"
    min_interval = 1.5
    note = ("Russian translations of web novels, plus original works and fanfiction. Many translations sell newer "
            "chapters: log in to have downloads include the ones you bought.")
    lists_adult = True
    login_url = f"{BASE}/"
    login_benefit = "18+ books, and the paid chapters you bought (downloads then include them)."
    login_form = {"user": "input[name='login[login]']", "password": "input[name='login[pass]']",
                  "submit": "input[type=submit][value='Войти']"}
    logged_in_js = "!document.querySelector(\"input[name='login[pass]']\") && !!document.querySelector('a[href*=\"/users/\"]')"
    extra_settings = {"pages": {"label": "Catalog pages to read in the first pass (20 books each, most viewed first)",
                                "default": "2000"}}

    def check_login(self) -> bool | None:
        page = self.http.get(f"{BASE}/").text
        if "name=\"login[pass]\"" in page:
            return False
        return True if "tl.rulate.ru" in page or "/users/" in page else None

    # ----- catalog
    def _card(self, block: str) -> BookInfo | None:
        link = re.search(r"<a href='/book/(\d+)[^']*'>(.*?)</a>(?:<br/><small[^>]*>(.*?)</small>)?", block, re.S)
        if not link:
            return None
        bid = link.group(1)
        chapters, paid = (_label(block, "Кол-во глав всего / Кол-во платных глав").split("/") + ["", ""])[:2]
        rating, votes = _pair(_label(block, "Рейтинг"))
        likes = re.sub(r"\D", "", _label(block, "Лайки"))
        cover = re.search(r"<img src='([^']+)'", block)
        desc = re.search(r'<p class="book-descr-short">(.*?)</p>', block, re.S)
        cat = re.search(r"<small class='cat'><a[^>]*>(.*?)</a>", block)
        state = re.search(r"состояние перевода: <span[^>]*>(.*?)</span>", block)
        active = re.search(r"последняя активность: (\d+)\.(\d+)\.(\d{4})", block)
        n_ch = _num(chapters)
        n_paid = _num(paid) or 0
        category = _text(cat.group(1)) if cat else ""
        return BookInfo(
            sid=bid, url=f"{BASE}/book/{bid}", title=_text(link.group(2)) or f"#{bid}",
            alt_titles=[_text(link.group(3))] if link.group(3) else [],
            description=_text(desc.group(1)) or None if desc else None,
            cover=BASE + cover.group(1) if cover and cover.group(1).startswith("/") else (cover.group(1) if cover else None),
            lang="ru", status=_status(state.group(1) if state else ""),
            is_translation=category not in ("Авторские", "Авторские фанфики"),
            origin=CATEGORY_ORIGIN.get(category), chapters=n_ch,
            rating=round(rating * 2, 2) if rating else None, votes=votes or None,
            likes=int(likes) if likes else None, pop_raw=int(likes) if likes else None,
            access="free" if not n_paid else ("paid" if n_ch and n_paid >= n_ch else "partial"),
            updated_at=f"{active.group(3)}-{int(active.group(2)):02d}-{int(active.group(1)):02d}" if active else None,
            tags=[category] if category else [], partial_tags=True,
        )

    def _search(self, sort: int, page: int) -> list[BookInfo]:
        params = {"t": "", "sort": sort, "cat": 0}
        if not self.settings.get("include_adult", True):
            params["adult"] = 0
        url = f"{BASE}/search" + ("" if page == 1 else f"/index/t//sort/{sort}/cat/0/Book_page/{page}")
        p = self.http.get(url, params=params if page == 1 else ({"adult": 0} if "adult" in params else None))
        start = p.text.find("<ul class='search-results'>")
        if start < 0:
            return []
        end = p.text.find("<div class='pagination", start)
        blocks = p.text[start:end if end > 0 else None].split("<li><div class='th'>")[1:]
        return [b for b in (self._card(x) for x in blocks) if b and b.chapters]

    def discover(self, state: dict):
        if state.get("full_done"):
            for page in range(1, 6):  # later passes: recently active translations
                books = self._search(4, page)
                if not books:
                    break
                yield books
            return
        limit = int(re.sub(r"\D", "", str(self.settings.get("pages") or "2000")) or 2000)
        page = state.get("page", 1)
        while page <= limit:
            books = self._search(5, page)
            if not books and page > 1:
                break
            if books:
                yield books
            page += 1
            state["page"] = page
        state.update(full_done=True, page=1)

    # ----- the book page
    def _book_page(self, sid: str, toc_page: int = 1) -> str:
        return self.http.get(f"{BASE}/book/{sid}", params={"Chapter_page": toc_page} if toc_page > 1 else None).text

    def details(self, book: dict) -> BookInfo:
        s = self._book_page(book["sid"])
        h1 = re.search(r'<h1>\s*<span itemprop="name">(.*?)</span>', s, re.S)
        if not h1:
            if re.search(r"18\+|совершеннолет", s):
                raise SiteError("an 18+ book: log in on the Sites page to see it")
            raise SiteError("unexpected page layout (no title)")
        alt = re.search(r'</h1>\s*<div style="font-size: 14px; color: #999;[^"]*">(.*?)</div>', s, re.S)

        def field(name: str) -> str:
            m = re.search(r"<strong>" + re.escape(name) + r":?</strong>\s*<em>(.*?)</em>", s, re.S)
            return m.group(1) if m else ""

        def badges(name: str) -> list[str]:
            return [_text(x) for x in re.findall(r'class="badge">(.*?)</a>', field(name), re.S)]

        genres, tags, fandoms = badges("Жанры"), badges("Тэги"), badges("Фэндом")
        labels = list(dict.fromkeys(x for x in genres + tags + [f"fandom:{f}" for f in fandoms] if x))
        authors = [_text(a) for a in re.findall(r"<a[^>]*>(.*?)</a>", field("Автор"), re.S)] or \
            ([_text(field("Автор"))] if _text(field("Автор")) else [])
        year = re.search(r"\d{4}", _text(field("Год выпуска")))
        state = re.search(r"Состояние перевода:</dt>\s*<dd>\s*<span[^>]*>(.*?)</span>", s, re.S)
        release = _text(field("Выпуск")).lower()
        status = _status(state.group(1) if state else "")
        if status == "ongoing" and "заверш" in release and "заверш" in (state.group(1).lower() if state else ""):
            status = "completed"
        desc = re.search(r'<meta property="ranobe:description" content="([^"]*)"', s)
        cover = re.search(r'<link itemprop="image" href="([^"]+)"', s)
        rows = self._rows(s)
        return BookInfo(
            sid=book["sid"], url=f"{BASE}/book/{book['sid']}", title=_text(h1.group(1)),
            alt_titles=[_text(alt.group(1))] if alt else [], authors=[a for a in authors if a],
            description=html_to_text(desc.group(1)) or None if desc else None,
            cover=cover.group(1) if cover else None, lang="ru", status=status,
            created_at=year.group(0) if year else None, tags=labels, adult=looks_adult(labels),
            extra={"fandoms": fandoms, "toc": [[c.id, c.title] for c in rows if c.free][:8]},
        )

    @staticmethod
    def _rows(page: str) -> list[Chapter]:
        out = []
        for cid, row in re.findall(r"<tr id='c_(\d+)'[^>]*class='chapter_row[^']*'>(.*?)</tr>", page, re.S):
            title = re.search(r"<td class='t'>(.*?)</td>", row, re.S)
            free = "ready_new' class='btn" in row or ("disabled" not in row and "ready_new" in row)
            out.append(Chapter(id=cid, title=_text(title.group(1)) if title else f"#{cid}", index=0, free=free))
        return out

    def chapters(self, book: dict) -> list[Chapter]:
        page = self._book_page(book["sid"])
        pages = [int(x) for x in re.findall(r"Chapter_page=(\d+)", page)]
        out = self._rows(page)
        for n in range(2, max(pages, default=1) + 1):
            out += self._rows(self._book_page(book["sid"], n))
            if self.progress:
                self.progress(len(out))
        for i, c in enumerate(out):
            c.index = i
        return out

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        try:
            s = self.http.get(f"{BASE}/book/{book['sid']}/{chapter.id}/ready_new").text
        except NotFound:
            return ""
        start = s.find('class="content-text"')
        if start < 0:
            return ""  # paid, or the site asks to log in
        end = s.find('<ul class="pager"', start)
        text = html_to_text(s[s.find(">", start) + 1: end if end > 0 else None])
        return clean_text(_THANKS.sub("", text))

    def opening_text(self, book: dict, max_chapters: int = 3, enough_words: int = 6000) -> list[str]:
        toc = (book.get("extra") or {}).get("toc")
        chapters = [Chapter(id=str(c), title=t, index=i) for i, (c, t) in enumerate(toc)] if toc else \
            [c for c in self._rows(self._book_page(book["sid"])) if c.free]
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
