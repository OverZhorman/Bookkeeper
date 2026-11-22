"""Running the AI requests by itself: batch after batch, applied without asking, and a whole run undone at once.
The Gemini API is replaced by a fake that answers from the request it gets."""
import importlib
import json

import pytest


@pytest.fixture()
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKKEEPER_DATA", str(tmp_path))
    from bookkeeper import config
    importlib.reload(config)
    from bookkeeper import autoai, db, labels, library, matching, search, tagai, tagedit, tagquery, tags
    for m in (db, tags, matching, library, tagquery, search, labels, tagedit, tagai, autoai):
        importlib.reload(m)
    db.init(tmp_path / "test.db")
    tags.ensure_user_file()
    return db, library, labels, tagai, autoai


def _book(library, n, labels_):
    from bookkeeper.sites.base import BookInfo
    return library.upsert_book("x", BookInfo(sid=str(n), url=f"u{n}", title=f"Book {n}", tags=list(labels_)))


def _sent(prompt: str, header: str) -> list[dict]:
    return [json.loads(line) for line in prompt.split(f"\n{header} (")[1].splitlines()[1:] if line.strip()]


def _answer(text: str) -> dict:
    return {"text": text, "finish": "STOP", "tokens_in": 10, "tokens_out": 5}


def _labels_library(library):
    n = 0
    for label, books in (("саске", 4), ("пропуск", 3), ("wattpad", 2), ("мусор", 1)):
        for _ in range(books):
            n += 1
            _book(library, n, [label])
    library.refresh_tag_counts()


def test_label_run_goes_until_done_and_undoes(lib):
    db, library, labels, tagai, autoai = lib
    _labels_library(library)
    asked = []

    def fake(prompt, model, key, thinking, max_output):
        sent = [x["label"] for x in _sent(prompt, "SITE LABELS")]
        asked.append(sent)
        lines = [json.dumps({"label": x, "tags": ["fandom-naruto"]} if x == "саске" else {"label": x, "hide": True},
                            ensure_ascii=False) for x in sent if x != "пропуск"]  # it never answers «пропуск»
        return _answer("```\n" + "\n".join(lines) + "\n```")

    rec = autoai.new_record("labels", 2, model="fake")
    autoai._loop(rec, "key", fake)
    assert asked == [["саске", "пропуск"], ["пропуск", "wattpad"], ["мусор"]]  # unanswered: one more try, then left
    assert rec["state"] == "done" and len(rec["imports"]) == 3
    assert [b["applied"] for b in rec["batches"]] == [1, 1, 1]
    assert [x["label"] for x in labels.unrecognized()["labels"]] == ["пропуск"]
    assert len(labels.imports()) == 3

    assert autoai.status()["runs"][0]["id"] == rec["id"]
    assert autoai.undo_run(rec["id"]) == {"undone": 3, "missing": 0}
    assert labels.unrecognized()["total"] == 4
    assert autoai._runs()[0]["undone"]


def test_run_stops_when_answers_are_useless(lib):
    db, library, labels, tagai, autoai = lib
    _labels_library(library)
    rec = autoai.new_record("labels", 1, model="fake")
    autoai._loop(rec, "key", lambda *a: _answer("Sorry, I can't help with that."))
    assert rec["state"] == "failed" and len(rec["batches"]) == autoai.EMPTY_IN_A_ROW
    assert "No answers found" in rec["batches"][0]["note"]
    assert labels.unrecognized()["total"] == 4


def test_rate_limit_waits_and_tries_again(lib, monkeypatch):
    db, library, labels, tagai, autoai = lib
    _labels_library(library)
    calls = []

    def fake(prompt, *a):
        calls.append(1)
        if len(calls) == 1:
            raise autoai.ApiError("Gemini API rate limit.", 0.01)
        if len(calls) == 3:
            raise autoai.ApiError("The Gemini API's limit for today is used up.")  # no wait: the run stops
        return _answer("\n".join(json.dumps({"label": x["label"], "hide": True}, ensure_ascii=False)
                                 for x in _sent(prompt, "SITE LABELS")))

    rec = autoai.new_record("labels", 2, model="fake")
    autoai._loop(rec, "key", fake)
    assert len(calls) == 3 and len(rec["batches"]) == 1 and rec["batches"][0]["applied"] == 2
    assert rec["state"] == "failed" and "limit for today" in rec["message"]


def test_max_batches(lib):
    db, library, labels, tagai, autoai = lib
    _labels_library(library)
    rec = autoai.new_record("labels", 1, max_batches=2, model="fake")
    autoai._loop(rec, "key", lambda prompt, *a: _answer("\n".join(
        json.dumps({"label": x["label"], "hide": True}, ensure_ascii=False) for x in _sent(prompt, "SITE LABELS"))))
    assert rec["state"] == "done" and len(rec["batches"]) == 2 and labels.unrecognized()["total"] == 2


def test_tag_run_reviews_every_tag_once(lib):
    db, library, labels, tagai, autoai = lib
    asked = []

    def fake(prompt, *a):
        ids = [x["tag"] for x in _sent(prompt, "TAGS TO IMPROVE")]
        asked.append(ids)
        return _answer("\n".join(json.dumps({"tag": i}) for i in ids))

    rec = autoai.new_record("tags", 600, q="romance", model="fake")
    autoai._loop(rec, "key", fake)
    assert asked and "romance" in asked[0] and rec["state"] == "done"
    assert "romance" in tagai._reviewed()
    assert sum(len(a) for a in asked) == len({i for a in asked for i in a})  # no tag sent twice


def test_key_is_kept_encrypted(lib):
    db, library, labels, tagai, autoai = lib
    with pytest.raises(ValueError):
        autoai.set_key("not a key")
    autoai.set_key("AIzaSyTestTestTestTestTestTestTest123")
    assert autoai.get_key() == "AIzaSyTestTestTestTestTestTestTest123" and autoai.settings()["has_key"]
    if autoai.secret.available():
        assert b"AIzaSy" not in autoai._key_path().read_bytes()
    autoai.set_key("")
    assert not autoai.settings()["has_key"]


def test_zero_free_quota_is_not_called_a_daily_limit(lib):
    import httpx
    db, library, labels, tagai, autoai = lib
    body = {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": (
        "You exceeded your current quota. * Quota exceeded for metric: generate_content_free_tier_input_token_count, "
        "limit: 0, model: gemini-x. Please retry in 11h42m52s."), "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "42172s"}]}}
    e = autoai._error(httpx.Response(429, json=body))
    assert e.wait is None and "can't be used on a free API key" in str(e)


def test_website_run_goes_through_the_browser(lib, monkeypatch):
    db, library, labels, tagai, autoai = lib
    from bookkeeper import geminiweb
    _labels_library(library)
    seen = []

    def fake(prompt, mode, stop, on_step):
        seen.append(mode)
        return _answer("\n".join(json.dumps({"label": x["label"], "hide": True}, ensure_ascii=False)
                                 for x in _sent(prompt, "SITE LABELS")))

    monkeypatch.setattr(geminiweb, "ask", fake)
    monkeypatch.setattr(autoai, "WEB_PAUSE", 0)
    autoai.save_settings(provider="web", web_mode="Neon High")
    rec = autoai.new_record("labels", 2, model="Neon High", provider="web")
    autoai._main(rec, "")
    assert rec["state"] == "done" and seen == ["Neon High", "Neon High"] and labels.unrecognized()["total"] == 0
    assert autoai.settings()["provider"] == "web" and autoai.settings()["web_mode"] == "Neon High"


def test_gemini_tab_picks_up_the_batch_and_answers(lib):
    import threading
    from bookkeeper import geminiweb
    importlib.reload(geminiweb)
    V = geminiweb.SCRIPT_VERSION
    out, stop = {}, threading.Event()
    t = threading.Thread(target=lambda: out.update(geminiweb.ask("THE REQUEST", "Neon High", stop, out.setdefault("steps", []).append)))
    t.start()
    job = None
    for _ in range(100):
        job = geminiweb.next_job("tab-a", V)
        if job:
            break
        threading.Event().wait(0.02)
    assert job["text"] == "THE REQUEST" and job["mode"] == "Neon High" and job["name"].endswith(".txt")
    assert geminiweb.next_job("tab-b", V) is None                   # another live tab doesn't get the same batch
    assert geminiweb.next_job("tab-a", V)["id"] == job["id"]          # the same tab gets it again after a reload
    assert geminiweb.tabs()["connected"] == 2
    assert geminiweb.next_job("tab-old", V - 1) is None and geminiweb.next_job("tab-old") is None   # an old copy gets nothing
    assert geminiweb.tabs()["outdated"] == 1 and geminiweb.tabs()["connected"] == 2
    assert geminiweb.report("tab-a", job["id"], step="attaching the request")
    assert not geminiweb.report("tab-a", "someone-else", text="{}")
    assert geminiweb.report("tab-a", job["id"], text='{"label": "x", "hide": true}')
    t.join(5)
    assert out["text"] == '{"label": "x", "hide": true}'
    assert geminiweb.next_job("tab-a", V) is None


def test_gemini_tab_errors_stop_or_retry(lib):
    import threading
    from bookkeeper import autoai, geminiweb
    importlib.reload(geminiweb)

    def answer(**fields):
        res, stop = {}, threading.Event()

        def go():
            try:
                res["ok"] = geminiweb.ask("R", "", stop)
            except autoai.ApiError as e:
                res["err"] = e
        t = threading.Thread(target=go)
        t.start()
        for _ in range(100):
            job = geminiweb.next_job("tab", geminiweb.SCRIPT_VERSION)
            if job:
                break
            threading.Event().wait(0.02)
        geminiweb.report("tab", job["id"], **fields)
        t.join(5)
        return res

    r = answer(error="this Gemini tab isn't signed in", fatal=True)
    assert r["err"].wait is None and "signed in" in str(r["err"])
    r = answer(error="Gemini's Send button stayed off")
    assert r["err"].wait == 60
    r = answer(text="You've reached your limit for Neon. Try again after 6:00 PM.")
    assert r["err"].wait is None and "reached your limit" in str(r["err"])
    r = answer(text="  \n")                       # nothing read from the page: try the batch again
    assert r["err"].wait == 60 and "empty" in str(r["err"])


def test_userscript_endpoints_need_the_token(lib):
    from fastapi.testclient import TestClient
    from bookkeeper import geminiweb
    from bookkeeper.web import app as webapp
    importlib.reload(geminiweb)
    importlib.reload(webapp)
    client = TestClient(webapp.create_app(manager=None), base_url="http://127.0.0.1:8765")
    script = client.get("/api/ai/web/userscript.user.js")
    assert script.status_code == 200 and geminiweb.token() in script.text
    assert '"http://127.0.0.1:8765"' in script.text and "__TOKEN__" not in script.text and "__VERSION__" not in script.text
    assert client.get("/api/ai/web/job?tab=x").status_code == 403
    assert client.get("/api/ai/web/job?tab=x", headers={"X-Bookkeeper-Token": "wrong"}).status_code == 403
    ok = client.get("/api/ai/web/job?tab=x", headers={"X-Bookkeeper-Token": geminiweb.token()})
    assert ok.status_code == 200 and ok.json() == {"job": None}
    r = client.post("/api/ai/web/report", json={"tab": "x", "id": "nope", "text": "{}"},
                    headers={"X-Bookkeeper-Token": geminiweb.token(), "Origin": "https://gemini.google.com"})
    assert r.status_code == 200 and r.json() == {"ok": False}
    # other routes still refuse other sites
    assert client.post("/api/ai/stop", headers={"Origin": "https://gemini.google.com"}).status_code == 403


def test_old_copies_are_forgotten_soon(lib, monkeypatch):
    from bookkeeper import geminiweb
    importlib.reload(geminiweb)
    assert geminiweb.next_job("old", geminiweb.SCRIPT_VERSION - 1) is None
    assert geminiweb.tabs()["outdated"] == 1
    monkeypatch.setattr(geminiweb, "OLD_GONE", 0)   # it stopped asking: updated or closed
    assert geminiweb.tabs()["outdated"] == 0


def test_each_batch_lists_its_changes(lib):
    db, library, labels, tagai, autoai = lib
    _labels_library(library)
    r = labels.apply_import('{"label": "саске", "tags": ["fandom-naruto"]}\n{"label": "мусор", "hide": true}')
    c = labels.import_changes("label_imports", r["import"])
    rows = {x["label"]: x for x in c["labels"]}
    assert rows["саске"]["before"] == {"state": "none"} and rows["саске"]["after"]["state"] == "tags"
    assert rows["саске"]["after"]["tags"][0]["id"] == "fandom-naruto"
    assert rows["мусор"]["after"] == {"state": "hidden"} and not c["now"]
    # an import from before the change list was kept: the right side shows what the label means now
    recs = db.get_setting("label_imports", [])
    recs[0].pop("after")
    db.set_setting("label_imports", recs)
    old = labels.import_changes("label_imports", r["import"])
    assert old["now"] and {x["label"]: x for x in old["labels"]}["мусор"]["after"] == {"state": "hidden"}
    with pytest.raises(ValueError):
        labels.import_changes("label_imports", "nope")
