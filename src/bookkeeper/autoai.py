"""Running the AI requests by itself, while you're away: Bookkeeper sends a batch (the same request you'd copy into a
chat) to the Gemini API, checks the answer, applies everything that passes the check, then sends the next batch,
until nothing is left, you stop it, or the API's limit for the day runs out.

Every batch is a normal import (Fix site labels > My fixes, or the earlier imports of Improve tags), so each one can
be undone, and so can a whole run. The answers are saved in data/ai-runs. The API key is encrypted with your Windows
account (see secret.py) and only ever sent to Google's API."""
import re
import threading
import time

import httpx

from . import config, db, labels, secret, tagai
from .db import now

API = "https://generativelanguage.googleapis.com/v1beta"
THINKING = ("", "minimal", "low", "medium", "high")  # "" = the model's own default
MAX_TRIES = 6          # one batch: tries before the run gives up
MAX_WAIT = 15 * 60     # the longest pause for a rate limit, seconds
EMPTY_IN_A_ROW = 2     # batches in a row that change nothing: the answers are probably broken, so stop
RUNS_KEPT = 20
WEB_PAUSE = 30         # seconds between two chats on the Gemini website


class ApiError(Exception):
    """The Gemini API said no. `wait`: seconds to wait before trying again (None: don't try again)."""

    def __init__(self, message: str, wait: float | None = None):
        super().__init__(message)
        self.wait = wait


# ---------------------------------------------------------------- the key and the model
def _key_path():
    return config.DATA_DIR / "accounts" / "gemini-api.key"


def get_key() -> str:
    raw = secret.read(_key_path())
    return raw.decode("utf-8", "replace").strip() if raw else ""


def set_key(key: str) -> None:
    key = (key or "").strip()
    if not key:
        _key_path().unlink(missing_ok=True)
        return
    if not re.fullmatch(r"[\w\-.]{20,200}", key):
        raise ValueError("That doesn't look like an API key: paste only the key itself.")
    secret.write(_key_path(), key.encode("utf-8"))


def settings() -> dict:
    return {"has_key": bool(get_key()), "model": db.get_setting("ai_model", ""),
            "thinking": db.get_setting("ai_thinking", ""), "encrypted": secret.available(),
            "provider": db.get_setting("ai_provider", "web"), "web_mode": db.get_setting("ai_web_mode", "")}


def save_settings(model: str | None = None, thinking: str | None = None, provider: str | None = None,
                  web_mode: str | None = None) -> None:
    if provider is not None:
        if provider not in ("api", "web"):
            raise ValueError("Unknown way to send the requests")
        db.set_setting("ai_provider", provider)
    if web_mode is not None:
        db.set_setting("ai_web_mode", " ".join(str(web_mode).split())[:80])
    if model is not None:
        db.set_setting("ai_model", str(model).strip().removeprefix("models/"))
    if thinking is not None:
        if thinking not in THINKING:
            raise ValueError("Unknown thinking level")
        db.set_setting("ai_thinking", thinking)


# ---------------------------------------------------------------- talking to the API
def _error(r: httpx.Response) -> ApiError:
    try:
        e = r.json().get("error") or {}
    except ValueError:
        e = {}
    msg = " ".join(str(e.get("message") or r.text[:300] or "").split()) or f"HTTP {r.status_code}"
    wait, daily = None, False
    for d in e.get("details") or []:
        m = re.match(r"([\d.]+)s", str(d.get("retryDelay") or ""))
        if m:
            wait = float(m.group(1)) + 2
        for v in d.get("violations") or []:
            if "PerDay" in str(v.get("quotaId") or ""):
                daily = True
    code = r.status_code
    if code == 429:
        if re.search(r"limit: 0\b", msg):  # before the daily check: Google names the daily quota here as well
            return ApiError("This model can't be used on a free API key (its free quota is 0). Pick another model, "
                            f"or turn on billing for the key in Google AI Studio. {msg}")
        if daily:
            return ApiError(f"The Gemini API's limit for today is used up. {msg}")
        return ApiError(f"Gemini API rate limit. {msg}", wait or 60)
    if code in (500, 502, 503, 504):
        return ApiError(f"The Gemini API is busy ({code}). {msg}", wait or 60)
    if code in (400, 401, 403, 404):
        return ApiError(f"The Gemini API refused the request ({code}). {msg}")
    return ApiError(f"The Gemini API answered {code}. {msg}", 60)


def _call(method: str, path: str, key: str, body: dict | None = None, params: dict | None = None,
          timeout: float = 60) -> dict:
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=30)) as cl:
            r = cl.request(method, API + path, headers={"x-goog-api-key": key}, json=body, params=params)
    except httpx.TimeoutException:
        raise ApiError("The Gemini API took too long to answer.", 60) from None
    except httpx.HTTPError as e:
        raise ApiError(f"Couldn't reach the Gemini API: {type(e).__name__}", 60) from None
    if r.status_code >= 400:
        raise _error(r)
    return r.json()


def _model_out(m: dict) -> dict:
    return {"id": str(m.get("name") or "").removeprefix("models/"), "name": m.get("displayName") or "",
            "description": " ".join(str(m.get("description") or "").split())[:240],
            "input": m.get("inputTokenLimit"), "output": m.get("outputTokenLimit"), "thinking": bool(m.get("thinking"))}


def models(key: str | None = None) -> list[dict]:
    """The models this key can ask, newest names first."""
    key = key or get_key()
    if not key:
        raise ApiError("Save your API key first.")
    out, token = [], None
    for _ in range(20):
        r = _call("GET", "/models", key, params={"pageSize": 1000, **({"pageToken": token} if token else {})})
        out += [_model_out(m) for m in r.get("models") or []
                if "generateContent" in (m.get("supportedGenerationMethods") or [])]
        token = r.get("nextPageToken")
        if not token:
            break
    return sorted(out, key=lambda m: m["id"], reverse=True)


def model_info(model: str, key: str) -> dict:
    return _model_out(_call("GET", f"/models/{model}", key))


def ask(prompt: str, model: str, key: str, thinking: str = "", max_output: int | None = None) -> dict:
    """One request: the answer's text (without the model's thoughts), why it ended, and the tokens it used."""
    config_ = {}
    if max_output:
        config_["maxOutputTokens"] = int(max_output)
    if thinking:
        config_["thinkingConfig"] = {"thinkingLevel": thinking}
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": config_}
    r = _call("POST", f"/models/{model}:generateContent", key, body, timeout=30 * 60)
    cands = r.get("candidates") or []
    if not cands:
        why = (r.get("promptFeedback") or {}).get("blockReason")
        raise ApiError(f"Gemini gave no answer{f' ({why})' if why else ''}.", None if why else 60)
    c = cands[0]
    text = "".join(p.get("text") or "" for p in (c.get("content") or {}).get("parts") or [] if not p.get("thought"))
    u = r.get("usageMetadata") or {}
    return {"text": text, "finish": c.get("finishReason") or "", "tokens_in": u.get("promptTokenCount") or 0,
            "tokens_out": (u.get("candidatesTokenCount") or 0) + (u.get("thoughtsTokenCount") or 0)}


# ---------------------------------------------------------------- runs
_lock = threading.RLock()
_stop = threading.Event()
_thread: threading.Thread | None = None
_active: dict | None = None


def _runs() -> list[dict]:
    return db.get_setting("ai_runs", [])


def _save(rec: dict) -> None:
    with _lock:
        runs = [r for r in _runs() if r.get("id") != rec["id"]]
        db.set_setting("ai_runs", [dict(rec), *runs][:RUNS_KEPT])


def status() -> dict:
    with _lock:
        runs = _runs()
        alive = _thread is not None and _thread.is_alive()
        for r in runs:
            if r.get("state") == "running" and not (alive and _active and _active["id"] == r["id"]):
                r.update(state="stopped", step="", message="Stopped: Bookkeeper was closed while it ran.",
                         finished=r.get("finished") or now())
                _save(r)
        if alive and _active:
            runs = [dict(_active) if r.get("id") == _active["id"] else r for r in runs]
    from . import geminiweb  # local import: geminiweb uses ApiError from here
    return {**settings(), "running": alive, "runs": runs, "web_tabs": geminiweb.tabs()}


def new_record(kind: str, limit: int, max_batches: int = 0, site: str = "", q: str = "", cat: str = "",
               model: str = "", thinking: str = "", provider: str = "api") -> dict:
    return {"id": now().replace(":", "").replace("-", "").replace(".", ""), "kind": kind, "provider": provider,
            "started": now(),
            "finished": None, "state": "running", "step": "Starting…", "message": "", "model": model,
            "thinking": thinking, "undone": False, "imports": [], "batches": [],
            "params": {"limit": int(limit), "max_batches": max(0, int(max_batches or 0)), "site": site or "",
                       "q": q or "", "cat": cat or ""}}


def start(kind: str, limit: int, max_batches: int = 0, site: str = "", q: str = "", cat: str = "") -> dict:
    global _thread, _active
    if kind not in ("labels", "tags"):
        raise ValueError("Unknown kind of run")
    key, s = get_key(), settings()
    web = s["provider"] == "web"
    if not web and not key:
        raise ValueError("Save your Gemini API key first.")
    if not web and not s["model"]:
        raise ValueError("Pick a model first.")
    with _lock:
        if _thread is not None and _thread.is_alive():
            raise ValueError("A run is already going: stop it first.")
        if web:
            rec = new_record(kind, limit, max_batches, site, q, cat, s["web_mode"], "", "web")
        else:
            rec = new_record(kind, limit, max_batches, site, q, cat, s["model"], s["thinking"])
        _stop.clear()
        _active = rec
        _save(rec)
        _thread = threading.Thread(target=_main, args=(rec, key), name="bookkeeper-ai-run", daemon=True)
        _thread.start()
    return rec


def stop() -> None:
    _stop.set()
    with _lock:
        if _active and _active["state"] == "running":
            _active["step"] = "Stopping after the current step…"


def _step(rec: dict, text: str) -> None:
    rec["step"] = text
    _save(rec)


def _finish(rec: dict, state: str, message: str) -> None:
    rec.update(state=state, message=message, step="", finished=now())
    _save(rec)


def _web_ask(rec: dict):
    from . import geminiweb  # local import: geminiweb uses ApiError from here
    def on_step(text: str) -> None:
        _step(rec, f"Batch {len(rec['batches']) + 1}: {text}")
    return lambda prompt, *_: geminiweb.ask(prompt, rec["model"], _stop, on_step)


def _main(rec: dict, key: str) -> None:
    try:
        _loop(rec, key, _web_ask(rec) if rec.get("provider") == "web" else ask)
    except Exception as e:  # noqa: BLE001 - a run must always end with a message, never hang as "running"
        _finish(rec, "failed", f"Stopped by an error: {type(e).__name__}: {e}")


def _ask_with_retries(rec: dict, prompt: str, key: str, ask_fn, max_output: int | None) -> dict:
    for attempt in range(1, MAX_TRIES + 1):
        try:
            return ask_fn(prompt, rec["model"], key, rec["thinking"], max_output)
        except ApiError as e:
            if e.wait is None or attempt == MAX_TRIES:
                raise
            wait = min(e.wait, MAX_WAIT)
            _step(rec, f"{e} Trying again in {round(wait)} s (try {attempt + 1} of {MAX_TRIES})…")
            if _stop.wait(wait):
                raise ApiError("Stopped.") from None
    raise ApiError("No answer")  # not reached


def _answers_dir(rec: dict):
    return config.DATA_DIR / "ai-runs" / rec["id"]


def _loop(rec: dict, key: str, ask_fn) -> None:
    p, kind = rec["params"], rec["kind"]
    max_output = None
    try:
        max_output = model_info(rec["model"], key).get("output") if ask_fn is ask else None
    except ApiError as e:
        if e.wait is None:
            return _finish(rec, "failed", str(e))
    done: set[str] = set()        # sent and answered in this run: never sent again
    tries: dict[str, int] = {}    # sent but not answered: once more, then left alone
    empty = 0
    while True:
        n = len(rec["batches"]) + 1
        if _stop.is_set():
            return _finish(rec, "stopped", "Stopped.")
        if p["max_batches"] and n > p["max_batches"]:
            return _finish(rec, "done", "Did the batch you asked for." if p["max_batches"] == 1
                           else f"Did the {p['max_batches']} batches you asked for.")
        _step(rec, f"Preparing batch {n}…")
        skip = done | {k for k, t in tries.items() if t >= 2}
        if kind == "labels":
            out = labels.export_for_ai(p["site"] or None, p["q"], p["limit"], exclude=skip)
            sent, sent_keys, what = out["count"], out["keys"], "labels"
        else:
            out = tagai.export(p["q"], p["cat"], False, p["limit"], exclude=skip)
            sent, sent_keys, what = out["tags"], out["ids"], "tags"
        if not sent:
            return _finish(rec, "done", f"Nothing left to send: every {what[:-1]} here has had an answer.")
        _step(rec, f"Batch {n}: waiting for Gemini to answer about {sent} {what}…")
        t0 = time.time()
        try:
            ans = _ask_with_retries(rec, out["text"], key, ask_fn, max_output)
        except ApiError as e:
            return _finish(rec, "stopped" if _stop.is_set() else "failed", str(e))
        b = {"n": n, "at": now(), "sent": sent, "seconds": round(time.time() - t0), "tokens_in": ans["tokens_in"],
             "tokens_out": ans["tokens_out"], "cut_off": ans["finish"] == "MAX_TOKENS", "applied": 0, "problems": 0,
             "new_tags": 0, "books": 0, "import": None, "note": ""}
        folder = _answers_dir(rec)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"batch-{n:03d}.txt").write_text(ans["text"], encoding="utf-8")
        if ans["finish"] not in ("STOP", "MAX_TOKENS", ""):
            b["note"] = f"Gemini stopped early ({ans['finish']}). "
        _step(rec, f"Batch {n}: checking and applying the answers…")
        answered: set[str] = set()
        try:
            if kind == "labels":
                preview = labels.check_import(ans["text"])
                answered = {it["key"] for it in preview["items"]}
                b["problems"] = preview["counts"]["problems"]
                res = labels.apply_import(ans["text"])
                b.update(applied=res["labels"], new_tags=res["new_tags"], books=res["books"])
            else:
                preview = tagai.check(ans["text"])
                answered = {t["id"] for t in preview["reviewed"]}
                b["problems"] = preview["counts"]["problems"]
                res = tagai.apply(ans["text"])
                b.update(applied=res["labels"] + res["links"] + res["edits"], new_tags=res["new_tags"],
                         books=res["books"], reviewed=res["reviewed"])
            b["import"] = res.get("import")
        except ValueError as e:  # no answers in the reply, or nothing usable in them
            b["note"] += str(e)
        if b["cut_off"]:
            b["note"] += "The answer was cut off at the model's length limit: the rest comes in the next batch. "
        for k in sent_keys:
            if k in answered:
                done.add(k)
            else:
                tries[k] = tries.get(k, 0) + 1
        rec["batches"].append(b)
        if b["import"]:
            rec["imports"].append(b["import"])
        _save(rec)
        changed = b["applied"] or b["new_tags"] or b.get("reviewed")
        empty = 0 if changed else empty + 1
        if empty >= EMPTY_IN_A_ROW:
            return _finish(rec, "failed", f"{EMPTY_IN_A_ROW} batches in a row changed nothing, so the run stopped. "
                                          f"The answers are in {folder}.")
        if rec.get("provider") == "web":  # a short pause between chats, like a person would take
            _step(rec, f"Batch {n} done. The next one starts in {WEB_PAUSE} s…")
            _stop.wait(WEB_PAUSE)


def undo_run(run_id: str) -> dict:
    """Undo every import of a run, newest first."""
    with _lock:
        if _thread is not None and _thread.is_alive() and _active and _active["id"] == run_id:
            raise ValueError("Stop the run first.")
        rec = next((r for r in _runs() if r.get("id") == run_id), None)
    if not rec:
        raise ValueError("No such run.")
    undo = labels.undo_import if rec["kind"] == "labels" else tagai.undo
    undone, missing = 0, 0
    for imp in reversed(rec.get("imports") or []):
        try:
            undo(imp)
            undone += 1
        except ValueError:
            missing += 1  # already undone by hand, or too old to be in the import history
    rec["undone"] = True
    _save(rec)
    return {"undone": undone, "missing": missing}
