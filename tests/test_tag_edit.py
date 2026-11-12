"""Editing tags from their pages: names and descriptions, new tags, parent/child links, anti-tags, aliases, reset."""
import importlib
import tomllib

import pytest


@pytest.fixture()
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKKEEPER_DATA", str(tmp_path))
    from bookkeeper import config
    importlib.reload(config)
    from bookkeeper import db, labels, library, matching, search, tagedit, tagquery, tags
    for m in (db, tags, matching, library, tagquery, search, labels, tagedit):
        importlib.reload(m)
    db.init(tmp_path / "test.db")
    tags.ensure_user_file()
    return db, tags, library, tagedit


def _book(library, n, labels_):
    from bookkeeper.sites.base import BookInfo
    return library.upsert_book("x", BookInfo(sid=str(n), url=f"u{n}", title=f"Book {n}", tags=list(labels_)))


def _tags(db, book_id):
    return {r[0] for r in db.conn().execute("SELECT DISTINCT tag FROM book_tags WHERE book_id=?", (book_id,))}


def test_names_description_and_reset(lib):
    db, T, library, E = lib
    book = _book(library, 1, ["Любовная история"])
    assert _tags(db, book) == {"любовная история"}
    E.edit("romance", {"label": "Love story", "label_ru": "Любовная история", "description": "Love is the plot."})
    assert T.info("romance")["label"] == "Love story" and T.describe("romance") == "Love is the plot."
    assert _tags(db, book) == {"romance"}            # the new name is now how the tag is written
    assert T.canonical("Romance") == ["romance"]      # the old name still works
    row = db.conn().execute("SELECT label, label_ru FROM tags WHERE id='romance'").fetchone()
    assert tuple(row) == ("Love story", "Любовная история")
    with pytest.raises(ValueError):
        E.edit("romance", {"label_uk": "Fantasy"})    # another tag's name
    E.edit("romance", {"description": ""})            # empty: back to Bookkeeper's own
    assert T.describe("romance") == T.DESCRIPTIONS.get("romance")
    E.reset("romance")
    assert T.info("romance")["label"] == "Romance" and _tags(db, book) == {"любовная история"}


def test_new_tags(lib):
    db, T, library, E = lib
    a = _book(library, 1, ["Сложные отношения"])
    b = _book(library, 2, ["#сложныеотношения", "Романтика"])
    tid = E.create({"label": "Complicated relationships", "category": "relationship"}, from_label="Сложные отношения")
    assert tid == "сложные отношения" and T.is_known(tid)
    assert _tags(db, a) == {tid} and tid in _tags(db, b)  # the other spelling joined it
    assert db.conn().execute("SELECT known, category FROM tags WHERE id=?", (tid,)).fetchone()[:] == (1, "relationship")
    mine = E.create({"label": "Tea ceremony", "label_ru": "Чайная церемония", "category": "theme"})
    assert mine == "tea-ceremony" and T.canonical("чайная церемония") == ["tea-ceremony"]
    with pytest.raises(ValueError):
        E.create({"label": "Romance"})
    E.delete(tid)                                     # the label is back to being a plain site label
    assert not T.is_known(tid) and _tags(db, a) == {"сложные отношения"}
    with pytest.raises(ValueError):
        E.delete("romance")


def test_parents_children_and_anti_tags(lib):
    db, T, library, E = lib
    book = _book(library, 1, ["ЛитРПГ", "Гарем"])
    assert "rpg-elements" in _tags(db, book)
    E.link("parent", "litrpg", "gamelit", on=False)        # switch off one of Bookkeeper's own rules
    assert "gamelit" not in T.parents("litrpg") and "gamelit" not in _tags(db, book)
    assert "rpg-elements" in _tags(db, book)               # LitRPG still brings RPG elements directly
    E.link("parent", "litrpg", "gamelit", on=True)
    assert "gamelit" in _tags(db, book)
    data = tomllib.loads(T.config.USER_TAGS_FILE.read_text(encoding="utf-8"))
    assert not data.get("rules_off") and not data.get("rules", {}).get("litrpg")
    E.link("child", "comedy", "harem", on=True)            # every harem book is a comedy now
    assert "harem" in T.children("comedy") and "comedy" in _tags(db, book)
    E.link("child", "comedy", "harem", on=False)
    assert "comedy" not in _tags(db, book)
    with pytest.raises(ValueError):
        E.link("parent", "rpg-elements", "litrpg", on=True)  # would go round in a circle
    E.link("anti", "harem", "no-harem", on=False)
    assert "no-harem" not in T.anti("harem") and "harem" not in T.anti("no-harem")
    E.link("anti", "isekai", "slice-of-life", on=True)
    assert "isekai" in T.anti("slice-of-life")
    with pytest.raises(ValueError):
        E.link("anti", "litrpg", "rpg-elements", on=True)    # same family


def test_aliases(lib):
    db, T, library, E = lib
    book = _book(library, 1, ["Ромком без драмы", "Любовная линия"])
    E.alias("romance", "Ромком без драмы", on=True)
    assert "Ромком без драмы" in T.aliases("romance") and "romance" in _tags(db, book)
    E.alias("romance", "Ромком без драмы", on=False)
    assert "ромком без драмы" in _tags(db, book)
    E.alias("romance", "Любовная линия", on=True)            # Bookkeeper read it as "Romantic subplot"
    assert "romantic-subplot" not in _tags(db, book)
    E.alias("romance", "Любовная линия", on=False)           # your fix undone: back to Bookkeeper's reading
    assert "romantic-subplot" in _tags(db, book)
    E.alias("romance", "Любовь", on=False)                  # one of Bookkeeper's own aliases
    assert "Любовь" not in T.aliases("romance") and T.canonical("любовь") == ["любовь"]
    with pytest.raises(ValueError):
        E.alias("romance", "Fantasy", on=True)              # that's another tag's name
