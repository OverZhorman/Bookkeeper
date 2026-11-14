"""Housekeeping: emptying the write-ahead log, and telling lock errors apart."""
import importlib
import sqlite3

import pytest


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKKEEPER_DATA", str(tmp_path))
    from bookkeeper import config, db
    importlib.reload(config)
    importlib.reload(db)
    db.init(tmp_path / "test.db")
    return db, tmp_path / "test.db"


def test_checkpoint_empties_the_write_ahead_log(fresh_db):
    db, path = fresh_db
    c = db.conn()
    assert c.execute("PRAGMA journal_size_limit").fetchone()[0] == db.WAL_LIMIT
    with db.transaction() as tc:
        tc.executemany("INSERT INTO meta(key, value) VALUES(?, ?)", [(f"k{i}", "x" * 500) for i in range(2000)])
    wal = path.with_name(path.name + "-wal")
    assert wal.stat().st_size > 0
    assert db.checkpoint() is True
    assert wal.stat().st_size == 0
    assert c.execute("SELECT COUNT(*) FROM meta WHERE key LIKE 'k%'").fetchone()[0] == 2000


def test_lock_errors_are_told_apart():
    from bookkeeper.crawler import _library_busy
    assert _library_busy(sqlite3.OperationalError("database is locked"))
    assert not _library_busy(sqlite3.OperationalError("no such column: x"))
    assert not _library_busy(ValueError("database is locked"))



def test_a_site_keeps_going_when_the_library_is_busy():
    import threading
    import types
    from bookkeeper import crawler
    w = crawler.SiteWorker.__new__(crawler.SiteWorker)  # just the main loop, no site behind it
    w.site_id, w.browser, w.gen, w.activity = "x", None, None, ""
    w.stop, w.manager = threading.Event(), types.SimpleNamespace(shutdown=threading.Event())
    w._setup = lambda: None
    cycles, pauses = [], []

    def cycle():
        cycles.append(1)
        if len(cycles) == 1:
            raise sqlite3.OperationalError("database is locked")  # a save had to wait too long
        if len(cycles) == 2:
            raise ValueError("a site problem")  # ...and noting this one fails too
        w.stop.set()
        return True

    def status(*a):
        raise sqlite3.OperationalError("database is locked")
    w.cycle, w._status, w._idle = cycle, status, pauses.append
    w.run()
    assert len(cycles) == 3 and pauses == [60, 60]  # a minute's pause each time, and the site carries on
