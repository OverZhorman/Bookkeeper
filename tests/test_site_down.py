"""A site that is down or overloaded (AO3's HTTP 503/525): Bookkeeper waits instead of failing, and keeps going with
what still works."""
import importlib
import time

import httpx
import pytest


def http_error(status: int) -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError(f"HTTP {status} for https://example.org/x", request=None, response=None)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKKEEPER_DATA", str(tmp_path / "data"))
    from bookkeeper import config
    importlib.reload(config)
    from bookkeeper import db, library
    importlib.reload(db); importlib.reload(library)
    db.init(tmp_path / "test.db")
    return tmp_path


def test_what_counts_as_the_site_being_down():
    from bookkeeper.crawler import backoff, unavailable
    from bookkeeper.sites.base import TemporaryError
    assert unavailable(http_error(525)) == "HTTP 525" and unavailable(http_error(503)) == "HTTP 503"
    assert unavailable(http_error(404)) is None and unavailable(ValueError("x")) is None
    try:
        try:
            raise http_error(502)
        except httpx.HTTPStatusError as e:
            raise TemporaryError("AO3 is overloaded") from e  # how AO3's connector reports it
    except TemporaryError as wrapped:
        assert unavailable(wrapped) == "HTTP 502"
    assert unavailable(httpx.ReadTimeout("slow")) == "no answer: ReadTimeout"
    assert unavailable(TemporaryError("a slow chapter")) is None
    assert [backoff(n) for n in (1, 2, 3, 4, 5, 9)] == [300, 600, 1200, 2400, 3600, 3600]


def make_worker(monkeypatch, site_cls):
    from bookkeeper import crawler, db
    monkeypatch.setitem(crawler.SITES, site_cls.id, site_cls)
    db.conn().execute("INSERT INTO sites(id, enabled, updated_at) VALUES(?, 1, 'x')", (site_cls.id,))
    manager = type("M", (), {"dirty": set(), "shutdown": None})()
    w = crawler.SiteWorker(manager, site_cls.id)
    w.site, w.state = site_cls(None, crawler.site_settings(site_cls.id)), {}
    return w


def add_book(sid):
    from bookkeeper import library
    from bookkeeper.sites.base import BookInfo
    library.upsert_book("downsite", BookInfo(sid=sid, url=f"u{sid}", title=f"Book {sid}", pop_raw=100 - int(sid),
                                             complete=True))


WORDS = "I opened the door and I saw the sea. " * 200


def test_lists_failing_dont_stop_the_text_checks(env, monkeypatch):
    from bookkeeper import db
    from bookkeeper.sites.base import Site

    class DownLists(Site):
        id = "downsite"
        name = "Down Site"

        def discover(self, state):
            raise http_error(525)
            yield []

        def details(self, book):
            raise NotImplementedError

        def opening_text(self, book, max_chapters=3, enough_words=6000):
            return [WORDS]

    add_book("1")
    w = make_worker(monkeypatch, DownLists)
    assert w.cycle() is True  # the narration check still ran
    assert w.listing_wait_until > time.time() + 250 and w.listing_failures == 1
    row = db.conn().execute("SELECT status, status_msg FROM sites WHERE id='downsite'").fetchone()
    assert row["status"] == "running" and "lists aren't loading" in row["status_msg"]
    assert db.conn().execute("SELECT pov FROM books WHERE sid='1'").fetchone()["pov"] == "first"


def test_site_down_stops_after_one_book_and_keeps_its_tries(env, monkeypatch):
    from bookkeeper import db
    from bookkeeper.sites.base import Site

    class AllDown(Site):
        id = "downsite"
        name = "Down Site"
        calls = 0

        def discover(self, state):
            return iter(())

        def details(self, book):
            raise NotImplementedError

        def opening_text(self, book, max_chapters=3, enough_words=6000):
            type(self).calls += 1
            raise http_error(503)

    for sid in ("1", "2", "3"):
        add_book(sid)
    w = make_worker(monkeypatch, AllDown)
    with pytest.raises(httpx.HTTPStatusError):
        w.cycle()  # run() then waits 5, 10, 20... minutes
    assert AllDown.calls == 1  # not every book in turn
    errors = db.conn().execute("SELECT b.sid, a.error FROM analysis a JOIN books b ON b.id=a.book_id").fetchall()
    assert [(r["sid"], r["error"][:10]) for r in errors] == [("1", "temporary:")]  # tried again later
