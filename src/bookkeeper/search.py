"""Turning the filters you pick in the interface into a database query."""
import math
import re

from . import db, tagquery
from . import tags as T
from .db import jload
from .library import AGE_RATINGS

# A book is 18+ if the site says so or it has the (certain) "Adult content" tag.
ADULT_SQL = ("(b.adult = 1 OR b.id IN (SELECT book_id FROM book_tags WHERE tag = 'adult' AND source != 'maybe'))")
# Its age rating: what the site gave, else NC-17 (18+) for 18+ books, else unknown.
AGE_SQL = f"COALESCE(b.age_rating, CASE WHEN {ADULT_SQL} THEN 'NC-17' END)"


def tag_exists(tag_id: str) -> bool:
    return db.conn().execute("SELECT 1 FROM tags WHERE id=?", (tag_id,)).fetchone() is not None


def _found(ids: list[str]) -> bool:
    return bool(ids) and all(T.is_known(i) or tag_exists(i) for i in ids)


def resolve_tag(name: str) -> list[str]:
    """A name typed in the Tags field: a tag, or else a fandom of that name (Naruto → the Naruto fandom)."""
    ids = T.canonical(name)
    if not _found(ids) and not name.lower().startswith(T.FANDOM_PREFIX):
        alt = T.canonical(T.FANDOM_PREFIX + name)
        if _found(alt):
            return alt
    return ids


def resolve_fandom(name: str) -> list[str]:
    """A name typed in the Fandoms field is always a fandom."""
    return T.canonical(name if name.lower().startswith(T.FANDOM_PREFIX) else T.FANDOM_PREFIX + name)


def parse_query(text: str, fandom: bool = False):
    return tagquery.parse(text, exists=tag_exists, resolve=resolve_fandom if fandom else resolve_tag)


def label_in(c, tag_id: str, lang: str = "en") -> str:
    m = _tag_meta(c, tag_id)
    if lang == "ru" and m.get("label_ru"):
        return m["label_ru"]
    if lang == "uk" and (m.get("label_uk") or m.get("label_ru")):
        return m.get("label_uk") or m["label_ru"]
    return m.get("label") or tag_id


def explain_query(text: str, lang: str = "en", fandom: bool = False) -> dict:
    """How a Tags or Fandoms query reads, for the line under the field."""
    c = db.conn()
    node = parse_query(text, fandom)
    names: dict[str, str] = {}

    def label(tag_id):
        if tag_id not in names:
            names[tag_id] = label_in(c, tag_id, lang)
        return names[tag_id]
    terms = [{"text": t.text, "known": t.known, "maybe": t.maybe, "prefix": t.prefix,
              "tags": [{"id": i, "label": label(i)} for i in t.ids]} for t in tagquery.terms(node)]
    return {"text": tagquery.explain(node, label), "terms": terms,
            "unknown": [t["text"] for t in terms if not t["known"]]}


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
                "(b.adult = 1 OR EXISTS(SELECT 1 FROM book_tags x WHERE x.book_id = b.id AND x.tag = 'adult' "
                "AND x.source != 'maybe')) AS adult, "
                "COALESCE(b.age_rating, CASE WHEN b.adult = 1 OR EXISTS(SELECT 1 FROM book_tags x WHERE x.book_id = b.id "
                "AND x.tag = 'adult' AND x.source != 'maybe') THEN 'NC-17' END) AS age_rating, "
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

    # The Tags and Fandoms fields (see tagquery.py). Old saved searches used three lists; they read the same way.
    legacy = tagquery.from_lists(_list(p.get("tags")), _list(p.get("any")), _list(p.get("not")))
    for text, fandom in (((p.get("tq") or "").strip() or legacy, False), ((p.get("fq") or "").strip(), True)):
        if text:
            sql, a = tagquery.to_sql(parse_query(text, fandom))
            where.append(sql)
            args += a

    orient = _list(p.get("orient"))
    if orient:
        where.append(f"b.id IN (SELECT book_id FROM book_tags WHERE source != 'maybe' AND tag IN "
                     f"({','.join('?' * len(orient))}))")
        args += orient
    if p.get("kind") in ("fanfic", "original"):
        fanfic = "b.id IN (SELECT book_id FROM book_tags WHERE tag = 'fanfiction' AND source != 'maybe')"
        where.append(fanfic if p.get("kind") == "fanfic" else f"NOT {fanfic}")
    ages = _list(p.get("age"))
    if ages:
        parts = []
        if "unknown" in ages:
            parts.append(f"{AGE_SQL} IS NULL")
        known = [a for a in ages if a in AGE_RATINGS]
        if known:
            parts.append(f"{AGE_SQL} IN ({','.join('?' * len(known))})")
            args += known
        if parts:
            where.append("(" + " OR ".join(parts) + ")")

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
    v = _num(p.get("stale"))
    if v:  # not updated for at least this many days (books with no date are left out)
        where.append("b.updated_at IS NOT NULL AND b.updated_at < date('now', ?)")
        args.append(f"-{int(v)} days")

    # 18+ books are shown unless you hide them (the switch in the filters, saved as the hide_adult setting).
    # adult=hide / adult=only in the address override the switch; adult=1 (older saved searches) means "show".
    adult = str(p.get("adult") or "")
    adult_sql = ADULT_SQL
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
        f"SELECT bt.book_id, bt.tag, GROUP_CONCAT(DISTINCT bt.source) AS sources, MAX(bt.score) AS score, t.label, "
        f"t.label_ru, t.label_uk, t.category, t.known, t.books FROM book_tags bt JOIN tags t ON t.id = bt.tag "
        f"WHERE bt.book_id IN ({','.join('?' * len(ids))}) GROUP BY bt.book_id, bt.tag", ids).fetchall()
    by_book: dict[int, list] = {}
    for r in rows:
        if r["category"] == "narration" and r["tag"] in T.POV_TAGS:
            continue  # shown separately as the narration badge
        sources = r["sources"].split(",")
        maybe = sources == ["maybe"]
        by_book.setdefault(r["book_id"], []).append(
            {"id": r["tag"], "label": r["label"], "label_ru": r["label_ru"], "label_uk": r["label_uk"],
             "category": r["category"], "sources": sources, "known": r["known"], "count": r["books"],
             "maybe": maybe, "score": r["score"] if maybe else None})
    for b in books:
        tags = by_book.get(b["id"], [])
        tags.sort(key=lambda t: (2 if t["maybe"] else 0 if "site" in t["sources"] or "user" in t["sources"] else 1,
                                 0 if t["known"] else 1, -(t["score"] or 0), -(t["count"] or 0)))
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
        "SELECT bt.tag, bt.source, bt.raw, bt.score, t.label, t.label_ru, t.label_uk, t.category, t.known, t.books "
        "FROM book_tags bt JOIN tags t ON t.id = bt.tag WHERE bt.book_id=? ORDER BY t.category, t.label",
        (book_id,)).fetchall()
    tags: dict[str, dict] = {}
    possible = []
    for t in tag_rows:
        base = {"id": t["tag"], "label": t["label"], "label_ru": t["label_ru"], "label_uk": t["label_uk"],
                "category": t["category"], "known": t["known"], "count": t["books"]}
        if t["source"] == "maybe":
            possible.append({**base, "score": t["score"], "why": t["raw"]})
            continue
        e = tags.setdefault(t["tag"], {**base, "sources": [], "raw": []})
        e["sources"].append(t["source"])
        if t["raw"] and t["raw"] not in e["raw"]:
            e["raw"].append(t["raw"])
    d["tags"] = list(tags.values())
    d["possible_tags"] = sorted((p for p in possible if p["id"] not in tags), key=lambda p: -(p["score"] or 0))
    age = c.execute(f"SELECT {AGE_SQL} FROM books b WHERE b.id=?", (book_id,)).fetchone()
    d["age_rating"] = age[0] if age else None
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


def tag_suggestions(q: str, limit: int = 20, category: str | None = None) -> list[dict]:
    """Tags for the autocomplete: names in any language, aliases of the shared tags, and the site labels in the
    library. Best matches first: a name that starts with what you typed, then an alias that does, then the rest."""
    c = db.conn()
    q = (q or "").strip().lower().replace("ё", "е")
    cat_sql, cat_args = (" AND category = ?", [category]) if category else ("", [])
    if not q:
        rows = c.execute(f"SELECT * FROM tags WHERE books > 0{cat_sql} ORDER BY known DESC, books DESC LIMIT ?",
                         (*cat_args, limit))
        return [dict(r) for r in rows]
    found: dict[str, dict] = {}
    for tid, alias, rank in T.suggest(q, category, limit=limit * 2):
        found[tid] = {"id": tid, "rank": rank, "matched": alias}
    like, start = f"%{q}%", f"{q}%"
    rows = c.execute(
        "SELECT id, ulower(label) LIKE ? OR ulower(label_ru) LIKE ? OR ulower(label_uk) LIKE ? OR id LIKE ? AS starts "
        "FROM tags WHERE (ulower(label) LIKE ? OR ulower(label_ru) LIKE ? OR ulower(label_uk) LIKE ? OR id LIKE ?)"
        f"{cat_sql} ORDER BY books DESC LIMIT ?", (start, start, start, start, like, like, like, like, *cat_args, limit * 3))
    for r in rows:
        rank = 0 if r["starts"] else 2
        if r["id"] not in found or found[r["id"]]["rank"] > rank:
            found[r["id"]] = {"id": r["id"], "rank": rank, "matched": None}
    if not found:
        return []
    meta = {r["id"]: dict(r) for r in c.execute(
        f"SELECT * FROM tags WHERE id IN ({','.join('?' * len(found))})", list(found))}
    out = []
    for tid, f in found.items():
        m = meta.get(tid) or {"id": tid, **T.info(tid), "known": int(T.is_known(tid)), "books": 0}
        names = {(m.get(k) or "").lower().replace("ё", "е") for k in ("label", "label_ru", "label_uk")} | {tid}
        out.append({**m, "rank": -1 if q in names else f["rank"], "matched": f["matched"]})
    # What you typed exactly, then the shared tags (they have translations and a family tree), then site labels.
    out.sort(key=lambda t: (t["rank"] >= 0, 0 if t.get("known") or t.get("category") == "fandom" else 1,
                            t["rank"], -(t.get("books") or 0)))
    return out[:limit]


_NEEDS_QUOTES = re.compile(r'[\s()|&,«»]|^[-!?−]|\*$')


def _token(name: str) -> str:
    return f'"{name}"' if _NEEDS_QUOTES.search(name) else name


def insert_text(o: dict, lang: str = "en", fandom: bool = False) -> str:
    """What the autocomplete writes into the field for a tag: its name in your tag language when that name means
    this tag and nothing else, else its id."""
    resolve = resolve_fandom if fandom else resolve_tag
    names = []
    if lang in ("ru", "uk"):
        names.append(o.get(f"label_{lang}") or (o.get("label_ru") if lang == "uk" else None))
    label = o.get("label") or ""
    if " / " not in label and len(label) <= 24:
        names.append(label)
    for name in names:
        if name and '"' not in name and resolve(name) == [o["id"]]:
            return _token(name)
    return _token(o["id"])


def complete(text: str, lang: str = "en", fandom: bool = False, quoted: bool = False, limit: int = 12) -> list[dict]:
    """Suggestions for what is being typed at the end of `text` (the field sends the words since the last bracket,
    | or & ). The last one to three words are tried, so "slow bu" finds Slow-burn romance and "romance ha" finds
    Harem. `replace_words` says how many of the last words a suggestion replaces."""
    category = "fandom" if fandom else None
    words = text.split()
    if not words:
        opts = tag_suggestions("", limit, category)
        return [{**o, "replace_words": 0, "insert": insert_text(o, lang, fandom),
                 "description": T.describe(o["id"])} for o in opts]
    if quoted:
        cands = [(len(words), " ".join(words))]
    else:
        cands = [(n, " ".join(words[-n:])) for n in range(min(3, len(words)), 0, -1)]
    out, seen = [], set()
    for n, part in cands:
        for o in tag_suggestions(part, limit, category):
            if o["id"] in seen:
                continue
            # A longer phrase only counts when it starts a shared tag's name: "romance f" shouldn't offer the
            # site label "romance fantasy" in place of the Romance you already typed.
            if n > 1 and not quoted and (o["rank"] > 1 or not (o.get("known") or o.get("category") == "fandom")):
                continue
            seen.add(o["id"])
            out.append({**o, "replace_words": n, "insert": insert_text(o, lang, fandom),
                        "description": T.describe(o["id"])})
    return out[:limit]


def all_tags() -> list[dict]:
    """The shared tags by category with their book counts, plus fandoms and the most common site labels."""
    c = db.conn()
    rows = [dict(r) for r in c.execute(
        "SELECT id, label, label_ru, label_uk, category, books, known FROM tags WHERE known = 1 OR "
        "(category = 'fandom' AND books > 0) ORDER BY books DESC")]
    have = {r["id"] for r in rows}
    for tid in T.all_ids():  # built-in tags no book has yet
        if tid not in have:
            rows.append({"id": tid, **T.info(tid), "books": 0, "known": 1})
    rows += [dict(r) for r in c.execute(
        "SELECT id, label, label_ru, label_uk, category, books, known FROM tags WHERE known = 0 AND "
        "category != 'fandom' AND books >= 5 ORDER BY books DESC LIMIT 300")]
    return rows


# ---------------------------------------------------------------- tag pages
def _tag_meta(c, tag_id: str) -> dict:
    row = c.execute("SELECT * FROM tags WHERE id=?", (tag_id,)).fetchone()
    i = T.info(tag_id)
    d = dict(row) if row else {"id": tag_id, "label": i["label"], "label_ru": i.get("label_ru"),
                               "label_uk": i.get("label_uk"), "category": i["category"],
                               "known": int(T.is_known(tag_id)), "books": 0}
    d["description"] = T.describe(tag_id)
    return d


def _brief(c, ids) -> list[dict]:
    out = []
    for t in ids:
        m = _tag_meta(c, t)
        out.append({k: m.get(k) for k in ("id", "label", "label_ru", "label_uk", "category", "books", "description")})
    return out


def tag_brief(tag_id: str) -> dict:
    """What the hover card shows."""
    c = db.conn()
    d = _tag_meta(c, tag_id)
    d["aliases"] = T.aliases(tag_id)[:8]
    d["parents"] = _brief(c, T.direct_parents(tag_id))
    d["children"] = len(T.children(tag_id))
    d["possible"] = c.execute("SELECT COUNT(DISTINCT book_id) FROM book_tags WHERE tag=? AND source='maybe'",
                              (tag_id,)).fetchone()[0]
    return d


def tag_page(tag_id: str) -> dict:
    """Everything about one tag: names, aliases, family tree, related tags and anti-tags."""
    c = db.conn()
    d = tag_brief(tag_id)
    d["aliases"] = T.aliases(tag_id)
    d["combined"] = [{"label": label, "with": _brief(c, others)} for label, others in T.combined(tag_id)]
    d["seen_as"] = [dict(r) for r in c.execute(
        "SELECT raw, COUNT(DISTINCT book_id) AS books FROM book_tags WHERE tag=? AND source='site' AND raw IS NOT NULL "
        "GROUP BY lower(raw) ORDER BY books DESC LIMIT 40", (tag_id,))]
    d["sites"] = [dict(r) for r in c.execute(
        "SELECT b.site, COUNT(DISTINCT b.id) AS books FROM book_tags bt JOIN books b ON b.id = bt.book_id "
        "WHERE bt.tag=? AND bt.source != 'maybe' GROUP BY b.site ORDER BY books DESC", (tag_id,))]
    d["parents"] = _brief(c, T.direct_parents(tag_id))
    d["ancestors"] = _brief(c, [t for t in T.ancestors(tag_id) if t not in T.direct_parents(tag_id)])

    def tree(nodes):
        return [{**_brief(c, [n["id"]])[0], "children": tree(n["children"])} for n in nodes]
    d["children_tree"] = tree(T.child_tree(tag_id))
    family = {tag_id, *T.ancestors(tag_id), *T.descendants(tag_id)}
    d["anti"] = _brief(c, T.anti(tag_id))
    related, rarely = _cooccurrence(c, tag_id, family | set(T.anti(tag_id)))
    d["related"], d["rarely"] = related, rarely
    # Label fixes (see labels.py): this label's own fix, and the labels you fixed to mean this tag.
    fx, k = T.fixes(), T.key(d.get("label") or tag_id)
    d["fixable"] = not d.get("known") and d.get("category") == "other"
    d["fix"] = next(({"label": n, "tags": _brief(c, ids), "hidden": not ids, "separate": ids == [T.own_id(n)]}
                     for n, ids in fx.items() if T.key(n) == k), None)
    d["fixes_here"] = [{"label": n, "tags": _brief(c, ids), "hidden": False, "separate": False}
                       for n, ids in fx.items() if tag_id in ids and T.key(n) != k]
    fixed = {T.key(n) for n in fx}
    for s in d["seen_as"]:
        s["fixed"] = T.key(s["raw"]) in fixed
    return d


def _cooccurrence(c, tag_id: str, skip: set[str]) -> tuple[list[dict], list[dict]]:
    """Tags that appear with this one far more often than chance (related), and common tags that almost never do."""
    n_x = c.execute("SELECT COUNT(DISTINCT book_id) FROM book_tags WHERE tag=? AND source != 'maybe'",
                    (tag_id,)).fetchone()[0]
    total = c.execute("SELECT COUNT(DISTINCT book_id) FROM book_tags WHERE source != 'maybe'").fetchone()[0]
    if not n_x or not total:
        return [], []
    together = {r[0]: r[1] for r in c.execute(
        "WITH x AS (SELECT DISTINCT book_id FROM book_tags WHERE tag=? AND source != 'maybe') "
        "SELECT bt.tag, COUNT(DISTINCT bt.book_id) FROM book_tags bt JOIN x ON x.book_id = bt.book_id "
        "WHERE bt.source != 'maybe' AND bt.tag != ? GROUP BY bt.tag", (tag_id, tag_id))}
    counts = {r[0]: r[1] for r in c.execute("SELECT id, books FROM tags WHERE books > 0")}
    # Only shared tags (and fandoms): one-off site labels such as character names would drown the list.
    shared = {t for t in counts if T.is_known(t) or t.startswith(T.FANDOM_PREFIX)}
    related = []
    for t, n in together.items():
        n_y = counts.get(t) or 0
        if t in skip or t not in shared or not n_y or n < max(3, 0.03 * n_x):
            continue
        lift = (n / n_x) / (n_y / total)
        if lift >= 1.5:
            related.append((t, n, lift))
    related.sort(key=lambda x: -(x[1] / n_x) * math.log2(x[2]))
    rarely = []
    for t, n_y in counts.items():
        if t in skip or t == tag_id or not T.is_known(t) or T.info(t)["category"] == "fandom":
            continue
        expected = n_x * n_y / total
        if expected >= 15 and together.get(t, 0) / expected <= 0.2:
            rarely.append((t, together.get(t, 0), expected))
    rarely.sort(key=lambda x: x[1] / x[2])

    def pack(items):
        out = []
        for t, n, _ in items[:15]:
            b = _brief(c, [t])[0]
            b["together"] = n
            b["share"] = round(100 * n / n_x)
            out.append(b)
        return out
    return pack(related), pack(rarely[:10])
