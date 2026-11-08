"""The tag search language, the new library filters, possible tags, fandoms and the tag family tree."""
import importlib
from datetime import date

import pytest


@pytest.fixture()
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKKEEPER_DATA", str(tmp_path))
    from bookkeeper import config
    importlib.reload(config)
    from bookkeeper import db, library, matching, search, tagquery, tags
    importlib.reload(db); importlib.reload(tags); importlib.reload(matching); importlib.reload(library)
    importlib.reload(tagquery); importlib.reload(search)
    db.init(tmp_path / "test.db")
    return db, tags, library, search


def _book(library, n, labels=(), **kw):
    from bookkeeper.sites.base import BookInfo
    return library.upsert_book("x", BookInfo(sid=str(n), url=f"u{n}", title=f"Book {n}", tags=list(labels), **kw))


def _found(search, **params):
    books = search.search({"per_page": 100, "dedupe": "0", **params})["books"]
    return sorted(int(b["title"].split()[-1]) for b in books)


def test_query_reads_back_in_words(lib):
    _, T, _, _ = lib
    from bookkeeper import tagquery as Q

    def reads(text):
        return Q.explain(Q.parse(text), lambda i: T.info(i)["label"])
    assert reads("romance -harem") == "Romance and not Harem"
    assert reads("romance !harem") == reads("romance NOT harem") == reads("Романтика не Гарем") == "Romance and not Harem"
    assert reads('"не гарем"') == "No harem"            # the site tag of that name, in quotes
    assert reads("гг не ояш") == T.info("not-ojash")["label"]  # a name with НЕ inside still works
    assert reads("romance | harem") == reads("romance OR harem") == reads("romance или harem") == "Romance or Harem"
    assert reads("romance, harem") == reads("romance & harem") == "Romance and Harem"
    assert reads("(isekai | reincarnation) -harem") == "(Another world / Isekai or Reincarnation) and not Harem"
    assert reads("-(romance harem)") == "not (Romance and Harem)"  # not "not Romance and Harem"
    assert reads("romance harem | isekai") == "(Romance and Harem) or Another world / Isekai"
    assert reads("?system") == "possibly System"
    assert reads("-?harem") == "not possibly Harem"
    assert reads("slow burn") == reads('"slow burn"') == "Slow-burn romance"  # known names need no quotes
    assert reads("fandom*") == "any tag starting with “fandom”"
    assert reads("xyzzy") == "“xyzzy” (no such tag yet)"
    assert Q.from_lists(["romance"], ["isekai", "reincarnation"], ["harem", "slow burn"]) == \
        'romance (isekai | reincarnation) -harem -"slow burn"'


def test_tag_search_in_the_library(lib):
    db, T, library, search = lib
    _book(library, 1, ["Романтика", "Попаданцы"])
    _book(library, 2, ["Романтика", "Гарем"])
    _book(library, 3, ["Попаданцы"])
    _book(library, 4, ["Фэнтези"])
    assert _found(search, tq="romance") == [1, 2]
    assert _found(search, tq="Романтика -Гарем") == [1]
    assert _found(search, tq="!romance") == [3, 4]
    assert _found(search, tq="harem | попаданцы") == [1, 2, 3]
    assert _found(search, tq="(harem | isekai) -romance") == [3]
    assert _found(search, tq="xyzzy") == []
    # Searches saved by older versions (three lists) still work.
    assert _found(search, tags="romance", **{"not": "harem"}) == [1]


def test_possible_tags(lib):
    db, T, library, search = lib
    book = _book(library, 4, ["Фэнтези"])
    with db.transaction() as c:
        library._replace_maybe_tags(c, book, [{"tag": "magic", "score": 0.5, "per_10k": 5.0},
                                              {"tag": "fantasy", "score": 0.9, "per_10k": 30.0}])
    _book(library, 5, ["Романтика"])
    assert _found(search, tq="magic") == []         # plain tags count only what's certain
    assert _found(search, tq="?magic") == [4]
    assert _found(search, tq="-?magic") == [5]
    d = search.book_detail(book)
    assert [p["id"] for p in d["possible_tags"]] == ["magic"]  # fantasy is certain already, so not "possible"
    assert "magic" not in [t["id"] for t in d["tags"]]
    library.refresh_tag_counts()
    assert db.conn().execute("SELECT books FROM tags WHERE id='magic'").fetchone()[0] == 0
    _book(library, 4, ["Фэнтези", "Магия"])         # now the site says so too
    assert search.book_detail(book)["possible_tags"] == []


def test_possible_tags_from_the_text():
    from bookkeeper.analysis.themes import detect
    text = "Он открыл статус. Система выдала уведомление: уровень повышен, навык получен. " * 40 + \
        "Обычные слова и ничего больше. " * 150
    found = {f["tag"]: f for f in detect([text])}
    assert "system" in found and 0 < found["system"]["score"] <= 1
    assert "dragons" not in found
    assert detect(["слишком коротко"]) == []


def test_fandoms_orientation_age_and_staleness(lib):
    db, T, library, search = lib
    assert T.canonical("fandom:Naruto") == ["fandom-naruto"]
    assert T.canonical("fandom:Совсем Новый Фандом") == ["fandom:совсем новый фандом"]
    _book(library, 5, ["fandom:Naruto", "Слэш"], age_rating="PG-13", updated_at="2020-01-01")
    _book(library, 6, ["fandom:Совсем Новый Фандом"], age_rating="16+", updated_at=date.today().isoformat())
    _book(library, 7, ["Романтика"], adult=True)
    _book(library, 8, ["Романтика"])
    assert _found(search, fq="naruto") == [5]
    assert _found(search, fq="Совсем новый фандом") == [6]
    assert _found(search, fq="-naruto", kind="fanfic") == [6]
    assert _found(search, tq="Naruto") == [5]       # a fandom's name works in the Tags field too
    assert _found(search, kind="fanfic") == [5, 6] and _found(search, kind="original") == [7, 8]
    assert _found(search, orient="slash") == [5]
    assert _found(search, age="PG-13") == [5]
    assert _found(search, age="R") == [6]          # 16+
    assert _found(search, age="NC-17") == [7]      # marked 18+ without a rating
    assert _found(search, age="unknown") == [8]
    assert _found(search, stale="365") == [5]      # books with no date are left out
    assert _found(search, updated_within="7") == [6]
    assert library.normalize_age("18+") == "NC-17" and library.normalize_age("NC-21") == "NC-21"
    assert library.normalize_age("Нет") is None


def test_tag_family_and_tag_page(lib):
    db, T, library, search = lib
    tree = T.child_tree("fantasy")
    cultivation = next(n for n in tree if n["id"] == "cultivation")
    assert "xianxia" in [n["id"] for n in cultivation["children"]]   # 2.1) under 2), not beside it
    assert "xianxia" not in [n["id"] for n in tree]
    assert T.direct_parents("xianxia") == ["cultivation"]
    assert "harem" in T.anti("no-harem") and "no-harem" in T.anti("harem")
    assert "магический детектив" not in T.aliases("fantasy")         # it means Fantasy + Mystery
    assert "магический детектив" in [label for label, _ in T.combined("fantasy")]
    for n in range(10):
        _book(library, 100 + n, ["Гарем", "Комедия"])
        _book(library, 200 + n, ["Детектив"])
    library.refresh_tag_counts()
    page = search.tag_page("harem")
    assert page["books"] == 10
    assert "comedy" in [x["id"] for x in page["related"]]
    assert "no-harem" in [x["id"] for x in page["anti"]]
    brief = search.tag_brief("fandom:совсем новый фандом")
    assert brief["category"] == "fandom"


def test_autocomplete(lib):
    _, T, _, search = lib
    harem = next(o for o in search.complete("romance ha", "en") if o["id"] == "harem")
    assert harem["replace_words"] == 1                    # keeps the Romance already typed
    slow = search.complete("slow bu", "en")[0]
    assert slow["id"] == "slow-burn" and slow["replace_words"] == 2
    assert search.complete("попад", "ru")[0]["insert"] == "Попаданцы"
    assert search.complete("попад", "en")[0]["insert"] == "isekai"
    ojash = search.complete("гг не оя", "ru")[0]
    assert ojash["id"] == "not-ojash" and ojash["replace_words"] == 3
    assert search.complete("нару", "ru", fandom=True)[0]["id"] == "fandom-naruto"
    for o in search.complete("male le", "uk") + search.complete("сло", "ru") + search.complete("fan", "en"):
        assert search.resolve_tag(o["insert"].strip('"')) == [o["id"]]  # what goes in reads back as that tag
