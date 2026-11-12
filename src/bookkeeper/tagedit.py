"""Editing tags from their pages: names, category, description, aliases, parent and child tags, anti-tags, and
tags of your own. Everything is saved in my_tags.toml ([tags.<id>], [rules], [rules_off], [anti], [anti_off]
and [fixes]), so it survives updates and can also be changed by hand."""
import re
import threading

from . import db, labels, library, search
from . import tags as T

FIELDS = ("label", "label_ru", "label_uk", "category", "description")
NAMES = ("label", "label_ru", "label_uk")
_LOCK = threading.Lock()


def _table(name: str) -> dict[str, list[str]]:
    return {k: T._as_list(v) for k, v in (T.user_config().get(name) or {}).items()}


def _clean(table: dict) -> dict:
    return {k: list(dict.fromkeys(v)) for k, v in table.items() if v}


def _my_tags() -> dict:
    return {k: dict(v) for k, v in (T.user_config().get("tags") or {}).items() if isinstance(v, dict)}


def builtin(tag_id: str) -> dict:
    """Bookkeeper's own names, category and description for a tag ({} for tags you made)."""
    if tag_id not in T.TAGS:
        return {}
    en, ru, cat, _ = T.TAGS[tag_id]
    return {"label": en, "label_ru": ru, "label_uk": T.UK.get(tag_id), "category": cat,
            "description": T.DESCRIPTIONS.get(tag_id)}


def _check_names(tag_id: str, names) -> None:
    """A name can't already be another shared tag's name or alias (it would take that tag's books)."""
    for name in names:
        if not name:
            continue
        others = [t for t in T.canonical(name) if t != tag_id and T.is_known(t)]
        if others:
            raise ValueError(f"“{name}” already means {T.info(others[0])['label']}. Pick another name, "
                             f"or edit that tag instead.")


def _books_of_changed_names(names, before: dict) -> set[int]:
    """Books with labels that now mean something else, because a tag got or lost a name."""
    c, out = db.conn(), set()
    for name in names:
        if name and T.key(name) and T.canonical(name) != before[name]:
            out |= labels._books_with(c, name, mapped_to=before[name])
    return out


def has_changes(tag_id: str) -> bool:
    """Whether you changed one of Bookkeeper's own tags (names, description, links, anti-tags)."""
    if tag_id in _my_tags():
        return True
    for name in ("rules", "rules_off", "anti", "anti_off"):
        for k, v in _table(name).items():
            if k == tag_id or tag_id in v:
                return True
    return False


def page_extras(tag_id: str) -> dict:
    """What the tag page needs for editing."""
    c = db.conn()
    i = T.info(tag_id)
    known = T.is_known(tag_id)
    return {
        "editable": known,
        "user_tag": known and tag_id not in T.TAGS,
        "edited": tag_id in T.TAGS and has_changes(tag_id),
        "builtin": builtin(tag_id),
        "values": {**{k: i.get(k) for k in ("label", "label_ru", "label_uk", "category")},
                   "description": T.describe(tag_id)},
        "parents_all": search._brief(c, T.parents(tag_id)),
        "children_direct": search._brief(c, sorted(T.children(tag_id), key=lambda t: T.info(t)["label"].lower())),
    }


def edit(tag_id: str, fields: dict) -> None:
    """Change a shared tag's names, category or description. An empty value goes back to Bookkeeper's own."""
    if not T.is_known(tag_id):
        raise ValueError("This label isn't a shared tag yet. Make it one first (Fix this label → Make it a shared tag).")
    with _LOCK:
        base = builtin(tag_id)
        mine = _my_tags().get(tag_id, {})
        for k in FIELDS:
            if k not in fields:
                continue
            value = (fields.get(k) or "").strip()
            if k == "category" and value and value not in T.CATEGORY_ORDER:
                raise ValueError(f"There's no category “{value}”.")
            if value and value != (base.get(k) or ""):
                mine[k] = value
            else:
                mine.pop(k, None)
        if tag_id not in T.TAGS and not any(mine.get(k) for k in NAMES):
            raise ValueError("A tag needs a name.")
        _check_names(tag_id, [mine.get(k) for k in NAMES])
        names = [*T.own_names(tag_id), *(mine.get(k) for k in NAMES if mine.get(k))]
        before = {n: T.canonical(n) for n in names}
        if tag_id not in T.TAGS and not mine.get("label"):
            mine["label"] = mine.get("label_ru") or mine.get("label_uk")
        T.write_tables({("tags", tag_id): mine or None})
        T.reload()
    library.sync_tag_rows([tag_id])
    affected = _books_of_changed_names(names, before)
    if affected:
        library.retag_books(affected)


def _new_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or T.own_id(name)


def create(fields: dict, from_label: str | None = None) -> str:
    """Make a new shared tag. With from_label, a site label becomes the shared tag (its books keep it, and its other
    spellings join it). Returns the tag's id."""
    names = {k: (fields.get(k) or "").strip() for k in NAMES}
    from_label = (from_label or "").strip() or None
    if from_label and not any(names.values()):
        names["label_ru" if re.search(r"[а-яёіїєґ]", from_label.lower()) else "label"] = from_label
    if not any(names.values()):
        raise ValueError("Give the tag a name.")
    category = (fields.get("category") or "theme").strip()
    if category not in T.CATEGORY_ORDER:
        raise ValueError(f"There's no category “{category}”.")
    with _LOCK:
        if from_label:
            tid = T.own_id(from_label)
            if T.is_known(tid):
                raise ValueError(f"“{from_label}” is a shared tag already.")
        else:
            base = _new_id(names["label"] or names["label_ru"] or names["label_uk"])
            tid, n = base, 2
            while T.is_known(tid):
                tid, n = f"{base}-{n}", n + 1
        _check_names(tid, names.values())
        all_names = [n for n in names.values() if n] + ([from_label] if from_label else [])
        before = {n: T.canonical(n) for n in all_names}
        entry = {k: v for k, v in names.items() if v}
        entry.setdefault("label", names["label_ru"] or names["label_uk"])
        entry["category"] = category
        if (fields.get("description") or "").strip():
            entry["description"] = fields["description"].strip()
        T.write_tables({("tags", tid): entry})
        T.reload()
    library.sync_tag_rows([tid])
    affected = _books_of_changed_names(all_names, before)
    if from_label:  # every spelling of the label joins the new tag
        affected |= labels._books_with(db.conn(), from_label, mapped_to=before[from_label])
    if affected:
        library.retag_books(affected)
    return tid


def link(kind: str, tag_id: str, other: str, on: bool) -> None:
    """Add (on) or remove a link from tag_id: kind "parent" (other is broader), "child" (other is narrower) or
    "anti" (they contradict each other). Bookkeeper's own links can be switched off and on again."""
    if kind == "child":  # "other is a child of tag_id" is the same as "tag_id is a parent of other"
        kind, tag_id, other = "parent", other, tag_id
    if kind not in ("parent", "anti"):
        raise ValueError("Unknown kind of link.")
    for t in (tag_id, other):
        if not (T.is_known(t) or search.tag_exists(t)):
            raise ValueError(f"There's no tag “{t}”.")
    if tag_id == other:
        raise ValueError("A tag can't be linked to itself.")
    with _LOCK:
        if kind == "parent":
            if on and not T.is_known(other):
                raise ValueError(f"“{T.info(other)['label']}” isn't a shared tag, so it can't be a parent. "
                                 f"Make it a shared tag first.")
            if on and other in T.descendants(tag_id):
                raise ValueError(f"{T.info(other)['label']} is already narrower than {T.info(tag_id)['label']}, "
                                 f"so it can't be broader too.")
        elif on and (other in T.ancestors(tag_id) or other in T.descendants(tag_id)):
            raise ValueError(f"{T.info(other)['label']} and {T.info(tag_id)['label']} are in the same family, "
                             f"so they can't contradict each other.")
        tabs = link_tables()
        set_link(tabs, kind, tag_id, other, on)
        T.write_tables(link_changes(tabs))
        T.reload()
    if kind == "parent":
        library.refresh_rules_for([tag_id])


def link_tables() -> dict[str, dict[str, list[str]]]:
    """my_tags.toml's link tables as they are now, to change with set_link() and save with link_changes()."""
    return {name: _table(name) for name in ("rules", "rules_off", "anti", "anti_off")}


def link_changes(tabs: dict) -> dict:
    return {(name,): _clean(v) for name, v in tabs.items()}


def set_link(tabs: dict, kind: str, tag_id: str, other: str, on: bool) -> None:
    """Add (on) or remove one link in the tables from link_tables(), without checking it: kind "parent" (other is
    broader than tag_id), "child" (other is narrower) or "anti". Bookkeeper's own links are switched off, not lost."""
    if kind == "child":
        kind, tag_id, other = "parent", other, tag_id
    if kind == "parent":
        ours = other in T.RULES.get(tag_id, [])
        rules, off = tabs["rules"], tabs["rules_off"]
        rules[tag_id] = [x for x in rules.get(tag_id, []) if x != other]
        off[tag_id] = [x for x in off.get(tag_id, []) if x != other]
        if on and not ours:
            rules[tag_id].append(other)
        if not on and ours:
            off[tag_id].append(other)
    elif kind == "anti":
        ours = other in T.ANTI.get(tag_id, []) or tag_id in T.ANTI.get(other, [])
        pair = {tag_id, other}
        anti = {k: [x for x in v if {k, x} != pair] for k, v in tabs["anti"].items()}
        off = {k: [x for x in v if {k, x} != pair] for k, v in tabs["anti_off"].items()}
        if on and not ours:
            anti.setdefault(tag_id, []).append(other)
        if not on and ours:
            off.setdefault(tag_id, []).append(other)
        tabs["anti"], tabs["anti_off"] = anti, off
    else:
        raise ValueError("Unknown kind of link.")


def alias(tag_id: str, name: str, on: bool) -> dict:
    """Add an alias (a label written this way means this tag, for every book) or take one away."""
    name = (name or "").strip()
    if not T.key(name):
        raise ValueError("Type the other name first.")
    if not T.is_known(tag_id):
        raise ValueError("Only shared tags have aliases.")
    if on:
        for t in T.all_ids():
            if t != tag_id and T.key(name) in {T.key(n) for n in T.own_names(t)}:
                raise ValueError(f"“{name}” is the name of {T.info(t)['label']}. Rename that tag first.")
        return labels.fix(name, [tag_id])
    result = {"books": 0}
    if T.fixes() and any(T.key(n) == T.key(name) and ids == [tag_id] for n, ids in T.fixes().items()):
        result = labels.fix(name, None)  # it was your fix: undo it
    if tag_id in T.canonical(name):  # Bookkeeper's own alias (or your synonym): keep the label apart
        result = labels.fix(name, None, separate=True)
    return result


def _drop_links(tag_id: str) -> tuple[dict, set[str]]:
    """my_tags.toml tables without any link or anti-tag that involves tag_id, and the tags whose rules change."""
    rules, off = _table("rules"), _table("rules_off")
    touched = {tag_id} | {k for k, v in rules.items() if tag_id in v} | {k for k, v in off.items() if tag_id in v}
    rules = {k: [x for x in v if x != tag_id] for k, v in rules.items() if k != tag_id}
    off = {k: [x for x in v if x != tag_id] for k, v in off.items() if k != tag_id}
    anti = {k: [x for x in v if x != tag_id] for k, v in _table("anti").items() if k != tag_id}
    aoff = {k: [x for x in v if x != tag_id] for k, v in _table("anti_off").items() if k != tag_id}
    return {("rules",): _clean(rules), ("rules_off",): _clean(off), ("anti",): _clean(anti),
            ("anti_off",): _clean(aoff)}, touched


def reset(tag_id: str) -> None:
    """Undo everything you changed on one of Bookkeeper's own tags: names, category, description, its parent and
    child links and anti-tags. Label fixes stay (they're on the Fix site labels page)."""
    if tag_id not in T.TAGS:
        raise ValueError("This is a tag you made; delete it instead.")
    with _LOCK:
        changes, touched = _drop_links(tag_id)
        changes[("tags", tag_id)] = None
        names = [*T.own_names(tag_id), *builtin(tag_id).values()]
        names = [n for n in names if isinstance(n, str)]
        before = {n: T.canonical(n) for n in names}
        T.write_tables(changes)
        T.reload()
    library.sync_tag_rows([tag_id])
    affected = _books_of_changed_names(names, before)
    if affected:
        library.retag_books(affected)
    library.refresh_rules_for(touched)


def delete(tag_id: str) -> None:
    """Delete a tag you made. Its books keep their site labels; labels you fixed to mean it go back to the list of
    labels to fix."""
    if tag_id in T.TAGS:
        raise ValueError("Bookkeeper's own tags can't be deleted. You can rename them, or hide their labels.")
    if tag_id not in _my_tags():
        raise ValueError("There's no tag of yours with that id.")
    with _LOCK:
        changes, touched = _drop_links(tag_id)
        changes[("tags", tag_id)] = None
        fixes = {}
        for name, ids in T.fixes().items():
            rest = [x for x in ids if x != tag_id]
            if rest or not ids:
                fixes[name] = rest
        changes[("fixes",)] = dict(sorted(fixes.items(), key=lambda kv: T.key(kv[0])))
        c = db.conn()
        books = {r[0] for r in c.execute("SELECT DISTINCT book_id FROM book_tags WHERE tag=?", (tag_id,))}
        T.write_tables(changes)
        T.reload()
    library.sync_tag_rows([tag_id])
    library.retag_books(books)
    library.refresh_rules_for(touched - {tag_id})
