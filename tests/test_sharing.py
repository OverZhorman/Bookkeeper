"""Sharing a library: the copy leaves out everything personal, and a friend's Bookkeeper takes it in."""
import importlib
import json
import sqlite3
import time
import zipfile
from pathlib import Path

import pytest

TOKEN = "tok-0123456789abcdefghijklmnop"


@pytest.fixture()
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKKEEPER_DATA", str(tmp_path / "mine"))
    from bookkeeper import config
    importlib.reload(config)
    from bookkeeper import db, library, matching, sharing, tags
    for m in (db, tags, matching, library, sharing):
        importlib.reload(m)
    config.ensure_dirs()
    db.init()
    return config, db, library, sharing


def _close(db):
    """Let go of the library, as a Bookkeeper that isn't running yet would."""
    c = getattr(db._local, "conn", None)
    if c is not None:
        c.close()
    db._local.__dict__.clear()
    db._initialized_path = None


def _my_library(config, db, library) -> tuple[int, int]:
    from bookkeeper.sites.base import BookInfo
    a = library.upsert_book("ficbook", BookInfo(sid="1", url="u1", title="Книга", tags=["ЛитРПГ"]))
    b = library.upsert_book("litnet", BookInfo(sid="2", url="u2", title="Book", tags=["Romance"]))
    c = db.conn()
    db.set_setting("ai_web_token", TOKEN)
    db.set_setting("account:ranobelib", {"user": "Someone", "at": "2026-11-20T10:00:00Z"})
    db.set_setting("hide_adult", True)
    db.set_setting("label_imports", [{"id": "1", "labels": {"x": ["y"]}}])
    db.set_setting("tags_version", 5)
    c.execute("INSERT INTO user_books(book_id, shelf, favorite, pov, note) VALUES(?, 'read', 1, NULL, 'my note')", (a,))
    c.execute("INSERT INTO user_books(book_id, shelf, favorite, pov, note) VALUES(?, 'want', 0, 'first', 'other note')",
              (b,))
    c.execute("INSERT INTO saved_searches(name, query) VALUES('mine', 'tags=litrpg')")
    c.execute("INSERT INTO downloads(book_id, fmt, state, file) VALUES(?, 'epub', 'done', 'C:/x.epub')", (a,))
    c.execute("INSERT INTO sites(id, enabled, settings, status, status_msg) VALUES('ranobelib', 1, ?, 'running', ?)",
              (json.dumps({"include_adult": True, "api_token": "site-secret"}), "logged in as Someone"))
    config.USER_TAGS_FILE.write_text('[rules]\n"harem" = ["romance"]\n', encoding="utf-8")
    return a, b


def test_the_copy_leaves_out_everything_personal(lib, tmp_path):
    config, db, library, sharing = lib
    _, b = _my_library(config, db, library)
    stages = []
    res = sharing.make_copy(tmp_path / "out", progress=lambda stage, done=0, total=0: stages.append(stage))
    assert res["books"] == 2 and stages[:2] == ["copy", "clean"] and stages[-1] == "pack"
    assert Path(res["file"]).name.startswith("Bookkeeper library ") and res["size"] == Path(res["file"]).stat().st_size
    with zipfile.ZipFile(res["file"]) as z:
        assert set(z.namelist()) == {"bookkeeper-library.json", "library.db", "my_tags.toml"}
        manifest = json.loads(z.read("bookkeeper-library.json"))
        raw = z.read("library.db")
        assert z.read("my_tags.toml").startswith(b"[rules]")
    assert manifest["format"] == 1 and manifest["books"] == 2 and manifest["sites"] == {"ficbook": 1, "litnet": 1}
    for private in (TOKEN, "Someone", "my note", "other note", "site-secret", "C:/x.epub"):
        assert private.encode() not in raw, private  # deleted, and overwritten rather than just let go
    (tmp_path / "copy.db").write_bytes(raw)
    s = sqlite3.connect(tmp_path / "copy.db")
    assert {r[0] for r in s.execute("SELECT key FROM meta")} == {"schema_version", "setting:tags_version"}
    assert s.execute("SELECT book_id, shelf, favorite, pov, note FROM user_books").fetchall() == [(b, None, 0, "first", None)]
    assert [s.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("saved_searches", "downloads", "queue")] == [0] * 3
    assert s.execute("SELECT enabled, settings, status, status_msg FROM sites").fetchall() == [(0, "{}", "idle", None)]
    assert s.execute("SELECT COUNT(*) FROM book_tags").fetchone()[0] >= 2
    assert s.execute("SELECT title FROM books_fts WHERE books_fts MATCH 'Книга'").fetchall() == [("Книга",)]
    assert s.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    assert not (config.DATA_DIR / sharing.WORK).exists()
    # the library itself is untouched
    assert db.get_setting("ai_web_token") == TOKEN and db.conn().execute("SELECT COUNT(*) FROM saved_searches").fetchone()[0] == 1


def test_a_friend_takes_in_the_copy(lib, tmp_path, monkeypatch):
    config, db, library, sharing = lib
    _my_library(config, db, library)
    copy = Path(sharing.make_copy(tmp_path / "out")["file"])
    _close(db)
    # The friend's computer: a library of their own, and tag rules of their own
    monkeypatch.setenv("BOOKKEEPER_DATA", str(tmp_path / "friend"))
    importlib.reload(config)
    config.ensure_dirs()
    db.init()
    from bookkeeper.sites.base import BookInfo
    library.upsert_book("litnet", BookInfo(sid="9", url="u9", title="Friend's book"))
    config.USER_TAGS_FILE.write_text('[rules]\n"dragons" = ["fantasy"]\n', encoding="utf-8")
    _close(db)
    lines = []
    res = sharing.take_in(copy, report=lines.append)
    assert res["books"] == 2 and res["sites"] == 2 and lines and "Unpacking 2 books" in lines[0]
    kept = Path(res["kept"])
    assert kept.parent == config.DATA_DIR and kept.name.startswith("library-before-import-")
    assert sqlite3.connect(kept).execute("SELECT title FROM books").fetchall() == [("Friend's book",)]
    assert '"harem"' in config.USER_TAGS_FILE.read_text(encoding="utf-8")
    assert '"dragons"' in Path(res["kept_tags"]).read_text(encoding="utf-8")
    assert not list(config.DATA_DIR.glob("library.db.importing*"))
    db.init()  # and Bookkeeper opens it as usual
    titles = {r[0] for r in db.conn().execute("SELECT title FROM books")}
    assert titles == {"Книга", "Book"}
    _close(db)


def test_an_empty_library_is_replaced_and_the_bare_db_works(lib, tmp_path, monkeypatch):
    config, db, library, sharing = lib
    _my_library(config, db, library)
    copy = Path(sharing.make_copy(tmp_path / "out")["file"])
    _close(db)
    unpacked = tmp_path / "unpacked"
    with zipfile.ZipFile(copy) as z:
        z.extractall(unpacked)  # what Windows does when the friend opens the .zip and copies its files out
    monkeypatch.setenv("BOOKKEEPER_DATA", str(tmp_path / "friend"))
    importlib.reload(config)
    config.ensure_dirs()
    db.init()  # started once already: an empty library
    _close(db)
    res = sharing.take_in(unpacked / "library.db")
    assert res["books"] == 2 and res["kept"] is None and res["kept_tags"] is None
    assert not list(config.DATA_DIR.glob("library-before-import-*"))
    assert '"harem"' in config.USER_TAGS_FILE.read_text(encoding="utf-8")


def test_take_in_refuses_what_isnt_a_shared_library(lib, tmp_path):
    config, db, library, sharing = lib
    with pytest.raises(sharing.ShareError, match="Can't find"):
        sharing.take_in(tmp_path / "missing.zip")
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    with pytest.raises(sharing.ShareError, match="isn't a library"):
        sharing.take_in(tmp_path / "notes.txt")
    with zipfile.ZipFile(tmp_path / "photos.zip", "w") as z:
        z.writestr("a.jpg", b"not really")
    with pytest.raises(sharing.ShareError, match="isn't a library"):
        sharing.take_in(tmp_path / "photos.zip")
    with zipfile.ZipFile(tmp_path / "newer.zip", "w") as z:
        z.writestr("bookkeeper-library.json", json.dumps({"format": 99, "version": "9.0"}))
        z.writestr("library.db", b"SQLite format 3\0")
    with pytest.raises(sharing.ShareError, match="newer Bookkeeper"):
        sharing.take_in(tmp_path / "newer.zip")
    assert config.DB_PATH.exists() and not list(config.DATA_DIR.glob("library*import*"))


def test_the_downloads_page_button_runs_in_the_background(lib, tmp_path, monkeypatch):
    config, db, library, sharing = lib
    _my_library(config, db, library)
    monkeypatch.setattr(sharing, "default_folder", lambda: tmp_path / "Downloads")
    assert sharing.status()["state"] == "idle"
    assert sharing.start()["state"] == "running"
    for _ in range(300):
        st = sharing.status()
        if st["state"] != "running":
            break
        time.sleep(0.1)
    assert st["state"] == "done" and st["books"] == 2, st
    assert Path(st["file"]).parent == tmp_path / "Downloads"
