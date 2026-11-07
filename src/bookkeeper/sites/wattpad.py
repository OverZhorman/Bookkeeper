"""Wattpad: user-written stories in many languages.

Wattpad is far too big to collect whole, so Bookkeeper collects the results of the search terms you choose
(Sites page -> Wattpad -> Settings), keeping English, Russian and Ukrainian stories by default.
Search results already include tags, status and stats; chapters and text come from Wattpad's own data feed."""
from ..analysis.text import detect_lang, html_to_text
from .base import BookInfo, Chapter, Site

BASE = "https://www.wattpad.com"
FIELDS = ("stories(id,title,user(name),tags,completed,numParts,readCount,voteCount,description,language(id,name),"
          "mature,cover,createDate,modifyDate,url,isPaywalled),total")
DEFAULT_QUERIES = ("firstperson, first person pov, litrpg, gamelit, isekai, reincarnation, transmigration, system, "
                   "progression fantasy, cultivation, kingdom building, dungeon, fantasy adventure, "
                   "попаданец, попаданка, фэнтези, литрпг, от первого лица")
MAX_OFFSET = 9900  # Wattpad's search stops answering past ~10,000 results per term


class Wattpad(Site):
    id = "wattpad"
    name = "Wattpad"
    home = BASE
    lang = "en"
    min_interval = 1.5
    note = ("Too big to collect whole: Bookkeeper collects the results of your search terms (Settings). "
            "Many Wattpad authors tag their point of view (firstperson, 1stperson), which helps a lot.")
    lists_adult = True
    extra_settings = {
        "queries": {"label": "Search terms, comma-separated", "default": DEFAULT_QUERIES},
        "languages": {"label": "Languages to keep (en, ru, uk)", "default": "en, ru, uk"},
    }

    def _queries(self) -> list[str]:
        raw = self.settings.get("queries") or DEFAULT_QUERIES
        return [q.strip() for q in raw.split(",") if q.strip()]

    def _info(self, s: dict) -> BookInfo:
        description = s.get("description") or ""
        lang = detect_lang(f"{s.get('title', '')}\n{description}")
        return BookInfo(
            sid=str(s["id"]), url=s.get("url") or f"{BASE}/story/{s['id']}", title=(s.get("title") or "").strip(),
            authors=[(s.get("user") or {}).get("name")] if (s.get("user") or {}).get("name") else [],
            description=description or None, cover=s.get("cover"), lang=lang,
            status="completed" if s.get("completed") else "ongoing", is_translation=False,
            chapters=s.get("numParts"), views=s.get("readCount"), likes=s.get("voteCount"), pop_raw=s.get("readCount"),
            adult=bool(s.get("mature")), access="partial" if s.get("isPaywalled") else "free",
            created_at=(s.get("createDate") or "")[:10] or None, updated_at=(s.get("modifyDate") or "")[:10] or None,
            tags=[t for t in s.get("tags") or [] if t], complete=True,
        )

    def _search(self, query: str, offset: int) -> tuple[list[BookInfo], int]:
        data = self.http.get_json(f"{BASE}/v4/search/stories", params={
            "query": query, "limit": 100, "offset": offset, "mature": "true", "fields": FIELDS})
        return [self._info(s) for s in data.get("stories") or []], int(data.get("total") or 0)

    def discover(self, state: dict):
        keep = {x.strip() for x in (self.settings.get("languages") or "en, ru, uk").split(",") if x.strip()}
        queries = self._queries()
        if state.get("full_done"):
            state.update(qi=0, offset=0, full_done=False)  # each new pass re-reads the terms (new stories)
        while state.get("qi", 0) < len(queries):
            q = queries[state.get("qi", 0)]
            books, total = self._search(q, state.get("offset", 0))
            kept = [b for b in books if b.lang in keep]
            if kept:
                yield kept
            state["offset"] = state.get("offset", 0) + 100
            if not books or state["offset"] >= min(total, MAX_OFFSET):
                state["qi"] = state.get("qi", 0) + 1
                state["offset"] = 0
        state["full_done"] = True

    def details(self, book: dict) -> BookInfo:
        raise NotImplementedError  # search results already have everything

    def chapters(self, book: dict) -> list[Chapter]:
        data = self.http.get_json(f"{BASE}/api/v3/stories/{book['sid']}", params={"fields": "parts(id,title,isPaywalled)"})
        return [Chapter(id=str(p["id"]), title=p.get("title") or f"Part {i + 1}", index=i, free=not p.get("isPaywalled"))
                for i, p in enumerate(data.get("parts") or [])]

    def chapter_text(self, book: dict, chapter: Chapter) -> str:
        p = self.http.get(f"{BASE}/apiv2/storytext", params={"id": chapter.id})
        return html_to_text(p.text)
