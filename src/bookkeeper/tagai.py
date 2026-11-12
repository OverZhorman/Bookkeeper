"""Improving shared tags with an AI chat, many at a time: copy a request with tags and their aliases, paste the
chat's reply back. The chat can move aliases to new child tags ("monster protagonist" from Non-human lead to a new
Monster protagonist, child of Non-human lead), move wrong aliases to the right tags or hide them, and add or remove
parent, child and anti-tag links. Everything is saved in my_tags.toml like the changes made by hand, and a whole
import can be undone."""
import json

from . import db, labels
from . import tags as T
from .db import jload, now

MAX_ALIASES_PER_TAG = 300

PROMPT = """\
I keep a personal catalog of web novels collected from book sites (Wattpad, Author.Today, Ficbook, Litnet,
RanobeLib and others). My app maps the sites' labels onto one list of SHARED TAGS. Tags form a family tree:
a book with a tag automatically gets the tag's parents too (every LitRPG book is also "RPG elements"), and
anti-tags are tags that contradict each other.

Over time many site labels became ALIASES of a broad tag, though plenty of them name something narrower or
something else. Below are TAGS TO IMPROVE, each with its names, description, links and aliases (with how many
of my books have each alias). Improve how they're organized:

1. Child tags. When several aliases of a tag (or one alias used by many books) name a narrower kind of it that
   a reader would want to search for, propose a new tag with that tag as its parent, and move those aliases to
   it. Books keep the broad tag through the parent link. Example: Non-human lead has the aliases
   "monster protagonist", "гг монстр", "гг паук", "Humanoid Protagonist", "animalcharacter", "герой животное",
   "Genderless Protagonist", "безполый" -> new tags Monster protagonist, Humanoid protagonist, Animal
   protagonist and Genderless protagonist, each with parents ["nonhuman-lead"], and those aliases move to them.
   If a shared tag already fits, use it instead of a new one.
2. Wrong aliases. An alias that means something else moves to the right tags; junk (site names, years,
   random words) is hidden.
3. Links. Add missing parent links (the tag's every book must also have the other tag), remove wrong ones,
   and add anti-tags for tags that can't both be true of one book. Be conservative.

Aliases that are just another way of writing the same tag (translations, spellings, short forms) stay as they
are: don't mention them.

Answer with JSON objects, one per line:
{"tag": "<id>"}
    write this for EVERY tag in TAGS TO IMPROVE, even when nothing changes, before any line about its aliases
{"tag": "<id>", "add_parents": ["<id>"], "remove_parents": [], "add_children": [], "remove_children": [], "add_anti": [], "remove_anti": []}
    changes to the tag's links (only the fields you need)
{"new_tag": {"id": "monster-protagonist", "en": "Monster protagonist", "ru": "ГГ монстр", "uk": "ГГ монстр", "category": "protagonist", "description": "The protagonist is a monster: a slime, a spider, a goblin...", "parents": ["nonhuman-lead"], "anti": []}}
    a new tag; write it before the aliases that move to it
{"alias": "<the alias exactly as given>", "tags": ["<id>", ...]}
    the alias now means these tags instead ("гг вампир" -> ["monster-protagonist", "vampires"])
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
- Categories: genre, theme, protagonist, setting, orientation, relationship, content, format, demographic,
  fandom.
- Answer only with JSON lines, all in one code block. No explanations.
"""


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
        if tid in done or not _size(tid):
            continue
        out.append(tid)
    exact = {t for t in out for k in keys if k in {T.key(n) for n in (t, *T.own_names(t))}}
    return sorted(out, key=lambda t: (t not in exact, -_size(t), t))


def export(q: str = "", category: str = "", reviewed: bool = False, limit: int = 600) -> dict:
    """A request for an AI chat: tags with their aliases, about `limit` aliases in all, and the shared tags."""
    c = db.conn()
    pool = candidates(q, category, reviewed)
    batch, n = [], 0
    for tid in pool:
        size = min(_size(tid), MAX_ALIASES_PER_TAG)
        if batch and n + size > limit:
            break
        batch.append(tid)
        n += size
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
        for field, ids in (("parents", T.direct_parents(tid)), ("children", T.children(tid)), ("anti", T.anti(tid))):
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
    return {"text": text, "tags": len(batch), "aliases": n, "total": len(pool), "chars": len(text),
            "reviewed": len(_reviewed())}


# ---------------------------------------------------------------- reading the reply
def _all_own_names() -> set[str]:
    return {T.key(n) for t in T.all_ids() for n in (t, *T.own_names(t))}


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

    def related(self, a: str, b: str) -> bool:
        return a in self.above(b) or b in self.above(a)


def _label(i: str, new: dict) -> str:
    return (new[i].get("label") or new[i].get("label_ru") or i) if i in new else T.info(i)["label"]


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
    own = _all_own_names()
    unknown = labels._unknown_index(db.conn())
    reviewed, links, aliases, seen = [], [], [], set()
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
            for field, kind, on in (("add_parents", "parent", True), ("remove_parents", "parent", False),
                                    ("add_children", "child", True), ("remove_children", "child", False),
                                    ("add_anti", "anti", True), ("remove_anti", "anti", False)):
                for x in labels._strs(o.get(field)):
                    other = labels._one_tag(x, new)
                    link = {"tag": tid, "label": _label(tid, new), "kind": kind, "on": on, "problem": None,
                            "other": other or x, "other_label": _label(other, new) if other else x}
                    link["key"] = f"{kind}:{tid}:{link['other']}:{int(on)}"
                    if link["key"] in seen:
                        continue
                    seen.add(link["key"])
                    child, parent = (tid, other) if kind == "parent" else (other, tid)
                    if other and other != tid and on and (
                            other in T.anti(tid) if kind == "anti" else parent in fam.parents(child)):
                        continue  # it's so already (often: a new tag's own parent, said twice)
                    links.append(link)
                    if not other:
                        link["problem"] = f"no tag “{x}”"
                    elif other == tid:
                        link["problem"] = "the same tag"
                    elif kind == "anti":
                        if on and fam.related(tid, other):
                            link["problem"] = "they're in the same family"
                        elif not on and other not in T.anti(tid):
                            link["problem"] = "not an anti-tag now"
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
            label = str(o["alias"]).strip()
            k = T.key(label)
            if not k or f"alias:{k}" in seen:
                continue
            seen.add(f"alias:{k}")
            before = T.canonical(label)
            it = {"key": f"alias:{k}", "label": label, "problem": None, "action": "tags", "ids": [], "tags": [],
                  "before": [{"id": i, "label": T.info(i)["label"]} for i in before if T.is_known(i)]}
            aliases.append(it)
            if k in own:
                it["problem"] = "it's a tag's own name: rename the tag instead"
                continue
            if not (before and all(T.is_known(i) for i in before)) and k not in unknown:
                it["problem"] = "not a label in your library"
                continue
            if o.get("hide") is True:
                it.update(action="hide")
                continue
            ids, bad = [], []
            for x in labels._strs(o.get("tags") if o.get("tags") is not None else o.get("tag")):
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
                it["problem"] = "no tags or hide"
            elif set(ids) == set(before):
                aliases.pop()  # it means that already
    used = {i for it in aliases if not it["problem"] for i in it["ids"]}
    used |= {x["other"] for x in links if not x["problem"]}
    new_tags = [labels._new_tag_out(t, new, used_by=sum(1 for it in aliases if t["id"] in it["ids"]))
                for t in new.values() if not t["same_as"]]
    counts = {"aliases": sum(1 for it in aliases if not it["problem"] and it["action"] == "tags"),
              "hide": sum(1 for it in aliases if not it["problem"] and it["action"] == "hide"),
              "links": sum(1 for x in links if not x["problem"]),
              "new_tags": sum(1 for t in new_tags if not t["problem"] and t["id"] in used),
              "problems": sum(1 for it in aliases if it["problem"]) + sum(1 for x in links if x["problem"])}
    return {"reviewed": [{"id": t, "label": T.info(t)["label"]} for t in reviewed], "new_tags": new_tags,
            "aliases": aliases, "links": links, "counts": counts}


def apply(text: str, keys=None, new_ids=None) -> dict:
    """Apply an AI's reply: the changes whose keys you kept ticked (all when None), with the new tags you kept."""
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
    links = [(x["kind"], x["tag"], x["other"], x["on"]) for x in filter(ok, preview["links"]) if x["other"] not in dropped]
    used = {i for _, ids in entries for i in ids} | {x[2] for x in links}
    make = [t for t in make if t["id"] in used]
    made = {t["id"] for t in make}
    # a new tag's own links first, so the answers' links can build on them
    links = [x for t in make for x in labels.new_tag_links(t) if T.is_known(x[2]) or x[2] in made] + links
    reviewed = [t["id"] for t in preview["reviewed"]]
    if not entries and not links and not made:
        if reviewed:
            _mark_reviewed(reviewed)
            return {"labels": 0, "books": 0, "links": 0, "new_tags": 0, "reviewed": len(reviewed), "import": None}
        raise ValueError("Nothing to apply: tick at least one change.")
    result = labels.apply_many(entries, [labels.new_tag_entry(t) for t in make], links)
    _mark_reviewed(reviewed)
    record = {"id": now().replace(":", "").replace("-", ""), "at": now(), "labels": result["previous"],
              "links": result["links"], "new_tags": sorted(made), "reviewed": reviewed,
              "count": result["labels"], "link_count": len(result["links"]), "books": result["books"]}
    db.set_setting("tag_imports", [record, *db.get_setting("tag_imports", [])][:30])
    return {"labels": result["labels"], "books": result["books"], "links": len(result["links"]),
            "new_tags": len(made), "reviewed": len(reviewed), "import": record["id"]}


def _mark_reviewed(ids) -> None:
    db.set_setting("tags_reviewed", sorted(_reviewed() | set(ids)))


def forget_reviewed() -> None:
    db.set_setting("tags_reviewed", [])


def imports() -> list[dict]:
    """Your imports of AI answers about tags, newest first."""
    return [{k: r.get(k) for k in ("id", "at", "count", "link_count", "books", "new_tags", "undone")}
            for r in db.get_setting("tag_imports", [])]


def undo(import_id: str) -> dict:
    """Put back every alias and link an import changed, and delete the tags it made (unless something else uses
    them). The tags it reviewed count as not reviewed again."""
    from . import tagedit  # local import: tagedit uses labels
    records = db.get_setting("tag_imports", [])
    rec = next((r for r in records if r.get("id") == import_id), None)
    if not rec or rec.get("undone"):
        raise ValueError("That import is already undone.")
    result = labels.apply_many(list(rec["labels"].items()),
                               links=[(k, a, b, not on) for k, a, b, on in reversed(rec.get("links") or [])])
    still_used = {i for ids in T.fixes().values() for i in ids}
    for tid in rec.get("new_tags", []):
        if tid not in still_used and tid in (T.user_config().get("tags") or {}):
            tagedit.delete(tid)
    db.set_setting("tags_reviewed", sorted(_reviewed() - set(rec.get("reviewed") or [])))
    rec["undone"] = True
    db.set_setting("tag_imports", records)
    return result
