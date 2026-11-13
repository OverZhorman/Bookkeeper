"""Improving shared tags with an AI chat: aliases move to new child tags, links change, and it all undoes."""
import importlib
import json

import pytest


@pytest.fixture()
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKKEEPER_DATA", str(tmp_path))
    from bookkeeper import config
    importlib.reload(config)
    from bookkeeper import db, labels, library, matching, search, tagai, tagedit, tagquery, tags
    for m in (db, tags, matching, library, tagquery, search, labels, tagedit, tagai):
        importlib.reload(m)
    db.init(tmp_path / "test.db")
    tags.ensure_user_file()
    return db, tags, library, labels, tagai


def _book(library, n, labels_):
    from bookkeeper.sites.base import BookInfo
    return library.upsert_book("x", BookInfo(sid=str(n), url=f"u{n}", title=f"Book {n}", tags=list(labels_)))


def _all(db, book_id):
    return {r[0] for r in db.conn().execute("SELECT DISTINCT tag FROM book_tags WHERE book_id=?", (book_id,))}


REPLY = """```json
{"tag": "nonhuman-lead"}
{"new_tag": {"id": "monster-protagonist", "en": "Monster protagonist", "ru": "ГГ монстр", "category": "protagonist", "parents": ["nonhuman-lead"]}}
{"new_tag": {"id": "genderless-protagonist", "en": "Genderless protagonist", "category": "protagonist", "parents": ["Non-human lead", "no-such-tag"]}}
{"alias": "гг паук", "tags": ["monster-protagonist"]}
{"alias": "monster protagonist", "tags": ["monster-protagonist"]}
{"alias": "Genderless Protagonist", "tags": ["genderless-protagonist"]}
{"alias": "нечеловеческие", "hide": true}
{"alias": "ГГ не человек", "hide": true}
{"alias": "non-human protagonist", "tags": ["nonhuman-lead"]}
{"tag": "monster-protagonist", "add_anti": ["genderless-protagonist"]}
{"tag": "nonhuman-lead", "add_children": ["monster-protagonist"], "add_parents": ["monster-protagonist"]}
{"tag": "harem", "add_anti": ["no-harem"]}
```"""


def test_export_lists_tags_with_their_aliases(lib):
    db, T, library, labels, tagai = lib
    _book(library, 1, ["гг паук", "гг паук"])
    _book(library, 2, ["гг паук", "Monster protagonist"])
    library.refresh_tag_counts()
    out = tagai.export(q="non-human lead")
    assert out["tags"] == 1 and "TAGS TO IMPROVE (1" in out["text"]
    item = json.loads(out["text"].split("TAGS TO IMPROVE (1, one JSON object per line)\n")[1].splitlines()[0])
    assert item["tag"] == "nonhuman-lead" and item["books"] == 2
    assert list(item["aliases"])[0] == "гг паук" and item["aliases"]["гг паук"] == 2
    assert item["aliases"]["monster protagonist"] == 1
    # without a filter: the tags with most aliases first, fandoms left out, about `limit` aliases in all
    many = tagai.export(limit=50)
    assert many["tags"] >= 1 and "fandom-" not in many["text"].split("TAGS TO IMPROVE")[1]


def test_check_apply_and_undo(lib):
    db, T, library, labels, tagai = lib
    a = _book(library, 1, ["гг паук"])
    b = _book(library, 2, ["Genderless Protagonist"])
    c = _book(library, 3, ["нечеловеческие", "Гарем"])
    labels.fix("нечеловеческие", ["nonhuman-lead"])  # an alias you made earlier
    library.refresh_tag_counts()
    assert "nonhuman-lead" in _all(db, a) and "nonhuman-lead" in _all(db, c)

    p = tagai.check(REPLY)
    new = {t["id"]: t for t in p["new_tags"]}
    assert [x["id"] for x in new["monster-protagonist"]["parents"]] == ["nonhuman-lead"]
    assert [x["id"] for x in new["genderless-protagonist"]["parents"]] == ["nonhuman-lead"]  # a name works too
    assert new["genderless-protagonist"]["unknown"] == ["no-such-tag"]
    al = {x["label"]: x for x in p["aliases"]}
    assert al["гг паук"]["ids"] == ["monster-protagonist"] and not al["гг паук"]["problem"]
    assert al["нечеловеческие"]["action"] == "hide"
    assert al["ГГ не человек"]["problem"]                  # a tag's own name is never hidden
    assert "non-human protagonist" not in al               # it means that already: left out
    ln = {(x["kind"], x["tag"], x["other"]): x for x in p["links"]}
    assert ("child", "nonhuman-lead", "monster-protagonist") not in ln   # the new tag's own parent, said twice
    assert "narrower" in ln[("parent", "nonhuman-lead", "monster-protagonist")]["problem"]  # a loop
    assert not ln[("anti", "monster-protagonist", "genderless-protagonist")]["problem"]
    assert [t["id"] for t in p["reviewed"]] == ["nonhuman-lead", "harem"]  # new tags aren't "reviewed"

    r = tagai.apply(REPLY)
    assert r["new_tags"] == 2 and r["labels"] == 4
    assert T.is_known("monster-protagonist") and T.parents("monster-protagonist") == ["nonhuman-lead"]
    assert _all(db, a) >= {"monster-protagonist", "nonhuman-lead"}          # the parent comes along
    assert _all(db, b) >= {"genderless-protagonist", "nonhuman-lead"}
    assert "нечеловеческие" not in _all(db, c) and "nonhuman-lead" not in _all(db, c)
    assert "genderless-protagonist" in T.anti("monster-protagonist")
    assert "nonhuman-lead" in tagai._reviewed()
    assert tagai.candidates() and "nonhuman-lead" not in tagai.candidates()  # reviewed: not in the next batch
    assert "nonhuman-lead" in tagai.candidates(q="nonhuman-lead")           # unless asked for by name

    tagai.undo(r["import"])
    assert not T.is_known("monster-protagonist") and not T.is_known("genderless-protagonist")
    assert "nonhuman-lead" in _all(db, a) and "monster-protagonist" not in _all(db, a)
    assert "nonhuman-lead" in _all(db, c)
    assert "nonhuman-lead" not in tagai._reviewed()
    assert not (T.user_config().get("rules") or {}) and not (T.user_config().get("anti") or {})


def test_links_between_existing_tags(lib):
    db, T, library, labels, tagai = lib
    a = _book(library, 1, ["Гарем"])
    library.refresh_tag_counts()
    reply = '{"tag": "harem", "add_parents": ["comedy"]}\n{"tag": "litrpg", "remove_parents": ["rpg-elements"]}'
    p = tagai.check(reply)
    assert {(x["kind"], x["other"], x["on"]) for x in p["links"] if not x["problem"]} == {
        ("parent", "comedy", True), ("parent", "rpg-elements", False)}
    r = tagai.apply(reply)
    assert "comedy" in _all(db, a) and "rpg-elements" not in T.parents("litrpg")
    tagai.undo(r["import"])
    assert "comedy" not in _all(db, a) and "rpg-elements" in T.parents("litrpg")


def test_my_tags_file_comes_back_as_it_was(lib):
    db, T, library, labels, tagai = lib
    path = T.config.USER_TAGS_FILE
    path.write_text(path.read_text(encoding="utf-8").replace(
        '[rules]\n# "harem" = ["romance"]\n', '[rules]\n# "harem" = ["romance"]\n\n# Add or rename tags:\n# [tags.x]\n'),
        encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    r = tagai.apply('{"tag": "harem", "add_parents": ["comedy"], "add_anti": ["slice-of-life"]}')
    text = path.read_text(encoding="utf-8")
    assert 'harem = ["comedy"]' in text and "# Add or rename tags:\n# [tags.x]\n" in text  # the example stays
    tagai.undo(r["import"])
    assert path.read_text(encoding="utf-8") == before


def test_label_import_new_tag_with_parent(lib):
    db, T, library, labels, tagai = lib
    a = _book(library, 1, ["гг слизень"])
    library.refresh_tag_counts()
    reply = ('{"new_tag": {"id": "slime-lead", "en": "Slime lead", "category": "protagonist", "parents": ["nonhuman-lead"]}}\n'
             '{"label": "гг слизень", "tags": ["slime-lead"]}')
    p = labels.check_import(reply)
    assert [x["id"] for x in p["new_tags"][0]["parents"]] == ["nonhuman-lead"]
    r = labels.apply_import(reply)
    assert _all(db, a) >= {"slime-lead", "nonhuman-lead"}
    labels.undo_import(r["import"])
    assert not T.is_known("slime-lead") and "гг слизень" in _all(db, a)
    assert not (T.user_config().get("rules") or {})


NAMES_REPLY = "\n".join([
    '{"tag": "nonhuman-lead", "en": "Non-human protagonist", "uk": "Нелюдський головний герой", '
    '"description": "The main character isn\'t human.", "category": "nonsense", "add_related": ["isekai", "magic"], '
    '"add_aliases": ["Spider MC", "нечеловек-гг", "ГГ не человек"]}',
    '{"tag": "harem", "en": "Fantasy", "ru": "гг паук"}',
    '{"tag": "slime-lead", "en": "Slime protagonist"}',
    '{"tag": "isekai", "remove_related": ["magic"], "add_related": ["into-game"]}',
    '{"alias": "monster protagonist", "keep": true}',
    '{"alias": "brand new label", "hide": true}',
    '{"alias": "магический детектив новый", "tags": ["magic", "mystery"]}',
])


def test_names_descriptions_new_aliases_and_related(lib):
    db, T, library, labels, tagai = lib
    from bookkeeper import search, tagedit
    a = _book(library, 1, ["Spider MC"])            # a label no shared tag knows
    b = _book(library, 2, ["Monster protagonist"])  # an alias of Non-human lead
    s = _book(library, 3, ["Slime hero"])
    tagedit.edit(tagedit.create({"label": "Slime lead", "category": "protagonist"}), {"label": "Slime hero"})
    library.refresh_tag_counts()
    path = T.config.USER_TAGS_FILE
    before = path.read_text(encoding="utf-8")
    assert "nonhuman-lead" in _all(db, b) and "slime-lead" in _all(db, s)

    p = tagai.check(NAMES_REPLY)
    ed = {(x["tag"], x["field"]): x for x in p["edits"]}
    assert not ed[("nonhuman-lead", "label")]["problem"] and not ed[("nonhuman-lead", "label")]["keep"]  # a built-in name stays anyway
    assert not ed[("nonhuman-lead", "description")]["problem"] and not ed[("nonhuman-lead", "label_uk")]["problem"]
    assert "no category" in ed[("nonhuman-lead", "category")]["problem"]
    assert "name of" in ed[("harem", "label")]["problem"]                  # Fantasy's own name
    assert "already means" in ed[("harem", "label_ru")]["problem"]         # Non-human lead's alias
    assert ed[("slime-lead", "label")]["keep"] == "Slime hero"             # your tag's old name stays an alias
    al = {x["label"]: x for x in p["aliases"]}
    assert al["Spider MC"]["ids"] == ["nonhuman-lead"] and not al["Spider MC"]["new"]
    assert al["нечеловек-гг"]["new"] and not al["нечеловек-гг"]["problem"]  # no book has it yet
    assert "ГГ не человек" not in al                                        # the tag's own name: nothing to do
    assert al["monster protagonist"]["action"] == "keep"
    assert al["brand new label"]["problem"]                                 # nothing to hide
    assert al["магический детектив новый"]["ids"] == ["magic", "mystery"] and al["магический детектив новый"]["new"]
    ln = {(x["kind"], x["tag"], x["other"], x["on"]): x for x in p["links"]}
    assert not ln[("related", "nonhuman-lead", "isekai", True)]["problem"]
    assert "not related now" in ln[("related", "isekai", "magic", False)]["problem"]
    assert "same family" in ln[("related", "isekai", "into-game", True)]["problem"]

    r = tagai.apply(NAMES_REPLY)
    assert r["edits"] == 4
    assert T.info("nonhuman-lead")["label"] == "Non-human protagonist"
    assert T.info("nonhuman-lead")["label_uk"] == "Нелюдський головний герой"
    assert T.describe("nonhuman-lead") == "The main character isn't human."
    assert T.canonical("Non-human lead") == ["nonhuman-lead"]
    assert T.info("slime-lead")["label"] == "Slime protagonist" and T.canonical("Slime hero") == ["slime-lead"]
    assert "slime-lead" in _all(db, s)
    assert T.related("nonhuman-lead") == ["isekai", "magic"] and T.related("isekai") == ["nonhuman-lead"]
    assert "nonhuman-lead" in _all(db, a)
    assert T.canonical("нечеловек-гг") == ["nonhuman-lead"]
    assert T.canonical("магический детектив новый") == ["magic", "mystery"]
    assert "nonhuman-lead" not in _all(db, b) and "monster protagonist" in _all(db, b)
    page = search.tag_page("nonhuman-lead")
    assert [x["id"] for x in page["see_also"]] == ["isekai", "magic"]
    assert "isekai" not in [x["id"] for x in page["related"]]
    assert [x["edit_count"] for x in tagai.imports()] == [4]

    tagai.undo(r["import"])
    assert T.info("nonhuman-lead")["label"] == "Non-human lead" and T.describe("nonhuman-lead") != "The main character isn't human."
    assert T.info("slime-lead")["label"] == "Slime hero"
    assert T.related("nonhuman-lead") == []
    assert "nonhuman-lead" not in _all(db, a) and "nonhuman-lead" in _all(db, b)
    assert T.canonical("нечеловек-гг") != ["nonhuman-lead"]
    assert path.read_text(encoding="utf-8") == before


def test_related_links_by_hand(lib):
    db, T, library, labels, tagai = lib
    from bookkeeper import tagedit
    tagedit.link("related", "harem", "comedy", True)
    assert T.related("harem") == ["comedy"] and T.related("comedy") == ["harem"]
    assert tagedit.has_changes("comedy")
    with pytest.raises(ValueError):
        tagedit.link("related", "isekai", "into-game", True)  # a child: its page shows it already
    tagedit.link("related", "comedy", "harem", False)          # either side removes the pair
    assert T.related("harem") == []
    mine = tagedit.create({"label": "Slime lead", "category": "protagonist"})
    tagedit.link("related", mine, "harem", True)
    tagedit.delete(mine)
    assert T.related("harem") == [] and not (T.user_config().get("related") or {})
