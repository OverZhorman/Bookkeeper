import importlib

import pytest


@pytest.fixture()
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKKEEPER_DATA", str(tmp_path))
    from bookkeeper import config
    importlib.reload(config)
    from bookkeeper import db, tags, library, matching
    importlib.reload(db); importlib.reload(tags); importlib.reload(matching); importlib.reload(library)
    db.init(tmp_path / "test.db")
    return db, tags, library, matching


def test_tag_synonyms_and_rules(lib):
    _, T, _, _ = lib
    assert T.canonical("ЛитРПГ") == ["litrpg"]
    assert T.canonical("LITRPG") == ["litrpg"]
    assert T.canonical("Lit-RPG") == ["litrpg"]
    assert T.canonical("Повествование от первого лица") == ["pov-first"]
    assert T.canonical("WEAKTOSTRONG") == ["progression"]
    assert set(T.canonical("Магическая академия")) == {"academy", "magic"}
    assert T.canonical("Совсем неизвестный тег") == ["совсем неизвестный тег"]
    assert {"rpg-elements", "gamelit"} <= T.implied({"litrpg"})


def test_book_pov_priority(lib):
    db, T, library, _ = lib
    from bookkeeper.sites.base import BookInfo
    bid = library.upsert_book("x", BookInfo(sid="1", url="u", title="Книга", tags=["ЛитРПГ"]))
    c = db.conn()
    tags = {r[0]: r[1] for r in c.execute("SELECT tag, source FROM book_tags WHERE book_id=?", (bid,))}
    assert tags["litrpg"] == "site" and tags["rpg-elements"] == "rule"
    assert c.execute("SELECT pov FROM books WHERE id=?", (bid,)).fetchone()[0] is None
    library.save_analysis(bid, {"pov": "third", "confidence": 1.0, "narrator": None, "details": {}})
    assert c.execute("SELECT pov, pov_source FROM books WHERE id=?", (bid,)).fetchone()[:] == ("third", "text")
    library.upsert_book("x", BookInfo(sid="1", url="u", title="Книга", tags=["ЛитРПГ", "от первого лица"]))
    assert c.execute("SELECT pov, pov_source FROM books WHERE id=?", (bid,)).fetchone()[:] == ("first", "site")
    library.set_user(bid, pov="second")
    assert c.execute("SELECT pov, pov_source FROM books WHERE id=?", (bid,)).fetchone()[:] == ("second", "user")


def test_cross_site_matching_shares_tags(lib):
    db, T, library, matching = lib
    from bookkeeper.sites.base import BookInfo
    a = library.upsert_book("ranobelib", BookInfo(sid="1", url="u1", title="Точка зрения Всеведущего читателя",
                                                  alt_titles=["Omniscient Reader's Viewpoint"], authors=["singNsong"],
                                                  is_translation=True, tags=["Апокалипсис"]))
    b = library.upsert_book("webnovel", BookInfo(sid="9", url="u2", title="Omniscient Reader's Viewpoint",
                                                 authors=["Sing Shong"], is_translation=True,
                                                 tags=["first person", "SYSTEM"]))
    library.upsert_book("webnovel", BookInfo(sid="10", url="u3", title="Something Else", authors=["X"]))
    assert matching.find_duplicates() == 1
    c = db.conn()
    w = {r[0]: r[1] for r in c.execute("SELECT id, work_id FROM books")}
    assert w[a] == w[b] is not None
    row = c.execute("SELECT pov, pov_source FROM books WHERE id=?", (a,)).fetchone()
    assert tuple(row) == ("first", "other-site")
    tags_a = {r[0] for r in c.execute("SELECT tag FROM book_tags WHERE book_id=?", (a,))}
    assert {"system", "rpg-elements", "apocalypse"} <= tags_a
