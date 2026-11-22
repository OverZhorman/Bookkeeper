"""Fantlab (fantlab.ru): the big Russian database of science fiction and fantasy (and much else), where readers vote
on each work's classifier: genres, general character, where and when it's set, plot devices, plot linearity and
reader age, each with the share of voters who picked it.

Catalog: Fantlab's genre search (/bygenre), novels only, most-rated first, for every classifier genre. Visitors see
only the first 50 results of a search, so Bookkeeper splits a search that finds more by year (and a single year by
Russian-language and translated works) until each part fits. Details: the work from Fantlab's open API
(api.fantlab.ru): the classifier, the annotation, the original title and alternative titles, the rating. robots.txt
lets programs in with 1.2 seconds between requests. Catalog only: Fantlab has no texts."""
import re
from datetime import date

from ..http import NotFound
from .base import BookInfo, Site, SiteError

BASE = "https://fantlab.ru"
API = "https://api.fantlab.ru"
PER_SEARCH = 50                               # what Fantlab shows visitors of one search
# The "genres/subgenres" part of the classifier: name -> id in the genre search (wg<id>).
GENRES = {
    "Фантастика": 1, "«Твёрдая» научная фантастика": 2, "«Мягкая» (гуманитарная) научная фантастика": 3,
    "Космоопера": 4, "Киберпанк": 5, "Планетарная фантастика": 6, "Таймпанк": 7, "Стоунпанк": 8, "Сандалпанк": 9,
    "Клокпанк": 10, "Стимпанк/паропанк": 11, "Дизельпанк": 12, "Темпоральная фантастика, хроноопера": 13,
    "Постапокалиптика": 15, "Роман-катастрофа": 16, "Утопия": 17, "Антиутопия": 18, "Фэнтези": 19,
    "Эпическое фэнтези": 20, "Героическое фэнтези": 21, "Городское фэнтези": 22, "Тёмное фэнтези": 23,
    "Технофэнтези": 211, "Научное фэнтези": 24, "«Дотолкиновское» фэнтези": 25, "«Классическое» фэнтези": 26,
    "Артуриана": 27, "Анималистическое": 28, "Мифологическое": 29, "Магический реализм": 33,
    "Классический латино-американский": 161, "Современный": 162, "Мистика": 30, "Хоррор/Ужасы": 31, "Готика": 227,
    "Классическая": 228, "Современная стилизация": 229, "Истории о привидениях": 230,
    "Классический мистический хоррор": 231, "Лавкрафтианский хоррор": 232, "Сплаттерпанк": 233,
    "Зомби-хоррор": 234, "Современный психологический хоррор": 235, "Сказка/Притча": 32, "Детектив": 34,
    "Классический детектив": 186, "Нуар": 187, "Полицейский детектив": 188, "Боевик": 35, "Триллер": 225,
    "Любовный роман": 36, "Историческая проза": 37, "Сюрреализм": 38, "Постмодернизм": 39, "Реализм": 160,
    "Психоделика": 116, "ЛитРПГ": 280, "Вестерн": 284,
}
# Classifier parts whose labels mean little or something else on their own ("Линейный", "Любой", and "Для взрослых",
# which is a reader age, not an 18+ mark): kept as "part: label". Places and times ("Параллельный мир", "Далёкое
# будущее") stay plain, so the shared tags recognise them.
PREFIXED = {5: "Возраст читателя", 7: "Линейность сюжета"}
AGES = {"Детская литература": "G", "Любой": "G", "Подростковая литература": "PG-13", "Для взрослых": "R",
        "Только для взрослых": "NC-17"}
ORIGIN = {"ja": "jp", "ko": "kr", "zh": "cn"}
_ROW = re.compile(r'<tr[^>]*><td><span class="hidden-numbers">\d+\. </span>(.*?)</td><td><nobr>(.*?)</nobr></td></tr>',
                  re.S)
_BBCODE = re.compile(r"\[/?[a-zA-Z]+(?:=[^\]]*)?\]")


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment or "")).strip()


def _plain(bbcode: str | None) -> str | None:
    """Fantlab's annotations use BBCode ([b], [url=...], [autor=1]Name[/autor])."""
    text = _BBCODE.sub("", bbcode or "").replace("\r\n", "\n").strip()
    return text or None


def parse_search(page: str) -> tuple[list[BookInfo], int]:
    """A genre search page: its works (the first 50 at most) and how many it found."""
    total = re.search(r"Найденные произведения \((\d+) шт", page)
    out = []
    for cell, score in _ROW.findall(page):
        link = re.search(r"<a href=/work(\d+)[^>]*>«(.*?)»</a>", cell, re.S)
        if not link:
            continue
        names = _text(cell[:cell.find("<a href=/work")])
        title, _, original = _text(link.group(2)).partition(" / ")
        kind = re.search(r"\((\w[\w\- ]*?)(?:, (\d{4}) г\.)?\)", _text(cell[link.end():]))
        rating = re.search(r"([\d.]+)\s*\((\d+)\)", score)
        out.append(BookInfo(
            sid=link.group(1), url=f"{BASE}/work{link.group(1)}", title=title,
            alt_titles=[original] if original else [], authors=[a for a in names.split(", ") if a],
            lang="ru", rating=float(rating.group(1)) if rating else None,
            votes=int(rating.group(2)) if rating else None, pop_raw=int(rating.group(2)) if rating else None,
            extra={"type": kind.group(1) if kind else None,
                   "year": int(kind.group(2)) if kind and kind.group(2) else None},
        ))
    return out, int(total.group(1)) if total else len(out)


def _labels(groups: list) -> list[tuple[str, float]]:
    out = []
    for g in groups or []:
        out.append((g.get("label") or "", float(g.get("percent") or 0)))
        out.extend(_labels(g.get("genre") or []))
    return [(name, pct) for name, pct in out if name]


def work_info(d: dict) -> BookInfo:
    """A work from the API (/work/<id>/extended)."""
    tags, age = [], None
    for group in (d.get("classificatory") or {}).get("genre_group") or []:
        gid = group.get("genre_group_id")
        for name, pct in _labels(group.get("genre") or []):
            if gid == 5:
                if age is None or pct > age[1]:
                    age = (name, pct)
            tags.append(f"{PREFIXED[gid]}: {name}" if gid in PREFIXED else name)
    authors = [a.get("name") for a in d.get("authors") or [] if a.get("type") == "autor" and a.get("name")]
    rating = d.get("rating") or {}
    code = (d.get("lang_code") or "").lower()
    translated = bool(code) and code != "ru"
    alts = [d.get("work_name_orig") or ""] + [str(x) for x in d.get("work_name_alts") or []]
    cover = None
    for block in (d.get("editions_blocks") or {}).values():
        pics = [e for e in block.get("list") or [] if e.get("pic_num") and e.get("edition_id")]
        if pics:
            cover = f"{BASE}/images/editions/small/{pics[-1]['edition_id']}"
            break
    adult = bool(age and age[0] == "Только для взрослых")
    unfinished = d.get("work_notfinished") or d.get("work_preparing")
    return BookInfo(
        sid=str(d["work_id"]), url=f"{BASE}/work{d['work_id']}", title=(d.get("work_name") or "").strip(),
        alt_titles=[a.strip() for a in alts if a and a.strip()], authors=authors,
        description=_plain(d.get("work_description")), cover=cover, lang="ru", is_translation=translated,
        origin=(ORIGIN.get(code, code) if translated else None), status="ongoing" if unfinished else "completed",
        rating=float(rating["rating"]) if rating.get("rating") else None, votes=rating.get("voters"),
        pop_raw=rating.get("voters"), adult=adult, age_rating=AGES.get(age[0]) if age else None,
        tags=list(dict.fromkeys(tags)),
        extra={"type": d.get("work_type"), "year": d.get("work_year"), "orig_lang": code or None,
               "authors_orig": [a.get("name_orig") for a in d.get("authors") or [] if a.get("name_orig")]},
    )


class Fantlab(Site):
    id = "fantlab"
    name = "Fantlab"
    home = BASE
    lang = "ru"
    min_interval = 1.5                        # robots.txt asks for 1.2 seconds
    has_text = False
    note = ("The big Russian science fiction and fantasy database, with a classifier readers vote on (genres, "
            "setting, time, plot devices, reader age). Bookkeeper reads each classifier genre's novels, most-rated "
            "first, then each novel through Fantlab's open API. Catalog only.")
    extra_settings = {
        "genres": {"label": "Classifier genres to read, comma-separated as Fantlab names them (Фантастика, Фэнтези, "
                            "ЛитРПГ, Космоопера…), or all", "default": "all"},
    }

    def _genres(self) -> list[int]:
        raw = str(self.settings.get("genres") or "all").strip()
        if raw.lower() in ("all", "все", ""):
            return list(GENRES.values())
        wanted = {x.strip().lower() for x in raw.split(",") if x.strip()}
        return [gid for name, gid in GENRES.items() if name.lower() in wanted] or list(GENRES.values())

    def _search(self, gid: int, yfrom: int = 0, yto: int = 0, lang: str = "") -> tuple[list[BookInfo], int]:
        params = {"sort": "marks", "form": "nov", f"wg{gid}": "on"}
        if yfrom:
            params.update(byyear="on", yearfrom=str(yfrom), yearto=str(yto))
        if lang:
            params["lang_id"] = lang
        try:
            page = self.http.get(f"{BASE}/bygenre", params=params).text
        except NotFound:
            return [], 0
        if "Найденные произведения" not in page and "genrevoteform" not in page:
            raise SiteError("unexpected genre search page (layout changed?)")
        return parse_search(page)

    def discover(self, state: dict):
        this_year = date.today().year
        if state.get("full_done"):
            for gid in self._genres():  # later passes: this year's and last year's novels
                books, _ = self._search(gid, this_year - 1, this_year)
                if books:
                    yield books
            return
        if "todo" not in state:
            state["todo"] = [[gid, 0, 0, ""] for gid in self._genres()]
        while state["todo"]:
            gid, yfrom, yto, lang = state["todo"][0]
            books, total = self._search(gid, yfrom, yto, lang)
            parts = []
            if total > PER_SEARCH:
                if not yfrom:
                    parts = [[gid, 1, this_year, lang]]
                elif yfrom < yto:
                    mid = (yfrom + yto) // 2
                    parts = [[gid, yfrom, mid, lang], [gid, mid + 1, yto, lang]]
                elif not lang:
                    parts = [[gid, yfrom, yto, "1"], [gid, yfrom, yto, "-1"]]
            state["todo"] = parts + state["todo"][1:]
            if books:
                yield books
        state["full_done"] = True
        state.pop("todo", None)

    def details(self, book: dict) -> BookInfo:
        d = self.http.get_json(f"{API}/work/{book['sid']}/extended")
        if not isinstance(d, dict) or "work_id" not in d:
            raise NotFound(book["sid"])
        return work_info(d)
