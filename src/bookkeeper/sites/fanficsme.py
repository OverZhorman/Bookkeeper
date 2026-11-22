"""Fanfics.me (fanfics.me): a Russian fan fiction archive, about 76,000 works, and Ranobe.me (ranobe.me), its sister
site for translated web novels (about 600), on the same engine.

Fanfics.me catalog: the search list (/find), newest updates first, 20 works per page. Each entry already has
everything Bookkeeper keeps (author, fandom, characters, direction such as джен or слэш, rating, genres, warnings,
"events" tags, size, status, views, readers, dates), so there's no separate details step. Text: the reader
(/read.php?id=N&chapter=M) lists the chapters and shows one per page. robots.txt only keeps programs off downloads.

Ranobe.me catalog: its catalog list (genres, chapter count, last update). Catalog only for now."""
import html as _html
import re
from datetime import datetime, timezone

from ..analysis.text import clean_text, html_to_text
from ..http import NotFound
from .base import BookInfo, Chapter, Site, looks_adult

BASE = "https://fanfics.me"
RANOBE_BASE = "https://ranobe.me"
STATUS = {"в процессе": "ongoing", "закончен": "completed", "заморожен": "frozen"}
RATINGS = {"G", "PG", "PG-13", "R", "NC-17", "NC-21"}


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


def _int(s: str | None) -> int | None:
    digits = re.sub(r"\D", "", s or "")
    return int(digits) if digits else None


def _date(s: str | None) -> str | None:
    try:
        return datetime.strptime((s or "").strip(), "%d.%m.%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _meta(block: str, label: str) -> str | None:
    """The value after "<b>Label:</b>" in an entry's details, up to the next line break."""
    m = re.search(r"<b>" + label + r":</b>(.*?)(?:<br\s*/?>|</td>)", block, re.S)
    return m.group(1) if m else None


def _fandom(name: str) -> str:
    return "Original" if name.lower().startswith("оригинальн") else f"fandom:{name}"


def parse_entry(fid: str, block: str) -> BookInfo | None:
    title = re.search(r'<h4><a href="/fic' + fid + r'">(.*?)</a>(?:&nbsp;)?\s*(?:<span class="small [^"]*">\((.*?)\)</span>)?',
                      block, re.S)
    if not title:
        return None
    stat = lambda name: _int((re.search(r'<span class="' + name + r'" title="[^"\d]*([\d\s\xa0]+)"', block) or [None, ""])[1])
    dates = re.search(r'title="Опубликовано ([\d.]+), изменено ([\d.]+)"', block) or \
        re.search(r'title="Опубликовано ([\d.]+)"', block)
    summary = re.search(r'<td class="FicTbl_sammary">(.*?)</td>', block, re.S)
    author = _meta(block, "Автор") or _meta(block, "Авторы")
    fandoms = [_text(f) for f in re.findall(r'<a href="/fandom\d+">(.*?)</a>', _meta(block, "Фандом") or "", re.S)]
    characters = [_text(c) for c in re.findall(r"<a[^>]*>(.*?)</a>", _meta(block, "Персонажи") or "", re.S)]
    pairings = [_text(c) for c in re.findall(r"<a[^>]*>(.*?)</a>", _meta(block, "Пейринги") or "", re.S)]
    rating = _text(_meta(block, "Рейтинг") or "") or None
    genres = [g.strip() for g in _text(_meta(block, "Жанры") or "").split(",") if g.strip()]
    warnings = [w.strip() for w in _text(_meta(block, "Предупреждения") or "").split(",") if w.strip()]
    events = [_text(e) for e in re.findall(r"<a[^>]*>(.*?)</a>", _meta(block, "События") or "", re.S)]
    size = _text(_meta(block, "Размер") or "")
    chars = _int(size.split("|", 1)[1]) if "|" in size else None
    status = _text(_meta(block, "Статус") or "").lower()
    direction = _text(title.group(2) or "")
    translated = bool(_meta(block, "Переводчик") or _meta(block, "Переводчики") or _meta(block, "Оригинал"))
    labels = list(dict.fromkeys(x for x in ([direction] if direction else []) + [size.split("|")[0].strip()] +
                                genres + warnings + events + [*map(_fandom, fandoms)] + pairings + characters if x))
    age = rating if rating in RATINGS else None
    return BookInfo(
        sid=fid, url=f"{BASE}/fic{fid}", title=_text(title.group(1)),
        authors=[_text(a) for a in re.findall(r'<a class="user"[^>]*>(.*?)</a>', author or "", re.S)],
        description=html_to_text(summary.group(1)).strip() or None if summary else None, lang="ru",
        is_translation=translated, status=next((v for k, v in STATUS.items() if status.startswith(k)), None),
        words=int(chars / 7.2) if chars else None, views=stat("Views"), likes=stat("ReadersCount"),
        pop_raw=stat("Views"), adult=age in ("NC-17", "NC-21") or looks_adult(labels), age_rating=age, access="free",
        created_at=_date(dates.group(1)) if dates else None,
        updated_at=_date(dates.group(dates.lastindex)) if dates else None, tags=labels,
        extra={"fandoms": [f for f in fandoms if _fandom(f) != "Original"], "readers": stat("ReadersCount"),
               "comments": stat("Comments"), "chars": chars},
        complete=True,
    )


def parse_find(page: str) -> tuple[list[BookInfo], int]:
    parts = re.split(r'<div id="fic_(\d+)" class="FicTable[^"]*">', page)
    books = [parse_entry(parts[i], parts[i + 1]) for i in range(1, len(parts) - 1, 2)]
    pages = [int(n) for n in re.findall(r'href="/find\?page=(\d+)', page)]
    return [b for b in books if b], max(pages, default=1)


class FanficsMe(Site):
    id = "fanficsme"
    name = "Fanfics.me"
    home = BASE
    lang = "ru"
    min_interval = 2.0
    lists_adult = True
    note = ("A Russian fan fiction archive, about 76,000 works, with fandoms, characters, genres, warnings and "
            "“events” tags. Everything but the text comes from its search list.")

    def _find(self, page: int) -> tuple[list[BookInfo], int]:
        try:
            return parse_find(self.http.get(f"{BASE}/find", params={"page": page} if page > 1 else None).text)
        except NotFound:
            return [], 0

    def discover(self, state: dict):
        if state.get("full_done"):
            for page in range(1, 6):  # later passes: the latest updates
                books, _ = self._find(page)
                if not books:
                    break
                yield books
            return
        page = state.get("page", 1)
        while True:
            books, last = self._find(page)
            if books:
                yield books
            if not books or page >= last:
                state.update(full_done=True, page=1)
                return
            page += 1
            state["page"] = page

    def details(self, book: dict) -> BookInfo:  # the search list already has everything
        raise NotImplementedError

    def _read(self, book: dict, n: str) -> str:
        return self.http.get(f"{BASE}/read.php", params={"id": book["sid"], "chapter": n}).text

    def chapters(self, book: dict) -> list[Chapter]:
        s = self._read(book, "0")
        toc = re.search(r'<ul class="FicContents">(.*?)</ul>', s, re.S)
        found = re.findall(r'<a href="/read\.php\?id=' + re.escape(book["sid"]) + r'&(?:amp;)?chapter=(\d+)#start_read">'
                           r'(.*?)</a>', toc.group(1), re.S) if toc else []
        if found:
            return [Chapter(id=n, title=_text(t) or f"Глава {i + 1}", index=i) for i, (n, t) in enumerate(found)]
        if 'id="c0"' in s:
            title = re.search(r'<div class="ReadContent"><h2>(.*?)</h2>', s, re.S)
            return [Chapter(id="0", title=_text(title.group(1)) if title else "Текст", index=0)]
        raise NotFound("no chapters")

    @staticmethod
    def chapter_body(s: str, n: str) -> str:
        start = s.find(f'id="c{n}"')
        if start < 0:
            return ""
        end = min([i for i in (s.find('<td class="chNav', start), s.find('<div class="ReadContentCenter', start))
                   if i > 0] or [len(s)])
        block = s[start:end]
        paras = [html_to_text(p).strip() for p in re.findall(r'<p class="fict"[^>]*>(.*?)</p>', block, re.S)]
        text = "\n".join(p for p in paras if p)
        return text or html_to_text(block[block.find(">") + 1:]).strip()

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        try:
            return self.chapter_body(self._read(book, chapter.id), chapter.id)
        except NotFound:
            return ""


def parse_ranobe_catalog(page: str) -> tuple[list[BookInfo], int]:
    out = []
    parts = re.split(r'<div id="fic_(\d+)" class="FicTable[^"]*">', page)
    for i in range(1, len(parts) - 1, 2):
        rid, block = parts[i], parts[i + 1]
        title = re.search(r'<div class="FicTable_Title">.*?<a href="/ranobe' + rid + r'">([^<]+)</a>', block, re.S)
        if not title:
            continue
        cover = re.search(r'<img src="([^"]+)"', block)
        chapters = re.search(r'<span class="ChaptersCount"[^>]*>(\d+)</span>', block)
        updated = re.search(r'data-time="(\d+)"', block)
        about = re.search(r'<div class="FicTable_Description">(.*?)<div class="FicTable_Genres">', block, re.S)
        genres = [_text(g) for g in re.findall(r'<a href="/catalog/genre/\d+">(.*?)</a>', block)]
        age = next((g for g in genres if re.fullmatch(r"\d+\+", g)), None)
        labels = [g for g in genres if g != age]
        out.append(BookInfo(
            sid=rid, url=f"{RANOBE_BASE}/ranobe{rid}", title=_text(title.group(1)),
            cover=(RANOBE_BASE + cover.group(1) if cover.group(1).startswith("/") else cover.group(1)) if cover else None,
            description=html_to_text(about.group(1)).strip() or None if about else None, lang="ru",
            chapters=int(chapters.group(1)) if chapters else None, age_rating=age,
            adult=age in ("18+", "21+") or looks_adult(labels), access="free",
            updated_at=datetime.fromtimestamp(int(updated.group(1)), timezone.utc).strftime("%Y-%m-%d") if updated else None,
            tags=labels or None, complete=True,
        ))
    pages = [int(n) for n in re.findall(r'href="/catalog\?page=(\d+)"', page)]
    return out, max(pages, default=1)


class RanobeMe(Site):
    id = "ranobeme"
    name = "Ranobe.me"
    home = RANOBE_BASE
    lang = "ru"
    min_interval = 2.0
    has_text = False
    note = "Russian translations of web novels, about 600, on Fanfics.me's engine. Catalog only for now."

    def _page(self, page: int) -> tuple[list[BookInfo], int]:
        try:
            s = self.http.get(f"{RANOBE_BASE}/catalog", params={"page": page} if page > 1 else None).text
        except NotFound:
            return [], 0
        return parse_ranobe_catalog(s)

    def discover(self, state: dict):
        page = 1 if state.get("full_done") else state.get("page", 1)
        while True:
            books, last = self._page(page)
            if books:
                yield books
            if not books or page >= last or (state.get("full_done") and page >= 2):
                state.update(full_done=True, page=1)
                return
            page += 1
            if not state.get("full_done"):
                state["page"] = page

    def details(self, book: dict) -> BookInfo:  # the catalog already has everything
        raise NotImplementedError
