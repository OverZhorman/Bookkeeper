"""Hardcover's API (answers shaped as the API gives them, made-up books) and the encrypted token setting."""
import importlib
import json

import pytest

from bookkeeper.http import Blocked
from bookkeeper.sites.base import SiteError
from bookkeeper.sites.hardcover import API, PER_PAGE, Hardcover, book_info


def raw_book(i, **kw):
    b = {"id": i, "title": f"Book {i}", "subtitle": None, "slug": f"book-{i}", "release_date": "2021-03-04",
         "description": "I log in and the System greets me. Then the dungeon opens and I level up.", "pages": 412,
         "rating": 4.25, "ratings_count": 812, "users_count": 5000 - i, "users_read_count": 3001,
         "book_category_id": 9, "alternative_titles": [],
         "cached_tags": {"Genre": [{"tag": "Fantasy", "tagSlug": "fantasy", "category": "Genre", "count": 90}],
                         "Mood": [{"tag": "adventurous", "count": 40}],
                         "Content Warning": [{"tag": "Death", "count": 3}],
                         "Tag": [{"tag": "LitRPG", "count": 77}, {"tag": "Twist ending", "count": 5, "spoilerRatio": 0.8}]},
         "cached_contributors": [{"author": {"name": "Ann  Writer", "slug": "ann"}, "contribution": None},
                                 {"author": {"name": "Tom Trans"}, "contribution": "Translator"}],
         "cached_image": {"url": "https://assets.hardcover.app/b.jpg", "width": 400}}
    b.update(kw)
    return b


class FakeApi:
    def __init__(self, pages, status=200):
        self.pages, self.calls, self.status = pages, [], status

    def post(self, url, json_body=None, headers=None, ok_status=(), **kw):
        assert url == API
        self.calls.append((json_body, headers))
        if self.status == 401:
            raise Blocked("access denied (HTTP 401)")
        v = json_body["variables"]
        if "names" in v:
            data = {"tags": [{"id": 11, "tag": "LitRPG"}, {"id": 12, "tag": "LitRPG"}]}
        else:
            where = json.dumps(v["where"], sort_keys=True)
            data = {"books": self.pages.get((where, v["offset"], next(iter(v["order"][0]))), [])}
        body = json.dumps({"data": data})
        return type("P", (), {"status": 200, "json": lambda self: json.loads(body)})()


def test_hardcover_book_from_the_api():
    b = book_info(raw_book(7))
    assert (b.sid, b.url, b.title, b.authors) == ("7", "https://hardcover.app/books/book-7", "Book 7", ["Ann Writer"])
    assert b.is_translation and b.lang == "en" and b.cover == "https://assets.hardcover.app/b.jpg"
    assert b.rating == 8.5 and b.votes == 812 and b.pop_raw == 4993 and b.likes == 3001
    assert b.created_at == "2021-03-04" and b.complete and b.extra["pages"] == 412
    assert b.tags == ["Web Novel", "Fantasy", "LitRPG", "adventurous", "Death"]  # the spoiler tag is left out
    flat = book_info(raw_book(8, cached_tags=[{"tag": "Isekai"}, "Harem"], book_category_id=1, slug=None))
    assert flat.tags == ["Isekai", "Harem"] and flat.url == "https://hardcover.app/books/8"


def test_hardcover_reads_categories_and_tags_with_the_token():
    base = {"book_status_id": {"_eq": 1}, "canonical_id": {"_is_null": True}}
    web = json.dumps({**base, "book_category_id": {"_eq": 9}}, sort_keys=True)
    lit = json.dumps({**base, "taggings": {"tag_id": {"_in": [11, 12]}}}, sort_keys=True)
    api = FakeApi({
        (web, 0, "users_count"): [raw_book(i) for i in range(1, PER_PAGE + 1)],
        (web, PER_PAGE, "users_count"): [raw_book(500)],
        (lit, 0, "users_count"): [raw_book(1)],
        (web, 0, "created_at"): [raw_book(900)],
        (lit, 0, "created_at"): [raw_book(901)],
    })
    site = Hardcover(api, {"token": "abc", "categories": "Web Novel, Nonsense", "tags": "LitRPG, Unknown Tag"})
    state = {}
    assert [len(batch) for batch in site.discover(state)] == [PER_PAGE, 1, 1]
    assert state == {"full_done": True, "li": 0, "page": 1}
    body, headers = api.calls[1]
    assert headers["Authorization"] == "Bearer abc" and headers["User-Agent"].startswith("Bookkeeper/")
    assert body["variables"]["offset"] == 0 and "cached_tags" in body["query"]
    assert [[b.sid for b in batch] for batch in site.discover(state)] == [["900"], ["901"]]  # later: newest


def test_hardcover_explains_a_missing_or_refused_token():
    with pytest.raises(SiteError, match="token"):
        list(Hardcover(FakeApi({}), {"token": ""}).discover({}))
    with pytest.raises(SiteError, match="didn't accept"):
        list(Hardcover(FakeApi({}, status=401), {"token": "old"}).discover({}))


def test_secret_settings_stay_out_of_the_library(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKKEEPER_DATA", str(tmp_path / "data"))
    from bookkeeper import config
    importlib.reload(config)
    from bookkeeper import accounts, crawler, db
    importlib.reload(db)
    db.init(tmp_path / "test.db")
    db.conn().execute("INSERT INTO sites(id, enabled, updated_at) VALUES('hardcover', 0, 'x')")
    manager = crawler.Manager.__new__(crawler.Manager)
    manager.workers = {}
    manager.poke = lambda site_id: None
    manager.update_settings("hardcover", {"token": "  secret-123 ", "tags": "LitRPG"})
    stored = db.conn().execute("SELECT settings FROM sites WHERE id='hardcover'").fetchone()["settings"]
    assert "secret-123" not in stored and "LitRPG" in stored
    assert b"secret-123" not in (config.DATA_DIR / "accounts" / "hardcover.token.secret").read_bytes()  # encrypted
    assert crawler.site_settings("hardcover")["token"] == "secret-123"
    assert crawler.site_settings("hardcover", secrets=False)["token"] == ""
    manager.update_settings("hardcover", {"token": ""})
    assert accounts.secret_setting("hardcover", "token") == ""
