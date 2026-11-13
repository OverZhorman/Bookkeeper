"""Improving shared tags with an AI chat, many at a time: copy a request with tags and their aliases, paste the
chat's reply back. The chat can move aliases to new child tags ("monster protagonist" from Non-human lead to a new
Monster protagonist, child of Non-human lead), move wrong aliases to the right tags, keep them apart or hide them,
add new aliases and combined labels, rename tags and fix their categories and descriptions, and add or remove
parent, child, anti-tag and related ("see also") links. Everything is saved in my_tags.toml like the changes made
by hand, and a whole import can be undone."""
import json

from . import db, labels
from . import tags as T
from .db import jload, now

MAX_ALIASES_PER_TAG = 300
TAG_WEIGHT = 5  # what one tag's names, description and links count for in a request, besides its aliases

PROMPT = """\
I keep a personal catalog of web novels collected from book sites (Wattpad, Author.Today, Ficbook, Litnet,
RanobeLib and others). My app maps the sites' labels onto one list of SHARED TAGS. Tags form a family tree:
a book with a tag automatically gets the tag's parents too (every LitRPG book is also "RPG elements"), and
anti-tags are tags that contradict each other. "Related" tags are a "see also" list on a tag's page: they
don't change any book's tags.

Over time many site labels became ALIASES of a broad tag, though plenty of them name something narrower or
something else. Below are TAGS TO IMPROVE, each with its names, description, links and aliases (with how many
of my books have each alias). Improve them:

1. Child tags. When several aliases of a tag (or one alias used by many books) name a narrower kind of it that
   a reader would want to search for, propose a new tag with that tag as its parent, and move those aliases to
   it. Books keep the broad tag through the parent link. Example: Non-human lead has the aliases
   "monster protagonist", "гг монстр", "гг паук", "Humanoid Protagonist", "animalcharacter", "герой животное",
   "Genderless Protagonist", "безполый" -> new tags Monster protagonist, Humanoid protagonist, Animal
   protagonist and Genderless protagonist, each with parents ["nonhuman-lead"], and those aliases move to them.
   If a shared tag already fits, use it instead of a new one.
2. Wrong aliases. An alias that means something else moves to the right tags. A real label that no shared tag
   covers is kept apart, as a label of its own. Junk (site names, years, random words) is hidden.
3. Links. Add missing parent links (the tag's every book must also have the other tag), remove wrong ones,
   and add anti-tags for tags that can't both be true of one book. Be conservative.
4. Names and descriptions. Fix a name that is wrong, unclear or missing (English, Russian, Ukrainian), a wrong
   category, and a description that is missing or unclear: one or two plain sentences on what books with the
   tag have.
5. New aliases. Common ways readers and sites write the tag that aren't among its aliases yet: translations,
   spellings, short forms, hashtags. Only real ones. A label meaning two tags at once is a combined label:
   {"alias": "магический детектив", "tags": ["magic", "mystery"]}.
6. Related tags. A few tags a reader of this tag would want to look at too, that aren't its parents, children
   or anti-tags. Be conservative.

Aliases that are just another way of writing the same tag (translations, spellings, short forms) stay as they
are: don't mention them.

Answer with JSON objects, one per line:
{"tag": "<id>"}
    write this for EVERY tag in TAGS TO IMPROVE, even when nothing changes, before any line about its aliases
{"tag": "<id>", "en": "...", "ru": "...", "uk": "...", "category": "...", "description": "..."}
    new names, category or description (only the fields that change)
{"tag": "<id>", "add_aliases": ["..."], "add_parents": ["<id>"], "remove_parents": [], "add_children": [], "remove_children": [], "add_anti": [], "remove_anti": [], "add_related": [], "remove_related": []}
    new aliases and changes to the tag's links (only the fields you need; names and links can share one line)
{"new_tag": {"id": "monster-protagonist", "en": "Monster protagonist", "ru": "ГГ монстр", "uk": "ГГ монстр", "category": "protagonist", "description": "The protagonist is a monster: a slime, a spider, a goblin...", "parents": ["nonhuman-lead"], "anti": []}}
    a new tag; write it before the aliases that move to it
{"alias": "<the alias exactly as given>", "tags": ["<id>", ...]}
    the alias now means these tags instead ("гг вампир" -> ["monster-protagonist", "vampires"])
{"alias": "<the alias>", "keep": true}
    a real label that no shared tag covers: it stops meaning the tag and stays a label of its own
{"alias": "<the alias>", "hide": true}
    junk: remove it from every book

Guidelines:
- Use ids from SHARED TAGS or new tags you proposed. Don't invent other ids. For a fandom that isn't in the
  list, write "fandom:<the fandom's usual name>".
- A child must always imply its parent: every book with "Monster protagonist" has a non-human lead. If that
  isn't always true, don't make it a child.
- Don't make a new tag for a single rare alias. A new tag is worth it when it gathers several aliases or a fair
  number of books.
- When an alias moves, list every tag it should mean. Its old tag doesn't need repeating if it's a parent of
  the new one.
- "combined" lists labels that mean the tag together with other tags. They can move too.
- A new name can't be another tag's name or alias. The old name stays as an alias.
- Categories: genre, theme, protagonist, setting, orientation, relationship, content, format, demographic,
  fandom.
- Answer only with JSON lines, all in one code block. No explanations.
"""

# What an answer may change about a tag: the answer's field -> the tag's field.
EDIT_FIELDS = (("en", "label"), ("label", "label"), ("ru", "label_ru"), ("label_ru", "label_ru"),
               ("uk", "label_uk"), ("label_uk", "label_uk"), ("category", "category"),
               ("description", "description"))
NAME_FIELDS = ("label", "label_ru", "label_uk")
LINK_FIELDS = (("add_parents", "parent", True), ("remove_parents", "parent", False),
               ("add_children", "child", True), ("remove_children", "child", False),
               ("add_anti", "anti", True), ("remove_anti", "anti", False),
               ("add_related", "related", True), ("remove_related", "related", False))


def _alias_books(c, tag_ids) -> dict[str, int]:
    """alias key -> books: how many books with these tags have each label, as the sites wrote it."""
    books = {r[0] for r in labels._rows_by_id(c, tag_ids, "SELECT DISTINCT book_id FROM book_tags "
                                                          "WHERE source = 'site' AND tag IN ({q})")}
    out: dict[str, int] = {}
    for r in labels._rows_by_id(c, books, "SELECT labels FROM books WHERE id IN ({q})"):
        for k in {T.key(x) for x in jload(r[0], []) or []}:
            out[k] = out.get(k, 0) + 1
    return out


def _size(tid: str) -> int:
    return len(T.aliases(tid)) + len(T.combined(tid))


def _reviewed() -> set[str]:
    return set(db.get_setting("tags_reviewed", []))


def candidates(q: str = "", category: str = "", reviewed: bool = False) -> list[str]:
    """Shared tags to improve, most aliases first: the ones matching q (a name or id; several separated by commas),
    of one category, and (unless reviewed) not reviewed yet. Fandoms only when asked for."""
    wanted = [s.strip() for s in q.split(",") if s.strip()]
    keys = [T.key(s) for s in wanted if T.key(s)]
    done = set() if reviewed or wanted else _reviewed()
    out = []
    for tid in T.all_ids():
        i = T.info(tid)
        if category and i.get("category") != category:
            continue
        if keys:
            names = [T.key(n) for n in (tid, *T.own_names(tid))]
            if not any(k == n or (len(k) >= 3 and k in n) for k in keys for n in names):
                continue
        elif not category and i.get("category") == "fandom":
            continue
        if tid in done:
            continue
        out.append(tid)
    exact = {t for t in out for k in keys if k in {T.key(n) for n in (t, *T.own_names(t))}}
    return sorted(out, key=lambda t: (t not in exact, -_size(t), t))


def export(q: str = "", category: str = "", reviewed: bool = False, limit: int = 600) -> dict:
    """A request for an AI chat: tags with their aliases, about `limit` aliases in all, and the shared tags."""
    c = db.conn()
    pool = candidates(q, category, reviewed)
    batch, n, aliases_n = [], 0, 0
    for tid in pool:
        size = min(_size(tid), MAX_ALIASES_PER_TAG)
        if batch and n + size + TAG_WEIGHT > limit:
            break
        batch.append(tid)
        n += size + TAG_WEIGHT
        aliases_n += size
    counts = _alias_books(c, batch)
    books = {r[0]: r[1] for r in labels._rows_by_id(c, batch, "SELECT id, books FROM tags WHERE id IN ({q})")}
    lines = []
    for tid in batch:
        i, have = T.info(tid), counts
        item = {"tag": tid, "en": i.get("label"), "ru": i.get("label_ru"), "uk": i.get("label_uk"),
                "category": i.get("category"), "books": books.get(tid) or 0}
        desc = " ".join((T.describe(tid) or "").split())
        if desc:
            item["description"] = desc
        for field, ids in (("parents", T.direct_parents(tid)), ("children", T.children(tid)), ("anti", T.anti(tid)),
                           ("related", T.related(tid))):
            if ids:
                item[field] = sorted(ids)
        aliases = sorted(T.aliases(tid), key=lambda a: (-have.get(T.key(a), 0), T.key(a)))
        item["aliases"] = {a: have.get(T.key(a), 0) for a in aliases[:MAX_ALIASES_PER_TAG]}
        if len(aliases) > MAX_ALIASES_PER_TAG:
            item["aliases_not_shown"] = len(aliases) - MAX_ALIASES_PER_TAG
        combined = T.combined(tid)[:max(0, MAX_ALIASES_PER_TAG - len(aliases))]
        if combined:
            item["combined"] = {label: others for label, others in combined}
        lines.append(json.dumps({k: v for k, v in item.items() if v not in (None, "")}, ensure_ascii=False))
    text = (PROMPT + "\nSHARED TAGS (id | English | Russian | category | meaning)\n"
            + "\n".join(labels._shared_tag_lines(c))
            + f"\n\nTAGS TO IMPROVE ({len(batch)}, one JSON object per line)\n" + "\n".join(lines) + "\n")
    return {"text": text, "tags": len(batch), "aliases": aliases_n, "total": len(pool), "chars": len(text),
            "reviewed": len(_reviewed())}


# ---------------------------------------------------------------- reading the reply
def _own_name_index() -> dict[str, str]:
    """key -> the tag it's the own name (or id) of."""
    out: dict[str, str] = {}
    for t in T.all_ids():
        for n in (t, *T.own_names(t)):
            out.setdefault(T.key(n), t)
    return out


class _Family:
    """The family tree as it would be after the answers so far, to catch loops and contradictions."""

    def __init__(self, new: dict):
        self.new = new
        self.added: dict[str, set[str]] = {}
        self.removed: dict[str, set[str]] = {}

    def parents(self, t: str) -> set[str]:
        base = set(self.new[t]["parents"]) if t in self.new else set(T.parents(t))
        return (base | self.added.get(t, set())) - self.removed.get(t, set())

    def above(self, t: str) -> set[str]:
        seen, todo = set(), [t]
        while todo:
            for p in self.parents(todo.pop()):
                if p not in seen:
                    seen.add(p)
                    todo.append(p)
        return seen

    def kin(self, a: str, b: str) -> bool:
        return a in self.above(b) or b in self.above(a)


def _label(i: str, new: dict) -> str:
    return (new[i].get("label") or new[i].get("label_ru") or i) if i in new else T.info(i)["label"]


def _edits_of(o: dict) -> dict[str, str]:
    """The new names, category and description on a {"tag": ...} answer."""
    out: dict[str, str] = {}
    for k, field in EDIT_FIELDS:
        v = o.get(k)
        if isinstance(v, str) and v.strip() and field not in out:
            out[field] = v.strip() if field == "description" else " ".join(v.split())
    if "category" in out:
        out["category"] = out["category"].lower()
    return out


def _current(tid: str, field: str) -> str:
    return (T.describe(tid) if field == "description" else T.info(tid).get(field)) or ""


def _still_means(tid: str, name: str) -> bool:
    """Whether a name means the tag even when it isn't one of the tag's own names: Bookkeeper's own names and
    synonyms for it, and your fixes and synonyms that mean just this tag."""
    k = T.key(name)
    if k in labels._builtin_names(tid):
        return True
    user = T.user_config()
    return any(T.key(label) == k and T._as_list(ids) == [tid]
               for table in ("fixes", "synonyms") for label, ids in (user.get(table) or {}).items())


def _already(kind: str, tid: str, other: str, fam: _Family) -> bool:
    """Whether a link an answer adds is there already (often: a new tag's own parent, said twice)."""
    if kind == "anti":
        return other in T.anti(tid)
    if kind == "related":
        return other in T.related(tid)
    child, parent = (tid, other) if kind == "parent" else (other, tid)
    return parent in fam.parents(child)


def check(text: str) -> dict:
    """What an AI's reply would do, change by change, before anything changes."""
    objs = labels._objects(text or "")
    if not any(k in o for o in objs for k in ("tag", "alias", "new_tag")):
        raise ValueError("No answers found. Paste the AI's whole reply: the lines that start with {\"tag\" or {\"alias\".")
    new = {}
    for o in objs:
        if isinstance(o.get("new_tag"), dict):
            t = labels._new_tag(o["new_tag"])
            new[t["id"]] = t
    labels._new_tag_links(new)
    fam = _Family(new)
    own = _own_name_index()
    unknown = labels._unknown_index(db.conn())
    reviewed, links, aliases, edits, seen = [], [], [], [], set()

    def alias_item(label: str, raw_tags, hide: bool = False, keep: bool = False, of: str | None = None) -> None:
        """One alias answer: the alias moves to these tags (a new spelling becomes a new alias), or it's kept
        apart, or hidden. `of`: the tag an "add_aliases" list belongs to."""
        label = str(label).strip()
        k = T.key(label)
        if not k or f"alias:{k}" in seen:
            return
        if of and (own.get(k) == of or (of in new and k in {T.key(new[of].get(f) or "") for f in NAME_FIELDS})):
            return  # the tag's own name: it means the tag already
        seen.add(f"alias:{k}")
        before = T.canonical(label)
        it = {"key": f"alias:{k}", "label": label, "problem": None, "action": "tags", "ids": [], "tags": [],
              "new": False, "before": [{"id": i, "label": T.info(i)["label"]} for i in before if T.is_known(i)]}
        aliases.append(it)
        if k in own:
            it["problem"] = "it's a tag's own name: rename the tag instead"
            return
        known = bool(before) and all(T.is_known(i) for i in before)
        if not known and k not in unknown:
            if hide or keep:
                it["problem"] = "not a label in your library"
                return
            it["new"] = True  # a spelling no book has yet: a new alias
        if hide:
            it.update(action="hide")
            return
        if keep:
            if not known:
                aliases.pop()  # a label of its own already
                return
            it.update(action="keep", ids=[T.own_id(label)])
            return
        ids, bad = [], []
        for x in labels._strs(raw_tags):
            found = labels._target(x, new)
            if found:
                ids += found
            else:
                bad.append(x)
        ids = list(dict.fromkeys(ids))
        it.update(ids=ids, tags=[{"id": i, "label": _label(i, new)} for i in ids])
        if bad:
            it["problem"] = "no tag " + ", ".join(f"“{b}”" for b in bad)
        elif not ids:
            it["problem"] = "no tags, keep or hide"
        elif set(ids) == set(before):
            aliases.pop()  # it means that already

    for o in objs:
        if "tag" in o and "alias" not in o and isinstance(o["tag"], str):
            tid = labels._one_tag(o["tag"].strip(), new) or o["tag"].strip()
            if tid in new and new[tid]["same_as"]:
                tid = new[tid]["same_as"]
            if not (T.is_known(tid) or (tid in new and not new[tid]["problem"])):
                if f"tag:{tid}" not in seen:
                    seen.add(f"tag:{tid}")
                    links.append({"key": f"tag:{tid}", "tag": tid, "label": tid, "kind": "tag", "on": True,
                                  "other": "", "other_label": "", "problem": "not a shared tag"})
                continue
            if T.is_known(tid) and tid not in reviewed:
                reviewed.append(tid)
            if T.is_known(tid):  # a new tag's names come with it
                for field, value in _edits_of(o).items():
                    ekey = f"edit:{tid}:{field}"
                    old = _current(tid, field)
                    if ekey in seen or value == old:
                        continue
                    seen.add(ekey)
                    edits.append({"key": ekey, "tag": tid, "label": T.info(tid)["label"], "field": field,
                                  "old": old, "new": value, "keep": None,
                                  "problem": None if field != "category" or value in T.CATEGORY_ORDER
                                  else f"there's no category “{value}”"})
            for x in labels._strs(o.get("add_aliases")):
                alias_item(x, [tid], of=tid)
            for field, kind, on in LINK_FIELDS:
                for x in labels._strs(o.get(field)):
                    other = labels._one_tag(x, new)
                    link = {"tag": tid, "label": _label(tid, new), "kind": kind, "on": on, "problem": None,
                            "other": other or x, "other_label": _label(other, new) if other else x}
                    link["key"] = f"{kind}:{tid}:{link['other']}:{int(on)}"
                    if link["key"] in seen:
                        continue
                    seen.add(link["key"])
                    if other and other != tid and on and _already(kind, tid, other, fam):
                        continue
                    links.append(link)
                    child, parent = (tid, other) if kind == "parent" else (other, tid)
                    if not other:
                        link["problem"] = f"no tag “{x}”"
                    elif other == tid:
                        link["problem"] = "the same tag"
                    elif kind == "anti":
                        if on and fam.kin(tid, other):
                            link["problem"] = "they're in the same family"
                        elif not on and other not in T.anti(tid):
                            link["problem"] = "not an anti-tag now"
                    elif kind == "related":
                        if on and fam.kin(tid, other):
                            link["problem"] = "they're in the same family already"
                        elif not on and other not in T.related(tid):
                            link["problem"] = "not related now"
                    elif on:
                        if child in fam.above(parent):
                            link["problem"] = f"{_label(parent, new)} is narrower than {_label(child, new)}"
                        else:
                            fam.added.setdefault(child, set()).add(parent)
                    elif parent not in fam.parents(child):
                        link["problem"] = "not linked now"
                    else:
                        fam.removed.setdefault(child, set()).add(parent)
        elif "alias" in o:
            alias_item(o["alias"], o.get("tags") if o.get("tags") is not None else o.get("tag"),
                       hide=o.get("hide") is True, keep=o.get("keep") is True)
    _check_names(edits, aliases, new, own)
    used = {i for it in aliases if not it["problem"] for i in it["ids"]}
    used |= {x["other"] for x in links if not x["problem"]}
    new_tags = [labels._new_tag_out(t, new, used_by=sum(1 for it in aliases if t["id"] in it["ids"]))
                for t in new.values() if not t["same_as"]]
    fine = [it for it in aliases if not it["problem"]]
    counts = {"aliases": sum(1 for it in fine if it["action"] == "tags" and not it["new"]),
              "new_aliases": sum(1 for it in fine if it["new"]),
              "keep": sum(1 for it in fine if it["action"] == "keep"),
              "hide": sum(1 for it in fine if it["action"] == "hide"),
              "links": sum(1 for x in links if not x["problem"]),
              "edits": sum(1 for x in edits if not x["problem"]),
              "new_tags": sum(1 for t in new_tags if not t["problem"] and t["id"] in used),
              "problems": sum(1 for x in [*aliases, *links, *edits] if x["problem"])}
    return {"reviewed": [{"id": t, "label": T.info(t)["label"]} for t in reviewed], "new_tags": new_tags,
            "aliases": aliases, "links": links, "edits": edits, "counts": counts}


def _check_names(edits: list, aliases: list, new: dict, own: dict) -> None:
    """New names can't be another tag's name or alias (unless the same answer moves that alias to this tag), and
    a name a tag loses stays its alias."""
    moved = {it["key"][len("alias:"):]: it for it in aliases if not it["problem"]}
    new_names = {T.key(t.get(f) or ""): t["id"] for t in new.values() if not t["same_as"] for f in NAME_FIELDS}
    taken: dict[str, str] = {}
    for it in edits:
        if it["field"] not in NAME_FIELDS or it["problem"]:
            continue
        tid, k = it["tag"], T.key(it["new"])
        others = [t for t in T.canonical(it["new"]) if t != tid and T.is_known(t)]
        m = moved.get(k)
        if not k:
            it["problem"] = "an empty name"
        elif taken.get(k, tid) != tid:
            it["problem"] = f"the answer gives {T.info(taken[k])['label']} this name too"
        elif new_names.get(k, tid) != tid:
            it["problem"] = "a new tag in the answer has this name"
        elif own.get(k, tid) != tid:
            it["problem"] = f"it's the name of {T.info(own[k])['label']}"
        elif others and not (m and m["action"] == "tags" and m["ids"] == [tid]):
            it["problem"] = f"“{it['new']}” already means {T.info(others[0])['label']}: move that alias first"
        else:
            taken[k] = tid
    for it in edits:  # the old name stays an alias, unless it still means the tag anyway
        if it["field"] not in NAME_FIELDS or it["problem"] or not it["old"]:
            continue
        tid, names_after = it["tag"], set()
        for f in NAME_FIELDS:
            e = next((e for e in edits if e["tag"] == tid and e["field"] == f and not e["problem"]), None)
            names_after.add(T.key(e["new"] if e else _current(tid, f)))
        if T.key(it["old"]) not in names_after and not _still_means(tid, it["old"]):
            it["keep"] = it["old"]


def apply(text: str, keys=None, new_ids=None) -> dict:
    """Apply an AI's reply: the changes whose keys you kept ticked (all when None), with the new tags you kept."""
    from . import tagedit  # local import: tagedit uses labels
    preview = check(text)
    make = [t for t in preview["new_tags"] if not t["problem"] and (new_ids is None or t["id"] in new_ids)]
    dropped = {t["id"] for t in preview["new_tags"]} - {t["id"] for t in make}
    ok = lambda x: not x["problem"] and (keys is None or x["key"] in keys)  # noqa: E731
    entries = []
    for it in filter(ok, preview["aliases"]):
        ids = [i for i in it["ids"] if i not in dropped]
        if it["action"] == "tags" and not ids:
            continue
        entries.append((it["label"], ids))
    # the tags' new names, category and description; the names they lose stay their aliases
    edits = list(filter(ok, preview["edits"]))
    mine = T.user_config().get("tags") or {}
    tag_entries: dict[str, dict] = {}
    for x in edits:
        tid = x["tag"]
        e = tag_entries.setdefault(tid, dict(mine[tid]) if isinstance(mine.get(tid), dict) else {})
        base = tagedit.builtin(tid)
        if base and x["new"] == (base.get(x["field"]) or ""):
            e.pop(x["field"], None)  # back to Bookkeeper's own
        else:
            e[x["field"]] = x["new"]
    moving = {T.key(label) for label, _ in entries}
    entries = [(x["keep"], [x["tag"]]) for x in edits if x["keep"] and T.key(x["keep"]) not in moving] + entries
    links = [(x["kind"], x["tag"], x["other"], x["on"]) for x in filter(ok, preview["links"]) if x["other"] not in dropped]
    used = {i for _, ids in entries for i in ids} | {x[2] for x in links}
    make = [t for t in make if t["id"] in used]
    made = {t["id"] for t in make}
    # a new tag's own links first, so the answers' links can build on them
    links = [x for t in make for x in labels.new_tag_links(t) if T.is_known(x[2]) or x[2] in made] + links
    reviewed = [t["id"] for t in preview["reviewed"]]
    if not entries and not links and not made and not tag_entries:
        if reviewed:
            _mark_reviewed(reviewed)
            return {"labels": 0, "books": 0, "links": 0, "new_tags": 0, "edits": 0, "reviewed": len(reviewed),
                    "import": None}
        raise ValueError("Nothing to apply: tick at least one change.")
    result = labels.apply_many(entries, [labels.new_tag_entry(t) for t in make], links, tag_entries)
    _mark_reviewed(reviewed)
    record = {"id": now().replace(":", "").replace("-", ""), "at": now(), "labels": result["previous"],
              "links": result["links"], "new_tags": sorted(made), "reviewed": reviewed,
              "tag_entries": result["previous_entries"], "count": result["labels"],
              "link_count": len(result["links"]), "edit_count": len(edits), "books": result["books"]}
    db.set_setting("tag_imports", [record, *db.get_setting("tag_imports", [])][:30])
    return {"labels": result["labels"], "books": result["books"], "links": len(result["links"]),
            "new_tags": len(made), "edits": len(edits), "reviewed": len(reviewed), "import": record["id"]}


def _mark_reviewed(ids) -> None:
    db.set_setting("tags_reviewed", sorted(_reviewed() | set(ids)))


def forget_reviewed() -> None:
    db.set_setting("tags_reviewed", [])


def imports() -> list[dict]:
    """Your imports of AI answers about tags, newest first."""
    return [{k: r.get(k) for k in ("id", "at", "count", "link_count", "edit_count", "books", "new_tags", "undone")}
            for r in db.get_setting("tag_imports", [])]


def undo(import_id: str) -> dict:
    """Put back every alias, link, name and description an import changed, and delete the tags it made (unless
    something else uses them). The tags it reviewed count as not reviewed again."""
    from . import tagedit  # local import: tagedit uses labels
    records = db.get_setting("tag_imports", [])
    rec = next((r for r in records if r.get("id") == import_id), None)
    if not rec or rec.get("undone"):
        raise ValueError("That import is already undone.")
    result = labels.apply_many(list(rec["labels"].items()),
                               links=[(k, a, b, not on) for k, a, b, on in reversed(rec.get("links") or [])],
                               tag_entries=rec.get("tag_entries") or {})
    still_used = {i for ids in T.fixes().values() for i in ids}
    for tid in rec.get("new_tags", []):
        if tid not in still_used and tid in (T.user_config().get("tags") or {}):
            tagedit.delete(tid)
    db.set_setting("tags_reviewed", sorted(_reviewed() - set(rec.get("reviewed") or [])))
    rec["undone"] = True
    db.set_setting("tag_imports", records)
    return result
