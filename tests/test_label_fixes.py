"""Fixing site labels once for every book: map, hide, keep separate, undo, and my_tags.toml staying intact."""
import importlib
import tomllib

import pytest


@pytest.fixture()
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKKEEPER_DATA", str(tmp_path))
    from bookkeeper import config
    importlib.reload(config)
    from bookkeeper import db, labels, library, matching, search, tagquery, tags
    importlib.reload(db); importlib.reload(tags); importlib.reload(matching); importlib.reload(library)
    importlib.reload(tagquery); importlib.reload(search); importlib.reload(labels)
    db.init(tmp_path / "test.db")
    tags.ensure_user_file()
    return db, tags, library, labels


def _book(library, n, labels_):
    from bookkeeper.sites.base import BookInfo
    return library.upsert_book("x", BookInfo(sid=str(n), url=f"u{n}", title=f"Book {n}", tags=list(labels_)))


def _tags(db, book_id):
    return {r[0] for r in db.conn().execute("SELECT tag FROM book_tags WHERE book_id=? AND source='site'", (book_id,))}


def test_a_fix_applies_to_every_book_and_can_be_undone(lib):
    db, T, library, labels = lib
    a = _book(library, 1, ["Попаданиевдругоймир", "Попаданцы"])
    b = _book(library, 2, ["#попаданиевдругоймир"])
    _book(library, 3, ["Романтика"])
    library.refresh_tag_counts()
    listed = labels.unrecognized()["labels"]
    assert len(listed) == 1 and listed[0]["books"] == 2      # two spellings, one row
    assert listed[0]["spellings"] in (["Попаданиевдругоймир"], ["#попаданиевдругоймир"])
    assert "isekai" in [s["id"] for s in listed[0]["suggestions"]]  # «попада(нцы)» is in the name

    result = labels.fix("попаданиевдругоймир", ["isekai"])
    assert result["books"] == 2                       # both spellings
    assert _tags(db, a) == {"isekai"} and _tags(db, b) == {"isekai"}
    assert labels.unrecognized()["labels"] == []
    assert db.conn().execute("SELECT books FROM tags WHERE id='isekai'").fetchone()[0] == 2
    assert db.conn().execute("SELECT 1 FROM tags WHERE id='попаданиевдругоймир'").fetchone() is None
    c = _book(library, 4, ["ПопаданиеВДругойМир"])     # books that arrive later follow the fix
    assert _tags(db, c) == {"isekai"}
    assert [f["label"] for f in labels.my_fixes()] == ["попаданиевдругоймир"]
    assert labels.my_fixes()[0]["books"] == 3

    labels.fix("попаданиевдругоймир", None)           # undo: book 1 gets its own label back too,
    assert _tags(db, a) == {"isekai", "попаданиевдругоймир"}  # though it shared Isekai with «Попаданцы»
    assert _tags(db, b) == {"#попаданиевдругоймир"}
    assert labels.my_fixes() == []


def test_hide_keep_separate_and_follow(lib):
    db, T, library, labels = lib
    a = _book(library, 1, ["wattpad", "ЛитРПГ"])
    b = _book(library, 2, ["отношения сложные"])
    c = _book(library, 3, ["Сложные отношения", "сложныеотношения"])  # one label to Bookkeeper (spaces don't count)
    library.refresh_tag_counts()
    assert labels.fix("Wattpad", [])["hidden"]
    assert _tags(db, a) == {"litrpg"}
    labels.fix("wattpad", None)                       # hidden labels come back
    assert _tags(db, a) == {"litrpg", "wattpad"}

    labels.fix("ЛитРПГ", None, separate=True)        # Bookkeeper's mapping was "wrong": keep it as its own tag
    assert _tags(db, a) == {"литрпг", "wattpad"}
    labels.fix("ЛитРПГ", None)
    assert _tags(db, a) == {"litrpg", "wattpad"}

    assert _tags(db, c) == {"сложные отношения", "сложныеотношения"}  # two tags until fixed…
    assert [x["books"] for x in labels.unrecognized(q="сложные")["labels"]] == [2, 1]  # …but one row to fix
    labels.fix("отношения сложные", ["сложные отношения"])  # one label means the other…
    assert _tags(db, b) == {"сложные отношения"}
    labels.fix("Сложные отношения", ["romance"])           # …so when that one gets fixed, it follows
    assert _tags(db, b) == {"romance"} and _tags(db, c) == {"romance"}
    assert T.fixes()["отношения сложные"] == ["romance"]

    with pytest.raises(ValueError):
        labels.fix("anything", ["no-such-tag-anywhere"])


def test_fixes_keep_the_rest_of_my_tags_toml(lib):
    db, T, library, labels = lib
    from bookkeeper import config
    config.USER_TAGS_FILE.write_text(
        '# my notes\n[synonyms]\n"моя метка" = ["isekai"]  # mine\n\n[fixes]\n"old" = ["romance"]\n\n'
        '# about my own tag\n[tags.my-tag]\nlabel = "My tag"\n', encoding="utf-8")
    T.set_fix("Новая метка", ["fantasy"])
    T.set_fix("old", None)
    T.set_fix("Скрыть", [])
    text = config.USER_TAGS_FILE.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    assert data["synonyms"] == {"моя метка": ["isekai"]} and data["tags"]["my-tag"]["label"] == "My tag"
    assert data["fixes"] == {"Новая метка": ["fantasy"], "Скрыть": []}
    assert "# my notes" in text and "# mine" in text and "# about my own tag\n[tags.my-tag]" in text
    T.reload()
    assert T.canonical("НОВАЯ МЕТКА") == ["fantasy"] and T.canonical("скрыть") == []


def test_labels_are_kept_as_written(lib):
    db, T, library, labels = lib
    book = _book(library, 1, ["Попаданцы", "Isekai", "непонятное"])
    assert library._site_labels(db.conn(), book) == ["Попаданцы", "Isekai", "непонятное"]
    # Libraries from before 0.4.1 get their labels back from the tags once, on start.
    db.conn().execute("UPDATE books SET labels = NULL")
    path = db._initialized_path
    db._initialized_path = None
    db.init(path)
    assert sorted(library._site_labels(db.conn(), book)) == ["Попаданцы", "непонятное"]  # one label per tag before
