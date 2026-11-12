"""Fixing labels with an AI chat: export a prompt, check and apply its reply, undo the whole import."""
import importlib
import json

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
    return db, tags, library, labels


def _book(library, n, labels_):
    from bookkeeper.sites.base import BookInfo
    return library.upsert_book("x", BookInfo(sid=str(n), url=f"u{n}", title=f"Book {n}", tags=list(labels_)))


def _tags(db, book_id):
    return {r[0] for r in db.conn().execute("SELECT tag FROM book_tags WHERE book_id=? AND source='site'", (book_id,))}


REPLY = """Sure! Here are the answers:
```json
{"new_tag": {"id": "complicated-relationships", "en": "Complicated relationships", "ru": "Сложные отношения", "category": "relationship"}}
{"label": "саске", "tags": ["fandom-naruto"]}
{"label": "Wattpad", "hide": true}
{"label": "сложные отношения", "tags": ["complicated-relationships", "Romance"]}
{"label": "непонятное слово", "keep": true}
{"label": "Фэнтези", "hide": true}
{"label": "выдумка", "tags": ["isekai"]}
{"label": "саске", "tags": ["no-such-tag"]}
```
Let me know if you need anything else."""


def test_export_import_and_undo(lib):
    db, T, library, labels = lib
    a = _book(library, 1, ["саске", "Наруто"])
    b = _book(library, 2, ["саске"])
    c = _book(library, 3, ["wattpad", "Романтика"])
    d = _book(library, 4, ["Сложные отношения", "Романтика"])
    _book(library, 5, ["непонятное слово", "Фэнтези"])
    library.refresh_tag_counts()

    out = labels.export_for_ai(limit=10)
    assert out["count"] == 4 and out["total"] == 4
    assert "fandom-naruto | Naruto" in out["text"] and "romance | Romance" in out["text"]
    sent = [json.loads(line) for line in out["text"].split("\nSITE LABELS (")[1].splitlines()[1:] if line.strip()]
    assert sent[0] == {"label": "саске", "books": 2, "often_with": ["fandom-naruto"], "examples": ["Book 1", "Book 2"]}
    assert labels.export_for_ai(limit=1)["count"] == 1

    preview = labels.check_import(REPLY)
    by = {i["label"]: i for i in preview["items"]}
    assert by["саске"]["ids"] == ["fandom-naruto"] and not by["саске"]["problem"]  # the 2nd answer is ignored
    assert by["Wattpad"]["action"] == "hide"
    assert by["сложные отношения"]["ids"] == ["complicated-relationships", "romance"]  # a name works as well
    assert by["Фэнтези"]["problem"]          # a shared tag's own name: an import never touches it
    assert by["выдумка"]["problem"]          # not a label in this library
    assert preview["counts"] == {"tags": 2, "hide": 1, "keep": 1, "problems": 2, "new_tags": 1}

    result = labels.apply_import(REPLY)
    assert result["labels"] == 4 and result["new_tags"] == 1
    assert _tags(db, b) == {"fandom-naruto"} and _tags(db, a) == {"fandom-naruto"}
    assert _tags(db, c) == {"romance"}                       # wattpad hidden
    assert _tags(db, d) == {"complicated-relationships", "romance"} and T.is_known("complicated-relationships")
    assert labels.unrecognized()["total"] == 0               # "keep" took its label off the list as well
    assert labels.imports()[0]["count"] == 4

    labels.undo_import(result["import"])
    assert _tags(db, b) == {"саске", "fandom-naruto"}       # Bookkeeper's own reading of «саске» again
    assert _tags(db, c) == {"wattpad", "romance"}
    assert not T.is_known("complicated-relationships") and "сложные отношения" in _tags(db, d)
    assert labels.unrecognized()["total"] == 4 and T.fixes() == {}
    with pytest.raises(ValueError):
        labels.undo_import(result["import"])


def test_replies_in_other_shapes(lib):
    db, T, library, labels = lib
    _book(library, 1, ["саске", "wattpad"])
    library.refresh_tag_counts()
    pretty = '[\n  {\n    "label": "саске",\n    "tags": "fandom-naruto"\n  },\n  {"label": "wattpad", "hide": true}\n]'
    assert [i["action"] for i in labels.check_import(pretty)["items"]] == ["tags", "hide"]
    only = labels.apply_import(pretty, keys={T.key("wattpad")})   # just the ticked answer
    assert only["labels"] == 1 and list(T.fixes()) == ["wattpad"]
    with pytest.raises(ValueError):
        labels.check_import("Sorry, I can't help with that.")
