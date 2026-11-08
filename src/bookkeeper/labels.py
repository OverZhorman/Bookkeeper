"""Fixing site labels: say once what a label means, and every book with it follows.

A fix maps a label as the sites write it (any spelling: «Попаданиевдругоймир», «#попаданиевдругоймир») onto
shared tags, hides it ([]), or keeps it as a tag of its own (for a label Bookkeeper maps to the wrong tag).
Fixes live in my_tags.toml's [fixes] table and apply to the books you have and to every book that arrives later.
Books keep their labels as written (books.labels), so any fix can be undone."""
from . import db, library, search
from . import tags as T
from .db import jload

PAGE = 50
# Tags a label hardly ever means, even when its books all have them (every Author.Today book is a "Novel").
_NOT_MEANINGS = {"narration", "format", "origin"}


def _rows_by_id(c, ids, sql: str) -> list:
    out, ids = [], list(ids)
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        out += c.execute(sql.format(q=",".join("?" * len(chunk))), chunk).fetchall()
    return out


def _books_with(c, label: str) -> set[int]:
    """Books whose site labels include this label, written any way (using the fixes as they are now)."""
    k = T.key(label)
    tag_ids = set(T.canonical(label))
    tag_ids |= {r[0] for r in c.execute("SELECT id FROM tags WHERE known = 0") if T.key(r[0]) == k}
    if tag_ids:
        books = {r[0] for r in _rows_by_id(c, tag_ids, "SELECT DISTINCT book_id FROM book_tags "
                                                      "WHERE source = 'site' AND tag IN ({q})")}
        rows = _rows_by_id(c, books, "SELECT id, labels FROM books WHERE id IN ({q})")
    else:  # a hidden label has no tag to start from: look through every book's labels
        rows = c.execute("SELECT id, labels FROM books WHERE labels IS NOT NULL AND labels != '[]'").fetchall()
    return {r[0] for r in rows if any(T.key(x) == k for x in jload(r[1], []) or [])}


def _context(c) -> dict:
    """What the suggestions need, worked out once per page."""
    names = []
    for k, ids in T.names().items():
        known = [i for i in ids if T.is_known(i)]
        if len(k) >= 4 and known:
            names.append((k, known))
    counts = {r[0]: r[1] for r in c.execute("SELECT id, books FROM tags WHERE known = 1 AND books > 0")}
    total = c.execute("SELECT COUNT(*) FROM books").fetchone()[0] or 1
    return {"names": names, "counts": counts, "total": total}


def _by_name(label: str, names) -> list[tuple[str, int]]:
    """Shared tags whose name or alias hides in the label: «попаданиевдругоймир» has «попада(нец)» → Isekai."""
    k = T.key(label)
    best: dict[str, int] = {}
    for nk, ids in names:
        if nk in k:
            score = len(nk)
        elif len(k) >= 4 and k in nk and len(k) >= 0.6 * len(nk):  # most of a longer name, not one word of it
            score = len(k) - 1
        elif len(nk) >= 7 and nk[:-3] in k:  # without its ending: попаданец → попада
            score = len(nk) - 4
        else:
            continue
        if score >= 5:
            for i in ids:
                best[i] = max(best.get(i, 0), score)
    return sorted(best.items(), key=lambda kv: -kv[1])


def _by_company(c, tag_id: str, ctx: dict) -> list[tuple[str, float]]:
    """Shared tags most books with this label also have, far more often than books in general."""
    rows = c.execute(
        "SELECT bt.tag, COUNT(DISTINCT bt.book_id) FROM book_tags bt JOIN (SELECT DISTINCT book_id FROM book_tags "
        "WHERE tag = ? AND source = 'site') x ON x.book_id = bt.book_id WHERE bt.source IN ('site', 'user') "
        "AND bt.tag != ? GROUP BY bt.tag", (tag_id, tag_id)).fetchall()
    n_x = c.execute("SELECT COUNT(DISTINCT book_id) FROM book_tags WHERE tag = ? AND source = 'site'",
                    (tag_id,)).fetchone()[0]
    out = []
    for t, n in rows:
        base = ctx["counts"].get(t)
        if not base or n < 2 or not n_x or T.info(t)["category"] in _NOT_MEANINGS:
            continue
        share = n / n_x
        if share >= 0.5 and share / (base / ctx["total"]) >= 3:
            out.append((t, share))
    return sorted(out, key=lambda x: -x[1])


def suggestions(label: str, tag_id: str | None = None, ctx: dict | None = None, limit: int = 4) -> list[dict]:
    """Likely meanings of a label, best first, each with why."""
    c = db.conn()
    ctx = ctx or _context(c)
    found: dict[str, dict] = {}
    for t, _ in _by_name(label, ctx["names"])[:3]:
        found.setdefault(t, {"why": "name"})
    if tag_id:
        for t, share in _by_company(c, tag_id, ctx)[:3]:
            found.setdefault(t, {"why": "company", "share": round(share * 100)})
    return [{**search._brief(c, [t])[0], **why} for t, why in list(found.items())[:limit]]


def unrecognized(site: str | None = None, q: str = "", offset: int = 0, limit: int = PAGE) -> dict:
    """Site labels that aren't shared tags, most common first, with suggestions for what each means. Spellings
    that differ only in spaces, case or symbols («сложные отношения», «#СложныеОтношения») are one row: one fix
    covers them all."""
    c = db.conn()
    if site:
        rows = c.execute("SELECT t.id, t.label, COUNT(DISTINCT bt.book_id) AS books FROM tags t JOIN book_tags bt "
                         "ON bt.tag = t.id AND bt.source = 'site' JOIN books b ON b.id = bt.book_id "
                         "WHERE t.known = 0 AND t.category = 'other' AND b.site = ? GROUP BY t.id", (site,)).fetchall()
    else:
        rows = c.execute("SELECT id, label, books FROM tags WHERE known = 0 AND category = 'other' AND books > 0").fetchall()
    groups: dict[str, dict] = {}
    for r in rows:
        k = T.key(r["id"])
        if not k:
            continue
        g = groups.setdefault(k, {"key": k, "ids": [], "spellings": [], "books": 0, "top": -1})
        g["ids"].append(r["id"])
        g["spellings"].append(r["label"])
        g["books"] += r["books"]
        if r["books"] > g["top"]:
            g.update(top=r["books"], id=r["id"], label=r["label"])
    items = list(groups.values())
    if q.strip():
        ql, qk = q.strip().lower().replace("ё", "е"), T.key(q)
        items = [g for g in items if (qk and qk in g["key"]) or any(ql in s.lower().replace("ё", "е")
                                                                     for s in g["spellings"])]
    items.sort(key=lambda g: (-g["books"], g["key"]))
    page = items[offset:offset + limit]
    by_id = {i: g for g in page for i in g["ids"]}
    for g in page:
        g["sites"] = {}
    for r in _rows_by_id(c, by_id, "SELECT bt.tag, b.site, COUNT(DISTINCT b.id) FROM book_tags bt "
                                   "JOIN books b ON b.id = bt.book_id WHERE bt.source = 'site' AND bt.tag IN ({q}) "
                                   "GROUP BY bt.tag, b.site"):
        sites = by_id[r[0]]["sites"]
        sites[r[1]] = sites.get(r[1], 0) + r[2]
    ctx = _context(c)
    out = []
    for g in page:
        out.append({"key": g["key"], "id": g["id"], "label": g["label"], "books": g["books"],
                    "spellings": [s for s in dict.fromkeys(g["spellings"]) if s != g["label"]],
                    "sites": [{"site": s, "books": n} for s, n in sorted(g["sites"].items(), key=lambda x: -x[1])],
                    "suggestions": suggestions(g["label"], g["id"], ctx)})
    return {"total": len(items), "books": sum(g["books"] for g in items), "offset": offset, "labels": out}


def current_fix(label: str) -> dict | None:
    k = T.key(label)
    for name, ids in T.fixes().items():
        if T.key(name) == k:
            return {"label": name, "tags": search._brief(db.conn(), ids), "hidden": not ids}
    return None


def fix(label: str, tag_ids: list[str] | None, separate: bool = False) -> dict:
    """Say what a site label means, for every book with it: tag_ids None undoes the fix, [] hides the label,
    separate=True keeps it as a tag of its own. Returns how many books changed."""
    label = (label or "").strip()
    if not T.key(label):
        raise ValueError("No label given.")
    c = db.conn()
    own = T.own_id(label)
    if separate:
        tag_ids = [own]
    if tag_ids is not None:
        tag_ids = list(dict.fromkeys(t for t in tag_ids if t))
        for t in tag_ids:
            if t != own and not (T.is_known(t) or search.tag_exists(t)):
                raise ValueError(f"There's no tag “{t}”.")
    affected = _books_with(c, label)
    # Labels you fixed to mean this one follow it: A → B, then B → Isekai makes A → Isekai too.
    follow: dict[str, list[str]] = {}
    if tag_ids is not None and tag_ids != [own]:
        for name, ids in T.fixes().items():
            if T.key(name) != T.key(label) and own in ids:
                follow[name] = list(dict.fromkeys(x for t in ids for x in (tag_ids if t == own else [t])))
                affected |= _books_with(c, name)
    T.set_fix(label, tag_ids)
    for name, ids in follow.items():
        T.set_fix(name, ids)
    T.reload()
    library.retag_books(affected)
    return {"label": label, "books": len(affected), "undone": tag_ids is None, "hidden": tag_ids == [],
            "separate": tag_ids == [own], "tags": search._brief(c, tag_ids or [])}


def my_fixes() -> list[dict]:
    """Your label fixes, with how many books have each label, most books first."""
    c = db.conn()
    fx = T.fixes()
    counts = {T.key(name): 0 for name in fx}
    if counts:
        for (labels,) in c.execute("SELECT labels FROM books WHERE labels IS NOT NULL AND labels != '[]'"):
            for k in {T.key(x) for x in jload(labels, []) or []} & counts.keys():
                counts[k] += 1
    out = [{"label": name, "tags": search._brief(c, ids), "hidden": not ids,
            "separate": ids == [T.own_id(name)], "books": counts[T.key(name)]} for name, ids in fx.items()]
    return sorted(out, key=lambda x: (-x["books"], T.key(x["label"])))
