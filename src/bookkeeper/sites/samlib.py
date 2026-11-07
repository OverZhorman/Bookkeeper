"""Samlib (samlib.ru, «Самиздат»): the oldest Russian self-publishing site.

It has hundreds of thousands of texts, mostly short, so Bookkeeper doesn't collect it whole: it reads the genre
lists you choose (Settings), most-read works first, and keeps the works long enough to be a novel or novella.
Each work is a single page with the whole text; Bookkeeper splits it into chapters at its "Глава …" headings."""
import html as _html
import re

from ..analysis.text import clean_text, detect_lang, html_to_text, opening_pieces
from ..http import NotFound
from .base import BookInfo, Chapter, Site, SiteError, looks_adult

BASE = "http://samlib.ru"
GENRES = {"24": "Фэнтези", "1": "Фантастика", "25": "Приключения", "22": "Киберпанк", "35": "Фанфик",
          "2": "Детектив", "17": "Мистика", "12": "Любовный роман", "26": "История", "30": "Хоррор", "8": "Юмор",
          "5": "Проза", "10": "Переводы", "16": "Сказки", "29": "Детская", "19": "Мемуары"}
DEFAULT_GENRES = "24, 1, 25, 22, 35, 2, 17, 12, 26"
FORMS = {"Роман", "Повесть", "Сборник рассказов", "Рассказ", "Новелла", "Пьеса; сценарий", "Очерк"}
_ROW = re.compile(r"<DL><DT><li>(.*?)</DL>", re.S | re.I)
_HEADING = re.compile(r"^(Глава|ГЛАВА|Часть|ЧАСТЬ|Пролог|ПРОЛОГ|Эпилог|ЭПИЛОГ|Интерлюдия|ИНТЕРЛЮДИЯ|Книга|КНИГА|"
                      r"Chapter|CHAPTER)\b[^\n]{0,80}$|^[IVXLC]{1,6}\.?$|^\d{1,3}\.?$")
_TEXT_START = re.compile(r"<!--[-\s]*Собственно произведение[-\s]*-->", re.I)
_TEXT_END = re.compile(r"<!--[-\s]*Блок описания произведения \(слева внизу\)|<!--[-\s]*Блочек голосования \(оценка\) нижний",
                       re.I)


def _text(fragment: str) -> str:
    return clean_text(_html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")))


class Samlib(Site):
    id = "samlib"
    name = "Samlib"
    home = BASE
    lang = "ru"
    min_interval = 2.0
    note = ("Too big to collect whole: Bookkeeper reads the genres you choose (Settings), most-read works first, "
            "and keeps novel-length ones.")
    extra_settings = {
        "genres": {"label": "Genres to collect (numbers: " + ", ".join(f"{k} {v}" for k, v in GENRES.items()) + ")",
                   "default": DEFAULT_GENRES},
        "min_size": {"label": "Shortest work to keep, in kilobytes (about 300 is a full novel)", "default": "150"},
        "pages": {"label": "Pages to read per genre (200 works each, most read first)", "default": "25"},
    }

    def _genres(self) -> list[str]:
        return [g for g in re.findall(r"\d+", str(self.settings.get("genres") or DEFAULT_GENRES))]

    def _num_setting(self, key: str, default: int) -> int:
        m = re.search(r"\d+", str(self.settings.get(key) or ""))
        return int(m.group(0)) if m else default

    # ----- catalog
    def _row(self, row: str, genre: str) -> BookInfo | None:
        work = re.search(r"<a href=/?([a-z0-9_]/[^/>\s]+/[^>\s]+?)\.shtml><b>(.*?)</b></a>", row, re.S | re.I)
        if not work:
            return None
        author = re.search(r"<a href=/?[a-z0-9_]/[^/>\s]+/?><font[^>]*>(.*?)</font></a>", row, re.S | re.I)
        size = re.search(r"<b>(\d+)k</b>", row)
        readers = re.match(r"\s*<b>(\d+)</b>", row)
        score = re.search(r"Оценка:<b>([\d.]+)\*(\d+)</b>", row)
        form = re.search(r"&nbsp;\s+([А-ЯЁа-яё][^<&]{1,40}?)\s+(?:<A HREF=/comment|</small>)", row)
        ann = re.search(r"<DD>.*?<i>(.*?)</i>", row, re.S | re.I)
        size_k = int(size.group(1)) if size else 0
        title = _text(work.group(2))
        description = _text(ann.group(1)) if ann else None
        sid = work.group(1)
        return BookInfo(
            sid=sid, url=f"{BASE}/{sid}.shtml", title=title or sid,
            authors=[_text(author.group(1))] if author else [], description=description or None,
            lang=detect_lang(f"{title} {description or ''}") or "ru", is_translation=genre == "10",
            words=int(size_k * 1024 / 7.2) if size_k else None,
            rating=float(score.group(1)) if score else None, votes=int(score.group(2)) if score else None,
            views=int(readers.group(1)) if readers else None, pop_raw=int(readers.group(1)) if readers else None,
            access="free", tags=[GENRES.get(genre, ""), *([form.group(1).strip()] if form and form.group(1).strip()
                                                          in FORMS else [])],
            partial_tags=True, extra={"size_k": size_k, "form": form.group(1).strip() if form else None},
        )

    def _listing(self, genre: str, page: int) -> list[BookInfo]:
        try:
            p = self.http.get(f"{BASE}/janr/index_janr_hits{genre}-{page}.shtml")
        except NotFound:
            return []
        min_k = self._num_setting("min_size", 150)
        out = []
        for row in _ROW.findall(p.text):
            info = self._row(row, genre)
            if info and (info.extra.get("size_k") or 0) >= min_k:
                out.append(info)
        return out

    def discover(self, state: dict):
        genres, pages = self._genres(), self._num_setting("pages", 25)
        if state.get("full_done"):  # each later pass reads the lists again (new and rising works)
            state.update(gi=0, page=1, full_done=False)
        while state.get("gi", 0) < len(genres):
            genre = genres[state.get("gi", 0)]
            page = state.get("page", 1)
            books = self._listing(genre, page)
            if books:
                yield books
            if page >= pages or not books and page > 3:
                state.update(gi=state.get("gi", 0) + 1, page=1)
            else:
                state["page"] = page + 1
        state["full_done"] = True

    # ----- the work page
    def details(self, book: dict) -> BookInfo:
        p = self.http.get(f"{BASE}/{book['sid']}.shtml", max_bytes=40_000)
        s = p.text
        h2 = re.search(r"<h2>(.*?)</h2>", s, re.S | re.I)
        if not h2:
            raise SiteError("unexpected page layout (no title)")
        author = re.search(r"<small><a href=[^>]*>(.*?)</a></small>", h2.group(1), re.S | re.I)
        title = _text(re.sub(r"(?is)<small>.*?</small>", "", h2.group(1)))
        info = BookInfo(sid=book["sid"], url=f"{BASE}/{book['sid']}.shtml", title=title,
                        authors=[_text(author.group(1))] if author else [])
        dates = re.search(r"Размещен:\s*(\d\d)/(\d\d)/(\d{4})(?:,\s*изменен:\s*(\d\d)/(\d\d)/(\d{4}))?\.\s*(\d+)k", s)
        if dates:
            d, m, y = dates.group(1, 2, 3)
            info.created_at = f"{y}-{m}-{d}"
            if dates.group(4):
                info.updated_at = f"{dates.group(6)}-{dates.group(5)}-{dates.group(4)}"
            info.words = int(int(dates.group(7)) * 1024 / 7.2)
        kinds = re.search(r'<li><a href=/type/[^>]*>(.*?)</a>:(.*?)(?:<li>|</ul>)', s, re.S | re.I)
        labels = []
        if kinds:
            form = _text(kinds.group(1))
            labels = ([form] if form in FORMS else []) + [
                _text(g) for g in re.findall(r"<a [^>]*>(.*?)</a>", kinds.group(2), re.S)]
        info.tags = [x for x in labels if x]
        info.adult = looks_adult(info.tags)
        info.is_translation = "Переводы" in labels
        ann = re.search(r"<b>Аннотация:</b><br>\s*<font[^>]*><i>(.*?)</i>", s, re.S | re.I)
        if ann:
            info.description = html_to_text(ann.group(1)) or None
        series = re.search(r'<li>\s*<a href=index_\d+\.shtml>\s*(.*?)</a>', s, re.S | re.I)
        info.extra = {"series": _text(series.group(1)) if series else None}
        info.lang = detect_lang(f"{title} {info.description or ''}") or "ru"
        info.status = "unknown"
        return info

    def _work_text(self, sid: str, max_bytes: int | None = None) -> str:
        try:
            s = self.http.get(f"{BASE}/{sid}.shtml", max_bytes=max_bytes).text
        except NotFound:
            return ""
        m = _TEXT_START.search(s)
        if not m:
            return ""
        end = _TEXT_END.search(s, m.end())
        return html_to_text(s[m.end(): end.start() if end else None])

    @staticmethod
    def split_chapters(text: str, chunk_words: int = 8000) -> list[tuple[str, str]]:
        """(title, text) parts: at 'Глава …' headings, or in even chunks when the text has none."""
        lines = text.split("\n")
        cuts = [i for i, line in enumerate(lines) if len(line) <= 90 and _HEADING.match(line.strip())]
        parts = []
        if len(cuts) >= 2:
            if cuts[0] > 0 and sum(len(x.split()) for x in lines[:cuts[0]]) > 200:
                parts.append(("Начало", "\n".join(lines[:cuts[0]])))
            for a, b in zip(cuts, cuts[1:] + [len(lines)]):
                body = "\n".join(lines[a + 1:b]).strip()
                if body:
                    parts.append((lines[a].strip(), body))
        if not parts:
            words, chunk, n = 0, [], 1
            for line in lines:
                chunk.append(line)
                words += len(line.split())
                if words >= chunk_words:
                    parts.append((f"Часть {n}", "\n".join(chunk)))
                    chunk, words, n = [], 0, n + 1
            if chunk:
                parts.append((f"Часть {n}" if n > 1 else "Текст", "\n".join(chunk)))
        return parts

    def chapters(self, book: dict) -> list[Chapter]:
        parts = self.split_chapters(self._work_text(book["sid"]))
        self._parts = {str(i): text for i, (_, text) in enumerate(parts)}
        return [Chapter(id=str(i), title=t, index=i) for i, (t, _) in enumerate(parts)]

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        parts = getattr(self, "_parts", None)
        if parts is None or chapter.id not in parts:
            self.chapters(book)
            parts = self._parts
        return parts.get(chapter.id, "")

    def opening_text(self, book: dict, max_chapters: int = 3, enough_words: int = 6000) -> list[str]:
        """The opening ~6000 words in three pieces (chapter breaks don't matter for the narration check)."""
        text = self._work_text(book["sid"], max_bytes=400_000)  # the opening is enough
        return opening_pieces(text, enough_words, max_chapters)
