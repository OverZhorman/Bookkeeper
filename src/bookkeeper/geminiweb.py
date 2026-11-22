"""Sending the AI requests to Gemini's own web page (gemini.google.com) through a userscript in your own browser:
you sign in to Gemini as usual, keep a Gemini tab open, and the script in that tab picks up each batch from
Bookkeeper, opens a new chat, picks your mode, attaches the request as a file, sends it, waits for the whole answer and
hands it back. It uses your Gemini subscription instead of an API key, and nothing signs in through automation.

The script talks only to Bookkeeper on this computer, with a secret token that is written into your copy of the script
(see web/gemini.user.js). When Gemini shows a sign-in page or a usage limit, the run stops and tells you."""
import hmac
import json
import re
import secrets
import threading
import time
from pathlib import Path

from . import db
from .autoai import ApiError

PROMPT = "Follow the instructions in the attached file exactly. Answer only with the JSON lines, all in one code block."
SCRIPT = Path(__file__).parent / "web" / "gemini.user.js"
SCRIPT_VERSION = 8
NO_TAB_WAIT = 15 * 60      # seconds a batch waits for a Gemini tab to pick it up
ANSWER_TIMEOUT = 55 * 60   # seconds from pickup to the answer (the script itself gives up after 50 minutes)
TAB_LOST = 3 * 60          # a tab that hasn't asked for this long has been closed: another tab may take the batch
OLD_GONE = 30              # an old copy of the script that hasn't asked for this long was updated or closed (it asks every 8 s)
LIMIT_WORDS = re.compile(r"limit|try again (later|after|in)|quota|лимит|попробуйте (позже|снова)", re.I)

_lock = threading.Lock()
_job: dict | None = None
_result: dict | None = None
_done = threading.Event()
_tabs: dict[str, float] = {}   # tab id -> when it last asked for work
_old_tabs: dict[str, float] = {}   # tabs with an old copy of the script -> when they last asked (they get no work)
OLD_COPY = ("The Gemini tab has an old copy of the Bookkeeper userscript. Press \"Install the userscript\" again, "
            "accept the update, then reload the Gemini tab.")


def token() -> str:
    t = db.get_setting("ai_web_token", "")
    if not t:
        t = secrets.token_urlsafe(24)
        db.set_setting("ai_web_token", t)
    return t


def token_ok(value: str | None) -> bool:
    return bool(value) and hmac.compare_digest(str(value), token())


def userscript(base: str) -> str:
    """Your copy of the userscript: it knows where Bookkeeper is and its token."""
    text = SCRIPT.read_text(encoding="utf-8")
    for k, v in (("BASE", base.rstrip("/")), ("TOKEN", token()), ("PROMPT", PROMPT)):
        text = text.replace(f'"__{k}__"', json.dumps(v, ensure_ascii=False))
    return text.replace("__VERSION__", str(SCRIPT_VERSION))


def tabs() -> dict:
    """The Gemini tabs with the script that asked for work lately: how many, and seconds since the last one asked."""
    now_ = time.time()
    with _lock:
        recent = [now_ - t for t in _tabs.values() if now_ - t < TAB_LOST]
        old = [t for t in _old_tabs.values() if now_ - t < OLD_GONE]
    return {"connected": len(recent), "seen_ago": round(min(recent)) if recent else None, "outdated": len(old)}


# ---------------------------------------------------------------- what the script calls
def next_job(tab: str, version: int = 0) -> dict | None:
    """The batch for this tab, if there is one and no other (live) tab has taken it. A tab running an old copy of
    the script gets nothing: the panel and the run tell you to install it again."""
    tab = str(tab or "")[:64] or "tab"
    now_ = time.time()
    with _lock:
        if version < SCRIPT_VERSION:
            _old_tabs[tab] = now_
            _tabs.pop(tab, None)
            return None
        _old_tabs.pop(tab, None)
        _tabs[tab] = now_
        for t in [t for t, at in _tabs.items() if now_ - at > 24 * 3600]:
            del _tabs[t]
        job = _job
        if job is None or _done.is_set():
            return None
        holder = job.get("tab")
        if holder and holder != tab and now_ - _tabs.get(holder, 0) < TAB_LOST:
            return None
        if holder != tab:
            job.update(tab=tab, taken=now_, step="picked up by the Gemini tab")
        return {k: job[k] for k in ("id", "mode", "name", "text")}


def report(tab: str, job_id: str, step: str | None = None, text: str | None = None, error: str | None = None,
           fatal: bool = False) -> bool:
    global _result
    with _lock:
        _tabs[str(tab or "")[:64] or "tab"] = time.time()
        job = _job
        if job is None or job["id"] != job_id or _done.is_set():
            return False
        if step:
            job["step"] = str(step)[:200]
        if text is not None or error:
            _result = {"text": text, "error": str(error)[:500] if error else None, "fatal": bool(fatal)}
            _done.set()
    return True


# ---------------------------------------------------------------- what autoai calls
def ask(prompt: str, mode: str, stop: threading.Event, on_step=lambda s: None) -> dict:
    global _job, _result
    with _lock:
        if _job is not None:
            raise ApiError("Another batch is already waiting for the Gemini tab.")
        _job = {"id": secrets.token_hex(8), "mode": mode or "", "name": f"bk{time.strftime('%H%M%S')}.txt",
                "text": prompt, "created": time.time(), "tab": None, "taken": None, "step": ""}
        _result = None
        _done.clear()
        job = _job
    try:
        shown = None
        while not _done.is_set():
            if stop.wait(2):
                raise ApiError("Stopped.")
            with _lock:
                taken, step = job["taken"], job["step"]
            if not taken and time.time() - job["created"] > NO_TAB_WAIT:
                raise ApiError(f"No Gemini tab with the Bookkeeper userscript picked up the batch in "
                               f"{NO_TAB_WAIT // 60} minutes. Open gemini.google.com in the browser where the "
                               "script is installed, and keep that tab open.")
            if taken and time.time() - taken > ANSWER_TIMEOUT:
                raise ApiError("The Gemini tab didn't send an answer back.", 60)
            seen = tabs()
            text = step if taken else OLD_COPY if seen["outdated"] and not seen["connected"] \
                else "waiting for a Gemini tab with the userscript…"
            if text != shown:
                on_step(text)
                shown = text
        r = _result or {}
    finally:
        with _lock:
            _job = None
    if r.get("error"):
        raise ApiError(f"The Gemini tab says: {r['error']}", None if r.get("fatal") else 60)
    text = r.get("text") or ""
    if not text.strip():
        raise ApiError("The Gemini tab sent back an empty answer.", 60)
    if "{" not in text and LIMIT_WORDS.search(text):
        raise ApiError(f"Gemini says: {' '.join(text.split())[:400]}")
    return {"text": text, "finish": "STOP", "tokens_in": 0, "tokens_out": 0}
