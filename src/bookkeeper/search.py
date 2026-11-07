"""Turning the filters you pick in the interface into a database query."""
import re

from . import db
from . import tags as T
from .db import jload

SORTS = {
    "popularity": "COALESCE(b.popularity, -1) {d}, COALESCE(b.pop_raw, -1) {d}",
    "rating": "COALESCE(b.rating, -1) {d}, COALESCE(b.votes, 0) {d}",
    "updated": "COALESCE(b.updated_at, '') {d}",
    "added": "b.added_at {d}, b.id {d}",
    "words": "COALESCE(b.words, -1) {d}",
    "chapters": "COALESCE(b.chapters, -1) {d}",
    "likes": "COALESCE(b.likes, -1) {d}",
    "views": "COALESCE(b.views, -1) {d}",
    "title": "b.title COLLATE NOCASE {d}",
    "relevance": "fts.rank",
    "random": "random()",
}

LIST_COLUMNS = ("b.id, b.site, b.url, b.title, b.authors, b.cover, b.lang, b.status, b.chapters, b.words, b.rating, "
                "b.votes, b.likes, b.views, b.popularity, b.pov, b.pov_source, b.narrator, b.access, "
                "(b.adult = 1 OR EXISTS(SELECT 1 FROM book_tags x WHERE x.book_id = b.id AND x.tag = 'adult')) AS adult, "
                "b.updated_at, b.work_id, b.is_translation, b.description, u.shelf, u.favorite")


def _list(value) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(x) for x in value if str(x)]
    return [x for x in str(value or "").split(",") if x]


def _num(value):
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def build_where(p: dict) -> tuple[str, list, str, list]:
    """Returns (joins, join args, where clause, where args)."""
    joins, jargs, where, args = "", [], ["1=1"], []
    q = (p.get("q") or "").strip()
    if q:
        terms = re.findall(r"\w+", q)
        if terms:
            joins += " JOIN (SELECT rowid AS id, rank FROM books_fts WHERE books_fts MATCH ?) fts ON fts.id = b.id"
            jargs.append(" ".join(f'"{t}"*' for t in terms))

    povs = _list(p.get("pov"))
    if povs:
        conds = []
        for v in povs:
            if v == "none":
                conds.append("b.pov IS NULL")
            else:
                conds.append("b.pov = ?")
                args.append(v)
        where.append("(" + " OR ".join(conds) + ")")
    if p.get("pov_source"):
        where.append(f"b.pov_source IN ({','.join('?' * len(_list(p['pov_source'])))})")
        args += _list(p["pov_source"])
    if p.get("narrator"):
        where.append(f"b.narrator IN ({','.join('?' * len(_list(p['narrator'])))})")
        args += _list(p["narrator"])

    include = _list(p.get("tags"))
    if include:
        where.append("b.id IN (" + " INTERSECT ".join("SELECT book_id FROM book_tags WHERE tag=?" for _ in include) + ")")
        args += include
    anyof = _list(p.get("any"))
    if anyof:
        where.append(f"b.id IN (SELECT book_id FROM book_tags WHERE tag IN ({','.join('?' * len(anyof))}))")
        args += anyof
    exclude = _list(p.get("not"))
    if exclude:
        where.append(f"b.id NOT IN (SELECT book_id FROM book_tags WHERE tag IN ({','.join('?' * len(exclude))}))")
        args += exclude

    for key, col in (("sites", "b.site"), ("lang", "b.lang"), ("status", "b.status"), ("access", "b.access")):
        values = _list(p.get(key))
        if values:
            parts = []
            if "unknown" in values:
                parts.append(f"{col} IS NULL")
                values = [v for v in values if v != "unknown"]
            if values:
                parts.append(f"{col} IN ({','.join('?' * len(values))})")
                args += values
            where.append("(" + " OR ".join(parts) + ")")

    if p.get("origin") == "original":
        where.append("b.is_translation = 0")
    elif p.get("origin") == "translation":
        where.append("b.is_translation = 1")

    for key, sql in (("min_words", "b.words >= ?"), ("max_words", "b.words <= ?"),
                     ("min_chapters", "b.chapters >= ?"), ("max_chapters", "b.chapters <= ?"),
                     ("min_rating", "b.rating >= ?"), ("min_likes", "b.likes >= ?")):
        v = _num(p.get(key))
        if v is not None:
            where.append(sql)
            args.append(v)
    v = _num(p.get("updated_within"))
    if v:
        where.append("b.updated_at >= date('now', ?)")
        args.append(f"-{int(v)} days")

    # 18+ books are shown unless you hide them (the switch in the filters, saved as the hide_adult setting).
    # adult=hide / adult=only in the address override the switch; adult=1 (older saved searches) means "show".
    adult = str(p.get("adult") or "")
    adult_sql = "(b.adult = 1 OR b.id IN (SELECT book_id FROM book_tags WHERE tag='adult'))"
    if adult == "only":
        where.append(adult_sql)
    elif adult in ("hide", "0") or (not adult and db.get_setting("hide_adult", False)):
        where.append(f"NOT {adult_sql}")
    shelf = p.get("shelf") or "hide-hidden"
    if shelf == "hide-hidden":
        where.append("(u.shelf IS NULL OR u.shelf != 'hidden')")
    elif shelf == "unread":
        where.append("(u.shelf IS NULL OR u.shelf NOT IN ('read', 'hidden', 'dropped'))")
    elif shelf == "favorite":
        where.append("u.favorite = 1")
    elif shelf in ("want", "reading", "read", "dropped", "hidden"):
        where.append("u.shelf = ?")
        args.append(shelf)
    if p.get("recommended"):
        where.append("b.id IN (SELECT book_id FROM recommendations)")
    if str(p.get("dedupe", "1")) == "1":
        where.append("b.is_primary = 1")
    return joins, jargs, " AND ".join(where), args


def search(p: dict) -> dict:
    c = db.conn()
    joins, jargs, where, args = build_where(p)
    sort = p.get("sort") or ("relevance" if p.get("q") else "popularity")
    if sort == "relevance" and not p.get("q"):
        sort = "popularity"
    direction = "ASC" if p.get("order") == "asc" else "DESC"
    order = SORTS.get(sort, SORTS["popularity"]).format(d=direction)
    page = max(1, int(_num(p.get("page")) or 1))
    per_page = min(100, max(10, int(_num(p.get("per_page")) or 40)))
    base = f"FROM books b LEFT JOIN user_books u ON u.book_id = b.id {joins} WHERE {where}"
    total = c.execute(f"SELECT COUNT(*) FROM (SELECT 1 {base} LIMIT 10001)", [*jargs, *args]).fetchone()[0]
    rows = c.execute(f"SELECT {LIST_COLUMNS} {base} ORDER BY {order}, b.id LIMIT ? OFFSET ?",
                     [*jargs, *args, per_page, (page - 1) * per_page]).fetchall()
    books = [card(r) for r in rows]
    _attach_tags(books)
    _attach_copies(books)
    return {"total": total, "total_capped": total > 10000, "page": page, "per_page": per_page, "books": books}


def card(r) -> dict:
    d = dict(r)
    d["authors"] = jload(d["authors"], [])
    desc = d.pop("description", None) or ""
    d["snippet"] = desc[:280] + ("…" if len(desc) > 280 else "")
    d["favorite"] = bool(d.get("favorite"))
    return d


def _attach_tags(books: list[dict], limit: int = 12):
    if not books:
        return
    ids = [b["id"] for b in books]
    rows = db.conn().execute(
        f"SELECT bt.book_id, bt.tag, GROUP_CONCAT(DISTINCT bt.source) AS sources, t.label, t.label_ru, t.label_uk, t.category, "
        f"t.known, t.books FROM book_tags bt JOIN tags t ON t.id = bt.tag WHERE bt.book_id IN "
        f"({','.join('?' * len(ids))}) GROUP BY bt.book_id, bt.tag", ids).fetchall()
    by_book: dict[int, list] = {}
    for r in rows:
        if r["category"] == "narration" and r["tag"] in T.POV_TAGS:
            continue  # shown separately as the narration badge
        by_book.setdefault(r["book_id"], []).append(
            {"id": r["tag"], "label": r["label"], "label_ru": r["label_ru"], "label_uk": r["label_uk"], "category": r["category"],
             "sources": r["sources"].split(","), "known": r["known"], "count": r["books"]})
    for b in books:
        tags = by_book.get(b["id"], [])
        tags.sort(key=lambda t: (0 if "site" in t["sources"] or "user" in t["sources"] else 1,
                                 0 if t["known"] else 1, -(t["count"] or 0)))
        b["tags"] = tags[:limit]
        b["tags_total"] = len(tags)


def _attach_copies(books: list[dict]):
    works = [b["work_id"] for b in books if b.get("work_id")]
    if not works:
        for b in books:
            b["copies"] = []
        return
    rows = db.conn().execute(f"SELECT id, work_id, site, url FROM books WHERE work_id IN ({','.join('?' * len(works))})",
                             works).fetchall()
    by_work: dict[int, list] = {}
    for r in rows:
        by_work.setdefault(r["work_id"], []).append({"id": r["id"], "site": r["site"], "url": r["url"]})
    for b in books:
        b["copies"] = [x for x in by_work.get(b.get("work_id"), []) if x["id"] != b["id"]]


def book_detail(book_id: int) -> dict | None:
    c = db.conn()
    r = c.execute("SELECT b.*, u.shelf, u.favorite, u.pov AS user_pov, u.note FROM books b "
                  "LEFT JOIN user_books u ON u.book_id=b.id WHERE b.id=?", (book_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    for k in ("authors", "alt_titles"):
        d[k] = jload(d[k], [])
    d["extra"] = jload(d["extra"], {})
    d["favorite"] = bool(d.get("favorite"))
    tag_rows = c.execute(
        "SELECT bt.tag, bt.source, bt.raw, t.label, t.label_ru, t.label_uk, t.category, t.known, t.books FROM book_tags bt "
        "JOIN tags t ON t.id = bt.tag WHERE bt.book_id=? ORDER BY t.category, t.label", (book_id,)).fetchall()
    tags: dict[str, dict] = {}
    for t in tag_rows:
        e = tags.setdefault(t["tag"], {"id": t["tag"], "label": t["label"], "label_ru": t["label_ru"], "label_uk": t["label_uk"],
                                       "category": t["category"], "known": t["known"], "count": t["books"],
                                       "sources": [], "raw": []})
        e["sources"].append(t["source"])
        if t["raw"] and t["raw"] not in e["raw"]:
            e["raw"].append(t["raw"])
    d["tags"] = list(tags.values())
    a = c.execute("SELECT * FROM analysis WHERE book_id=?", (book_id,)).fetchone()
    if a:
        a = dict(a)
        a["details"] = jload(a["details"], {})
    d["analysis"] = a
    d["copies"] = []
    if d.get("work_id"):
        d["copies"] = [dict(x) for x in c.execute(
            "SELECT id, site, url, title, pov, pov_source FROM books WHERE work_id=? AND id!=?",
            (d["work_id"], book_id))]
    d["recommendations"] = [dict(x) for x in c.execute(
        "SELECT source, post_url, at FROM recommendations WHERE book_id=? ORDER BY at DESC LIMIT 20", (book_id,))]
    d["downloads"] = [dict(x) for x in c.execute(
        "SELECT id, fmt, state, progress, total, file, error, created_at FROM downloads WHERE book_id=? "
        "ORDER BY id DESC LIMIT 10", (book_id,))]
    d["queued"] = bool(c.execute("SELECT 1 FROM queue WHERE book_id=?", (book_id,)).fetchone())
    return d


def tag_suggestions(q: str, limit: int = 20) -> list[dict]:
    c = db.conn()
    q = (q or "").strip().lower()
    if not q:
        rows = c.execute("SELECT * FROM tags WHERE books > 0 ORDER BY known DESC, books DESC LIMIT ?", (limit,))
    else:
        like = f"%{q}%"
        rows = c.execute(
            "SELECT * FROM tags WHERE (ulower(label) LIKE ? OR ulower(label_ru) LIKE ? OR ulower(label_uk) LIKE ? OR id LIKE ?) "
            "ORDER BY (ulower(label) LIKE ? OR ulower(label_ru) LIKE ? OR ulower(label_uk) LIKE ?) DESC, known DESC, books DESC "
            "LIMIT ?", (like, like, like, like, f"{q}%", f"{q}%", f"{q}%", limit))
    return [dict(r) for r in rows]
