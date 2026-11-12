"""Flibusta's whole-catalog listing (catalog file, genre pages, book pages) and Wuxia.click's end of listing."""
import importlib
import io
import zipfile

import pytest


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKKEEPER_DATA", str(tmp_path))
    from bookkeeper import config
    importlib.reload(config)
    from bookkeeper import db, library, matching, tags
    for m in (db, tags, matching, library):
        importlib.reload(m)
    db.init(tmp_path / "test.db")
    return db, library


class Page:
    def __init__(self, url, content):
        self.url, self.status, self.headers = url, 200, {}
        self.content = content if isinstance(content, bytes) else content.encode("utf-8")
        self.text = self.content.decode("utf-8", "replace")


class FakeHttp:
    """Answers by the path and query of the URL; a value that's an exception is raised."""
    def __init__(self, pages):
        self.pages, self.asked = pages, []

    def get(self, url, params=None, **kw):
        path = url.split("://", 1)[-1].split("/", 1)[-1]
        if params:
            path += "?" + "&".join(f"{k}={v}" for k, v in params.items())
        self.asked.append(path)
        answer = self.pages.get(path)
        if isinstance(answer, Exception):
            raise answer
        if answer is None:
            raise AssertionError(f"unexpected request {path}")
        return Page(url, answer)


def _catalog_zip() -> bytes:
    lines = ["Last Name;First Name;Middle Name;Title;Subtitle;Language;Year;Series;ID",
             "Александрова;Наталья;Николаевна;Машина чудес;;ru;2026;Роковой артефакт;894809",
             "Smith;John;;Title; with a semicolon;;en;2001;;100",
             "Иванов;Иван;;Машина чудес;;ru;2026;Роковой артефакт;894809",
             "Петров;Петр;;Книга;;bg;1999;;200",
             "a broken line"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("catalog.txt", "﻿" + "\n".join(lines) + "\n")
    return buf.getvalue()


GENRES = '<a href="/g/det_artifact">Артефакт-детективы</a> (det_artifact) - 2<br>'
GENRE_PAGE = ('<ol><h4>04.11.2026</h4> <h5><a href="/a/29686">Наталья Николаевна Александрова</a></h5>'
              '<a href="/b/894809">Машина чудес</a><br><a href="/b/7">Not listed here</a><br></ol>'
              '<div class="block"><a href="/a/1">Reader</a>: <a href="/b/555">A reviewed book</a></div>')
EMPTY_FEED = '<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
BOOK_PAGE = """<h1 class="title">Машина чудес (fb2)</h1>
<a href="/a/29686">Наталья Николаевна Александрова</a> &nbsp;
<p class="genre"><a href="/g/290" class="genre" name="det_artifact">Артефакт-детективы</a></p><p class="genre"><a href="/g/24" class="genre" name="detective">Детективы</a></p>
Машина чудес <span style=size>1540K, 208 с.</span>
 &nbsp; издание 2026 г.
 &nbsp; издано в серии <a href="/s/61909">Артефакт-детектив. Наталья Александрова</a>
<br>Добавлена: 04.11.2026
<h2>Аннотация</h2>
<p>В XIII веке средневековый испанский учёный изобрёл машину.</p>
</div><div id="sidebar-right" class="sidebar"><a href="/b/1">Other</a></div></body>"""


def test_flibusta_lists_the_whole_catalog_then_adds_genres(env):
    db, library = env
    from bookkeeper.sites.flibusta import Flibusta
    http = FakeHttp({"catalog/catalog.zip": _catalog_zip(), "g/": GENRES, "g/det_artifact": GENRE_PAGE,
                     "opds/new/0/new": EMPTY_FEED})
    site = Flibusta(http, {"languages": "ru, en"})
    state: dict = {}
    batches = list(site.discover(state))
    listed = batches[0]
    assert [(b.sid, b.title, b.lang) for b in listed] == [("100", "Title; with a semicolon", "en"),
                                                         ("894809", "Машина чудес", "ru")]  # no Bulgarian book
    assert listed[1].authors == ["Наталья Николаевна Александрова", "Иван Иванов"]
    assert listed[1].extra == {"series": "Роковой артефакт", "year": "2026"} and listed[1].tags is None
    genre_batch = batches[1]
    assert [(b.sid, b.tags, b.add_tags) for b in genre_batch] == [("894809", ["Артефакт-детективы"], True),
                                                                  ("7", ["Артефакт-детективы"], True)]
    assert state["phase"] == "updates" and state["full_done"] and state["cat_max"] == 894809
    assert state["cat_langs"] == ["en", "ru"]

    for batch in batches:
        for info in batch:
            library.upsert_book("flibusta", info)
    c = db.conn()
    assert c.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 2     # book 7 isn't listed: not added
    bid = c.execute("SELECT id FROM books WHERE sid='894809'").fetchone()[0]
    assert library._site_labels(c, bid) == ["Артефакт-детективы"]
    assert c.execute("SELECT meta_at FROM books WHERE id=?", (bid,)).fetchone()[0] is None  # details still to read

    # the next pass reads only the week's new arrivals
    assert list(site.discover(state)) == [] and http.asked[-1] == "opds/new/0/new"


def test_flibusta_genre_pages_that_fail_or_come_back_empty(env):
    from bookkeeper.sites.base import TemporaryError
    from bookkeeper.sites.flibusta import Flibusta

    def page(n, pager=""):
        return f'<ol><a href="/b/{n}">Book {n}</a><br></ol>{pager}'
    pager = '<a href="/g/sf?page=1">2</a> <a href="/g/sf?page=3">4</a>'
    http = FakeHttp({"g/sf": page(1, pager), "g/sf?page=1": "<div>no list today</div>",
                     "g/sf?page=2": TemporaryError("502 Bad Gateway"), "g/sf?page=3": page(4, pager)})
    site = Flibusta(http, {})
    state = {"genres": [["sf", "Фантастика", 120]], "gi": 0, "gpage": 0, "glast": None}
    gen = site._genres(state)
    first = next(gen)                                   # pages 0 and 1 (empty) are kept before the failure…
    assert [b.sid for b in first] == ["1"]
    with pytest.raises(TemporaryError):
        next(gen)
    assert state["gpage"] == 2 and state["gi"] == 0     # …and the failed page is next when it's tried again
    http.pages["g/sf?page=2"] = page(3, pager)
    rest = [b.sid for batch in site._genres(state) for b in batch]
    assert rest == ["3", "4"] and state["gi"] == 1      # page 3 is the last one the pager links to


def test_flibusta_book_page(env):
    from bookkeeper.sites.flibusta import Flibusta
    site = Flibusta(FakeHttp({"b/894809": BOOK_PAGE}), {})
    info = site.details({"sid": "894809"})
    assert (info.title, info.authors, info.words, info.updated_at) == \
        ("Машина чудес", ["Наталья Николаевна Александрова"], 1540 * 58, "2026-11-04")
    assert info.tags == ["Артефакт-детективы", "Детективы"] and info.description.startswith("В XIII веке")
    assert info.extra == {"series": "Артефакт-детектив. Наталья Александрова", "year": "2026", "format": "fb2"}


def test_wuxiaclick_end_of_listing(env):
    from bookkeeper.http import NotFound
    from bookkeeper.sites.wuxiaclick import WuxiaClick
    gone = NotFound("https://wuxia.click/browse")
    site = WuxiaClick(FakeHttp({"browse?order_by=new&page=641": gone, "browse?order_by=new&page=300": gone}), {})
    state = {"page": 641}
    assert list(site.discover(state)) == [] and state["full_done"]   # past the end: the listing is done
    state = {"page": 300, "pages": 641}
    with pytest.raises(NotFound):                                      # inside the listing: a hiccup
        list(site.discover(state))
    assert not state.get("full_done")
