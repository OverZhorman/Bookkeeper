"""Kubikus forum (kubikus.ru/forum): readers recommending books to each other.

This "site" adds no books of its own. It reads the recommendation sections of the forum, collects every
book mentioned in posts (links to book sites, and "Author «Title»" / "Author - Title" in the text), and links
each mention to the matching book in your library, now or whenever that book arrives later.
In the Library, use "Only books recommended on forums"; the book panel lists the posts."""
import html as _html
import re

from .. import db, matching
from ..db import now
from .base import Site

BASE = "https://www.kubikus.ru/forum/"
SOURCE = "Kubikus"
DEFAULT_FORUMS = "48, 28, 19, 49"  # Посоветуйте мне..., Наша Ф&Ф, Ино Ф&Ф, Ф&Ф на СамИздате
MONTHS = {"янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "мая": 5, "июн": 6, "июл": 7, "авг": 8, "сен": 9,
          "окт": 10, "ноя": 11, "дек": 12}

# Links to books on sites Bookkeeper knows (or will know). Unknown sites are kept for later.
LINKS = [
    ("authortoday", re.compile(r"author\.today/(?:work|reader)/(\d+)")),
    ("litnet", re.compile(r"litnet\.com/(?:ru|uk|en)/(?:book|reader)/[^/?#\s\"]*?-b(\d+)")),
    ("flibusta", re.compile(r"flibusta\.[a-z]+/b/(\d+)")),
    ("wattpad", re.compile(r"wattpad\.com/(?:story/)?(\d{5,})")),
    ("wuxiaclick", re.compile(r"wuxia\.click/novel/([\w-]+)")),
    ("ranobelib", re.compile(r"ranobelib\.me/(?:ru/)?(?:book/)?(\d+--[\w-]+|[a-z][\w-]+)")),
    # Sites whose connectors come later: kept now, matched once those books exist.
    ("ficbook", re.compile(r"ficbook\.net/readfic/([\w-]+)")),
    ("samlib", re.compile(r"samlib\.ru/(\w/[\w.-]+/[\w.-]+?\.shtml)")),
    ("rulate", re.compile(r"rulate\.ru/book/(\d+)")),
    ("royalroad", re.compile(r"royalroad\.com/fiction/(\d+)")),
    ("scribblehub", re.compile(r"scribblehub\.com/series/(\d+)")),
    ("ao3", re.compile(r"archiveofourown\.org/works/(\d+)")),
    ("fanfiction", re.compile(r"fanfiction\.net/s/(\d+)")),
]
BOOKISH_HOSTS = re.compile(r"samlib\.ru|ficbook\.net|rulate\.ru|litmir|rulit\.me|litvek|royallib|royalroad|"
                           r"scribblehub|webnovel|fanfiction\.net|archiveofourown|novelupdates|ranobes|ranobehub")

AUTHOR = r"([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?(?:\s+[А-ЯЁ]\.){0,2})"
QUOTED = r"[«\"„“]([^»\"“”\n]{3,80})[»\"“”]"
TEXT_PATTERNS = [
    re.compile(AUTHOR + r"\s*[-–—:,]?\s*" + QUOTED),                  # Метельский «Унесенный ветром»
    re.compile(QUOTED + r"\s*[-–—(,]\s*" + AUTHOR),                    # «Унесенный ветром» - Метельский
    re.compile(r"(?m)^\s*" + AUTHOR + r"\s*[-–—]\s*([А-ЯЁA-Z][^.!?\n«»\"]{2,60})"),  # Метельский - Унесенный ветром
]


def _post_date(text: str) -> str | None:
    m = re.search(r"(\d{1,2})\s+([А-Яа-я]{3})[а-я]*\s+(\d{4})", text)
    if not m:
        return None
    month = MONTHS.get(m.group(2).lower()[:3])
    return f"{m.group(3)}-{month:02d}-{int(m.group(1)):02d}" if month else None


def extract_mentions(body_html: str) -> list[dict]:
    """Books mentioned in one post: links to book sites, and "Author «Title»" in the text."""
    out = []
    for url in re.findall(r'href="([^"]+)"', body_html):
        url = _html.unescape(url)
        for site, pattern in LINKS:
            m = pattern.search(url)
            if m:
                out.append({"site": site, "sid": m.group(1), "url": url})
                break
        else:
            if BOOKISH_HOSTS.search(url):
                out.append({"url": url})
    text = _html.unescape(re.sub(r"<br\s*/?>|</p>|<p[^>]*>", "\n", body_html))
    text = re.sub(r"<[^>]+>", " ", text)
    for i, pattern in enumerate(TEXT_PATTERNS):
        for m in pattern.finditer(text):
            author, title = (m.group(1), m.group(2)) if i != 1 else (m.group(2), m.group(1))
            title = title.strip(" .,;:-–—")
            if len(title) >= 3 and len(author) >= 3:
                out.append({"title": title, "author": author.strip()})
    return out


def match_open_mentions() -> int:
    """Link stored mentions to books now in the library. Returns how many new links were made."""
    c = db.conn()
    made, last = 0, 0
    while True:
        rows = c.execute("SELECT * FROM mentions WHERE matched=0 AND id>? ORDER BY id LIMIT 2000", (last,)).fetchall()
        if not rows:
            return made
        last = rows[-1]["id"]
        made += _match_rows(c, rows)


def _match_rows(c, rows) -> int:
    made = 0
    for r in rows:
        ids: list[int] = []
        if r["site"] and r["sid"]:
            if r["site"] == "ranobelib" and "--" not in r["sid"]:  # old-style link without the number
                ids = [x[0] for x in c.execute("SELECT id FROM books WHERE site='ranobelib' AND sid LIKE ?",
                                               (f"%--{r['sid']}",))]
            else:
                ids = [x[0] for x in c.execute("SELECT id FROM books WHERE site=? AND sid=?", (r["site"], r["sid"]))]
        elif r["title"] and r["author"]:
            tk = matching.norm_title(r["title"])
            keys = [f"ta:{tk}:{w}" for w in matching.author_words(r["author"])]
            if tk and keys:
                found = {x[0] for x in c.execute(
                    f"SELECT DISTINCT book_id FROM match_keys WHERE key IN ({','.join('?' * len(keys))})", keys)}
                ids = sorted(found) if len(found) <= 5 else []
        if ids:
            for book_id in ids:
                c.execute("INSERT OR IGNORE INTO recommendations(book_id, source, post_url, at) VALUES(?,?,?,?)",
                          (book_id, r["source"], r["post_url"], r["at"]))
                made += 1
            c.execute("UPDATE mentions SET matched=1 WHERE id=?", (r["id"],))
    return made


class KubikusForum(Site):
    id = "kubikus"
    name = "Kubikus forum (recommendations)"
    home = "https://www.kubikus.ru"
    lang = "ru"
    min_interval = 2.0
    note = ("Adds no books of its own: reads the recommendation sections of the forum and marks the books people "
            "recommend. Filter with “Only books recommended on forums”.")
    extra_settings = {"forums": {"label": "Forum section numbers to read", "default": DEFAULT_FORUMS}}

    def _forums(self) -> list[str]:
        return [x.strip() for x in str(self.settings.get("forums") or DEFAULT_FORUMS).split(",") if x.strip()]

    def _topics(self, forum: str, page: int) -> list[tuple[str, str]]:
        p = self.http.get(BASE + "forum.asp", params={"FORUM_ID": forum, "CAT_ID": 5, "whichpage": page})
        seen, out = set(), []
        for tid, cat in re.findall(r'href="topic\.asp\?TOPIC_ID=(\d+)&(?:amp;)?FORUM_ID=\d+&(?:amp;)?CAT_ID=(\d+)', p.text):
            if tid not in seen:
                seen.add(tid)
                out.append((tid, cat))
        return out

    def _read_topic_page(self, forum: str, tid: str, cat: str, page: int) -> tuple[int, int]:
        """Saves mentions from one page of a topic. Returns (mentions found, number of pages in the topic)."""
        url = f"{BASE}topic.asp?TOPIC_ID={tid}&FORUM_ID={forum}&CAT_ID={cat}&whichpage={page}"
        p = self.http.get(url)
        s = p.text
        pages = max([int(x) for x in re.findall(r"whichpage=(\d+)", s)] + [1])
        found = 0
        chunks = s.split("Послано&nbsp;-&nbsp;")
        c = db.conn()
        for i in range(1, len(chunks)):
            before, chunk = chunks[i - 1], chunks[i]
            reply = re.findall(r'name="rep(\d+)"', before[-3000:])
            at = _post_date(chunk[:40].replace("&nbsp;", " "))
            body_start = chunk.find('<hr noshade size="1">')
            if body_start < 0:
                continue
            body = chunk[body_start:]
            end = min([x for x in (body.find('<noindex><font style="font-size: 10px;">'), body.find("</td>")) if x > 0]
                      or [len(body)])
            post_url = url + (f"#rep{reply[-1]}" if reply else "")
            for m in extract_mentions(body[:end]):
                c.execute("INSERT OR IGNORE INTO mentions(source, post_url, at, site, sid, url, title, author) "
                          "VALUES(?,?,?,?,?,?,?,?)", (SOURCE, post_url, at, m.get("site"), m.get("sid"),
                                                      m.get("url"), m.get("title"), m.get("author")))
                found += 1
        return found, pages

    def discover(self, state: dict):
        forums = self._forums()
        done_topics: dict = state.setdefault("topics_read", {})  # topic id -> pages read
        list_pages = 3 if state.get("full_done") else 10_000   # later passes: only recently active topics
        fi = state.get("fi", 0)
        while fi < len(forums):
            forum = forums[fi]
            page = state.get("fpage", 1)
            while page <= list_pages:
                topics = self._topics(forum, page)
                if not topics:
                    break
                for tid, cat in topics:
                    start = max(1, int(done_topics.get(tid, 0)))  # re-read the last page: it may have new posts
                    tp, pages = start, start
                    while tp <= pages:
                        _, pages = self._read_topic_page(forum, tid, cat, tp)
                        done_topics[tid] = tp
                        tp += 1
                        yield []  # lets the worker save progress and pause between pages
                    match_open_mentions()
                page += 1
                state["fpage"] = page
            fi += 1
            state.update(fi=fi, fpage=1)
        state.update(fi=0, fpage=1, full_done=True, last_read=now())

    def details(self, book: dict):
        raise NotImplementedError

    def chapters(self, book: dict):
        return []

    def chapter_text(self, book: dict, chapter):
        return ""
