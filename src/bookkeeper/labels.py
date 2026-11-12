"""Fixing site labels: say once what a label means, and every book with it follows.

A fix maps a label as the sites write it (any spelling: «Попаданиевдругоймир», «#попаданиевдругоймир») onto
shared tags, hides it ([]), or keeps it as a tag of its own (for a label Bookkeeper maps to the wrong tag).
Fixes live in my_tags.toml's [fixes] table and apply to the books you have and to every book that arrives later.
Books keep their labels as written (books.labels), so any fix can be undone."""
import json
import re

from . import db, library, search
from . import tags as T
from .db import jload, now

PAGE = 50
# Tags a label hardly ever means, even when its books all have them (every Author.Today book is a "Novel").
_NOT_MEANINGS = {"narration", "format", "origin"}


def _rows_by_id(c, ids, sql: str) -> list:
    out, ids = [], list(ids)
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        out += c.execute(sql.format(q=",".join("?" * len(chunk))), chunk).fetchall()
    return out


def _books_with(c, label: str, mapped_to: list[str] | None = None) -> set[int]:
    """Books whose site labels include this label, written any way. `mapped_to`: the tags the label meant until
    now, when the tag list has already changed (default: what it means now)."""
    k = T.key(label)
    tag_ids = set(T.canonical(label) if mapped_to is None else mapped_to)
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


def _by_company(c, tag_id: str, ctx: dict, min_share: float = 0.5, min_lift: float = 3) -> list[tuple[str, float]]:
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
        if share >= min_share and share / (base / ctx["total"]) >= min_lift:
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
    items = _groups(c, site, q)
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


def _groups(c, site: str | None = None, q: str = "") -> list[dict]:
    """Unrecognized labels grouped by spelling, most books first, without the ones you fixed or left as they are."""
    if site:
        rows = c.execute("SELECT t.id, t.label, COUNT(DISTINCT bt.book_id) AS books FROM tags t JOIN book_tags bt "
                         "ON bt.tag = t.id AND bt.source = 'site' JOIN books b ON b.id = bt.book_id "
                         "WHERE t.known = 0 AND t.category = 'other' AND b.site = ? GROUP BY t.id", (site,)).fetchall()
    else:
        rows = c.execute("SELECT id, label, books FROM tags WHERE known = 0 AND category = 'other' AND books > 0").fetchall()
    fixed = {T.key(name) for name in T.fixes()}
    groups: dict[str, dict] = {}
    for r in rows:
        k = T.key(r["id"])
        if not k:
            continue
        if k in fixed:
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
    return items


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


# ---------------------------------------------------------------- many fixes at once (AI chat imports)
def _unknown_index(c) -> dict[str, list[tuple[str, int]]]:
    """key -> [(tag id, books)] for every site label that isn't a shared tag."""
    out: dict[str, list[tuple[str, int]]] = {}
    for tid, books in c.execute("SELECT id, books FROM tags WHERE known = 0"):
        k = T.key(tid)
        if k:
            out.setdefault(k, []).append((tid, books or 0))
    return out


def _books_with_many(c, names) -> set[int]:
    """Books whose site labels include any of these labels (written any way), in one pass."""
    keys = {T.key(n) for n in names if T.key(n)}
    if not keys:
        return set()
    index = _unknown_index(c)
    tag_ids, scan = set(), False
    for n in names:
        ids = set(T.canonical(n)) | {tid for tid, _ in index.get(T.key(n), [])}
        if ids:
            tag_ids |= ids
        else:
            scan = True  # a hidden label has no tag to start from
    if scan:
        rows = c.execute("SELECT id, labels FROM books WHERE labels IS NOT NULL AND labels != '[]'").fetchall()
    else:
        books = {r[0] for r in _rows_by_id(c, tag_ids, "SELECT DISTINCT book_id FROM book_tags "
                                                      "WHERE source = 'site' AND tag IN ({q})")}
        rows = _rows_by_id(c, books, "SELECT id, labels FROM books WHERE id IN ({q})")
    return {r[0] for r in rows if any(T.key(x) in keys for x in jload(r[1], []) or [])}


def _link_is(kind: str, a: str, b: str) -> bool:
    if kind == "child":
        kind, a, b = "parent", b, a
    return b in T.parents(a) if kind == "parent" else b in T.anti(a)


def apply_many(entries, new_tags=(), links=()) -> dict:
    """Many label fixes in one go: entries [(label, ids)], where ids None undoes a fix, [] hides the label and
    [its own id] leaves it as it is; new_tags are made first; links [(kind, tag, other, on)] add or remove parent,
    child and anti-tag links (see tagedit.set_link). One write to my_tags.toml, one re-tagging pass.
    Returns how many labels and books changed, what each label meant before, and the links that changed (for undo)."""
    from . import tagedit  # local import: tagedit uses this module
    c = db.conn()
    entries = [(label.strip(), ids) for label, ids in entries if T.key(label)]
    # a new tag's names mean it from now on, even where they were another tag's alias
    new_names = [t[k] for t in new_tags for k in ("label", "label_ru", "label_uk") if t.get(k)]
    affected = _books_with_many(c, [label for label, _ in entries] + new_names)
    previous: dict[str, list[str] | None] = {}
    links = [list(x) for x in links if _link_is(*x[:3]) != bool(x[3])]  # only the ones that change something
    with T._FILE_LOCK:
        fixes = T.fixes()
        by_key = {T.key(name): name for name in fixes}
        for label, ids in entries:
            old = by_key.pop(T.key(label), None)
            previous.setdefault(label, fixes.get(old) if old else None)
            if old:
                fixes.pop(old)
            if ids is not None:
                fixes[label] = list(dict.fromkeys(ids))
                by_key[T.key(label)] = label
        changes = {("tags", t["id"]): {k: v for k, v in t.items() if k != "id" and v} for t in new_tags}
        if entries:
            changes[("fixes",)] = dict(sorted(fixes.items(), key=lambda kv: T.key(kv[0])))
        if links:
            tabs = tagedit.link_tables()
            for kind, a, b, on in links:
                tagedit.set_link(tabs, kind, a, b, on)
            changes.update(tagedit.link_changes(tabs))
        T.write_tables(changes)
    T.reload()
    if new_tags:
        library.sync_tag_rows([t["id"] for t in new_tags])
    if affected:
        library.retag_books(affected)
    touched = {a if kind == "parent" else b for kind, a, b, _ in links if kind in ("parent", "child")}
    if touched:
        library.refresh_rules_for(touched)
    return {"labels": len(entries), "books": len(affected), "previous": previous, "links": links}


AI_PROMPT = """\
I keep a personal catalog of web novels collected from book sites (Wattpad, Author.Today, Ficbook, Litnet,
RanobeLib and others). Every site tags books its own way, and my app maps those tags onto one list of shared
tags. Below are SITE LABELS the app couldn't map (most common first) and the list of SHARED TAGS.
Decide what each site label means.

For every site label, answer with one JSON object on its own line:
{"label": "<the label exactly as given>", "tags": ["<shared tag id>", ...]}
    the label means these shared tags
{"label": "<the label>", "hide": true}
    junk that says nothing about the book itself: site or app names, years, contests, "recommend",
    "my first story", emoji, author notes, random words
{"label": "<the label>", "keep": true}
    a real label that no shared tag covers, or you aren't sure

You may also propose a new shared tag when several labels share a useful meaning that no shared tag covers.
Write it once, on its own line before the labels that use it, then use its id in "tags":
{"new_tag": {"id": "complicated-relationships", "en": "Complicated relationships", "ru": "Сложные отношения", "uk": "Складні стосунки", "category": "relationship", "description": "The main characters' relationship is complicated.", "parents": ["romance"]}}
Categories: genre, theme, protagonist, setting, orientation, relationship, content, format, demographic, fandom.
Tags form a family tree. "parents" are broader shared tags that EVERY book with the new tag also has: books get
them automatically, so a new tag that is a narrower kind of a shared tag should name it as a parent.
"anti" (optional) lists shared tags that contradict the new tag (can't both be true of one book).

Guidelines:
- Use only ids from SHARED TAGS, or the ids of new tags you proposed. Don't invent other ids.
- A label can mean several tags: "попаданцы в магический мир" -> ["isekai", "magic"].
- Character, place and pairing names mean their fandom: "саске" -> ["fandom-naruto"]. For a fandom that isn't
  in the list, write "fandom:<the fandom's usual name>", for example "fandom:Genshin Impact".
- "often_with" lists shared tags that most books with the label also have, and "examples" are titles of books
  with it. Use them as hints, but decide by what the label itself means.
- Prefer the most specific tag that fits. Don't add broader tags that follow anyway (litrpg already brings
  rpg-elements), and don't map a label to a tag just because its books often have it.
- When several labels name the same narrower kind of a shared tag ("гг монстр", "monster protagonist",
  "гг паук" are all kinds of "nonhuman-lead"), propose a new child tag with that shared tag in "parents" and
  map the labels to it, instead of mapping them all to the broad tag. Don't make a new tag for one rare label.
- Answer only with JSON lines, one for every site label, all in one code block. No explanations.
"""


def _shared_tag_lines(c) -> list[str]:
    """The shared tags for the prompt: id | English | Russian | category | meaning."""
    order = {cat: n for n, cat in enumerate(T.CATEGORY_ORDER)}
    lines = []
    for tid in sorted(T.all_ids(), key=lambda t: (order.get(T.info(t).get("category"), 99), t)):
        i = T.info(tid)
        desc = " ".join((T.describe(tid) or "").split())
        desc = desc if len(desc) <= 140 else desc[:139] + "…"
        lines.append(" | ".join([tid, i.get("label") or "", i.get("label_ru") or "", i.get("category") or "", desc]).rstrip(" |"))
    # fandoms from the sites (Ficbook) that aren't built in, the biggest ones
    for tid, label in c.execute("SELECT id, label FROM tags WHERE id LIKE 'fandom:%' AND books >= 2 "
                                "ORDER BY books DESC LIMIT 300"):
        lines.append(f"{tid} | {label} | | fandom")
    return lines


def export_for_ai(site: str | None = None, q: str = "", limit: int = 250) -> dict:
    """A prompt for an AI chat: the most common unrecognized labels (with hints) and the shared tags."""
    c = db.conn()
    groups = _groups(c, site, q)
    page = groups[:max(1, limit)]
    ctx = _context(c)
    lines = []
    for g in page:
        item = {"label": g["label"], "books": g["books"]}
        often = [t for t, _ in _by_company(c, g["id"], ctx, min_share=0.3, min_lift=1.5)[:4]]
        if often:
            item["often_with"] = often
        q_ = ",".join("?" * len(g["ids"]))
        titles = [r[0] for r in c.execute(
            f"SELECT DISTINCT b.title FROM book_tags bt JOIN books b ON b.id = bt.book_id WHERE bt.tag IN ({q_}) "
            f"AND bt.source = 'site' ORDER BY COALESCE(b.popularity, 0) DESC LIMIT 2", g["ids"])]
        if titles:
            item["examples"] = [t if len(t) <= 70 else t[:69] + "…" for t in titles]
        lines.append(json.dumps(item, ensure_ascii=False))
    text = (AI_PROMPT + "\nSHARED TAGS (id | English | Russian | category | meaning)\n" + "\n".join(_shared_tag_lines(c))
            + f"\n\nSITE LABELS ({len(page)}, one JSON object per line)\n" + "\n".join(lines) + "\n")
    return {"text": text, "count": len(page), "total": len(groups), "chars": len(text)}


def _objects(text: str) -> list[dict]:
    """Every JSON object in an AI's reply, wherever it is: in code blocks, a list, one per line, with words around."""
    out, depth, start, in_str, esc = [], 0, 0, False, False
    for i, ch in enumerate(text):
        if depth and in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif depth and ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(text[start:i + 1])
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    out.append(obj)
    return out


def _new_tag(spec: dict) -> dict:
    names = {"label": spec.get("en") or spec.get("label"), "label_ru": spec.get("ru") or spec.get("label_ru"),
             "label_uk": spec.get("uk") or spec.get("label_uk")}
    names = {k: str(v).strip() for k, v in names.items() if v and str(v).strip()}
    tid = str(spec.get("id") or "").strip().lower()
    tid = re.sub(r"[^a-z0-9а-яёіїєґ:-]+", "-", tid).strip("-") or re.sub(
        r"[^a-z0-9]+", "-", (names.get("label") or "").lower()).strip("-")
    category = str(spec.get("category") or "theme").strip().lower()
    out = {"id": tid, **names, "category": category if category in T.CATEGORY_ORDER else "theme",
           "description": str(spec.get("description") or "").strip(), "problem": None, "same_as": None,
           "raw_parents": _strs(spec.get("parents") or spec.get("parent")), "raw_anti": _strs(spec.get("anti")),
           "parents": [], "anti": [], "unknown": []}
    if not tid or not names:
        out["problem"] = "it has no id or name"
    elif T.is_known(tid):
        out["same_as"] = tid  # there's a shared tag with that id already: labels can just use it
    else:
        parents = {i for p in out["raw_parents"] for i in T.canonical(p) if T.is_known(i)}
        for name in names.values():
            others = [t for t in T.canonical(name) if T.is_known(t)]
            own = [t for t in others if T.key(name) in {T.key(n) for n in (t, *T.own_names(t))}]
            # an existing tag under another id, unless the name is just an alias of the new tag's parent
            # ("ГГ монстр" was an alias of Non-human lead, and becomes its own child tag)
            if own or (others and not set(others) <= parents):
                out["same_as"] = (own or others)[0]
                break
    return out


def _strs(value) -> list[str]:
    """An answer's list of tags (or one tag as a string), as clean strings."""
    value = [value] if isinstance(value, str) else value if isinstance(value, list) else []
    return [s for s in (str(x).strip() for x in value) if s]


def _one_tag(x: str, new: dict) -> str | None:
    """One shared tag (or a usable new one) for a parent or anti-tag in an answer, or None."""
    ids = _target(x, new)
    return ids[0] if ids and len(ids) == 1 and (T.is_known(ids[0]) or ids[0] in new) else None


def _broader(tag_id: str, new: dict) -> set[str]:
    """Every tag above this one, the new tags' parents included."""
    seen, todo = set(), [tag_id]
    while todo:
        t = todo.pop()
        for p in (new[t]["parents"] if t in new else T.parents(t)):
            if p not in seen:
                seen.add(p)
                todo.append(p)
    return seen


def _new_tag_links(new: dict) -> None:
    """Work out the parents and anti-tags of the new tags an answer proposed (only shared or new tags; no loops)."""
    for tid, t in new.items():
        if t["problem"] or t["same_as"]:
            continue
        for field, raw in (("parents", t["raw_parents"]), ("anti", t["raw_anti"])):
            for x in raw:
                found = _one_tag(x, new)
                if not found or found == tid:
                    t["unknown"].append(x)
                elif found not in t[field] and not (field == "parents" and tid in _broader(found, new)):
                    t[field].append(found)
    for tid, t in new.items():  # an anti-tag can't be in the same family
        family = _broader(tid, new)
        t["anti"] = [a for a in t["anti"] if a not in family and tid not in _broader(a, new)]


def _target(x: str, new: dict) -> list[str] | None:
    """Tag ids for one entry of an answer's "tags" (an id, a new tag's id, a fandom, or a tag's name)."""
    if x in new:
        return [new[x]["same_as"] or x] if not new[x]["problem"] else None
    if T.is_known(x):
        return [x]
    if x.lower().startswith(T.FANDOM_PREFIX):
        return T.canonical(x) or None
    ids = T.canonical(x)
    return ids if ids and all(T.is_known(i) for i in ids) else None


def _new_tag_out(t: dict, new: dict, **extra) -> dict:
    """A proposed new tag for the preview: its parents and anti-tags with their names."""
    def brief(i):
        return {"id": i, "label": (new[i].get("label") or new[i].get("label_ru")) if i in new else T.info(i)["label"]}
    out = {k: v for k, v in t.items() if not k.startswith("raw_")}
    return {**out, "parents": [brief(i) for i in t["parents"]], "anti": [brief(i) for i in t["anti"]], **extra}


def new_tag_entry(t: dict) -> dict:
    """What my_tags.toml keeps of a new tag."""
    return {k: t[k] for k in ("id", "label", "label_ru", "label_uk", "category", "description") if t.get(k)}


def new_tag_links(t: dict) -> list[tuple]:
    ids = lambda xs: [x["id"] if isinstance(x, dict) else x for x in xs]  # noqa: E731
    return [("parent", t["id"], p, True) for p in ids(t["parents"])] + [("anti", t["id"], a, True) for a in ids(t["anti"])]


def check_import(text: str) -> dict:
    """What an AI's reply would do, label by label, before anything changes."""
    c = db.conn()
    objs = _objects(text or "")
    if not any("label" in o or "new_tag" in o for o in objs):
        raise ValueError("No answers found. Paste the AI's whole reply: the lines that start with {\"label\".")
    new = {}
    for o in objs:
        if isinstance(o.get("new_tag"), dict):
            t = _new_tag(o["new_tag"])
            new[t["id"]] = t
    _new_tag_links(new)
    index = _unknown_index(c)
    fixed = {T.key(name) for name in T.fixes()}
    new_names = {t["id"]: t.get("label") or t.get("label_ru") for t in new.values()}
    items, seen = [], set()
    for o in objs:
        if "label" not in o:
            continue
        label = str(o["label"]).strip()
        k = T.key(label)
        if not k or k in seen:
            continue
        seen.add(k)
        it = {"label": label, "key": k, "books": sum(b for _, b in index.get(k, [])), "problem": None,
              "action": "tags", "ids": [], "tags": []}
        items.append(it)
        # Only labels that are still unrecognized: an answer can't touch a shared tag's own names ("hide Фэнтези").
        if k in fixed:
            it["problem"] = "already fixed"
            continue
        if k not in index or (T.canonical(label) and all(T.is_known(i) for i in T.canonical(label))):
            it["problem"] = "not an unrecognized label in your library"
            continue
        if o.get("hide") is True:
            it.update(action="hide", ids=[])
        elif o.get("keep") is True:
            it.update(action="keep", ids=[T.own_id(label)])
        else:
            raw = o.get("tags") if o.get("tags") is not None else o.get("tag")
            raw = [raw] if isinstance(raw, str) else [str(x) for x in raw or []]
            ids, bad = [], []
            for x in (x.strip() for x in raw):
                found = _target(x, new) if x else None
                if found:
                    ids += found
                elif x:
                    bad.append(x)
            it.update(action="tags", ids=list(dict.fromkeys(ids)))
            if bad:
                it["problem"] = "no tag " + ", ".join(f"“{b}”" for b in bad)
            elif not ids:
                it["problem"] = "no tags, hide or keep"
        if it["action"] == "tags":
            it["tags"] = [{"id": i, "label": new_names.get(i) or T.info(i)["label"]} for i in it["ids"]]
    used = {i for it in items for i in it["ids"]}
    new_tags = [_new_tag_out(t, new, used_by=sum(1 for it in items if t["id"] in it["ids"])) for t in new.values()
                if not t["same_as"]]
    counts = {a: sum(1 for it in items if it["action"] == a and not it["problem"]) for a in ("tags", "hide", "keep")}
    counts["problems"] = sum(1 for it in items if it["problem"])
    counts["new_tags"] = sum(1 for t in new_tags if not t["problem"] and t["id"] in used)
    return {"items": items, "new_tags": new_tags, "counts": counts}


def apply_import(text: str, keys=None, new_ids=None) -> dict:
    """Apply an AI's reply: the answers whose keys you kept ticked (all when None), with the new tags you kept."""
    preview = check_import(text)
    proposed = {t["id"] for t in preview["new_tags"]}
    make = [t for t in preview["new_tags"] if not t["problem"] and (new_ids is None or t["id"] in new_ids)]
    dropped = proposed - {t["id"] for t in make}
    entries = []
    for it in preview["items"]:
        if it["problem"] or (keys is not None and it["key"] not in keys):
            continue
        ids = [i for i in it["ids"] if i not in dropped] if it["action"] == "tags" else it["ids"]
        if it["action"] == "tags" and not ids:
            continue
        entries.append((it["label"], ids))
    used = {i for _, ids in entries for i in ids}
    make = [t for t in make if t["id"] in used]
    made = {t["id"] for t in make}
    links = [x for t in make for x in new_tag_links(t) if T.is_known(x[2]) or x[2] in made]
    if not entries:
        raise ValueError("Nothing to apply: tick at least one answer.")
    result = apply_many(entries, [new_tag_entry(t) for t in make], links)
    record = {"id": now().replace(":", "").replace("-", ""), "at": now(), "labels": result["previous"],
              "links": result["links"], "new_tags": sorted(made), "count": result["labels"], "books": result["books"]}
    db.set_setting("label_imports", [record, *db.get_setting("label_imports", [])][:30])
    return {**result, "import": record["id"], "new_tags": len(make)}


def imports() -> list[dict]:
    """Your imports of AI answers, newest first."""
    return [{k: r.get(k) for k in ("id", "at", "count", "books", "new_tags", "undone")}
            for r in db.get_setting("label_imports", [])]


def undo_import(import_id: str) -> dict:
    """Put back every label an import changed, and delete the tags it made (unless something else uses them)."""
    from . import tagedit  # local import: tagedit uses this module
    records = db.get_setting("label_imports", [])
    rec = next((r for r in records if r.get("id") == import_id), None)
    if not rec or rec.get("undone"):
        raise ValueError("That import is already undone.")
    result = apply_many(list(rec["labels"].items()),
                        links=[(k, a, b, not on) for k, a, b, on in reversed(rec.get("links") or [])])
    still_used = {i for ids in T.fixes().values() for i in ids}
    for tid in rec.get("new_tags", []):
        if tid not in still_used and tid in (T.user_config().get("tags") or {}):
            tagedit.delete(tid)
    rec["undone"] = True
    db.set_setting("label_imports", records)
    return result
