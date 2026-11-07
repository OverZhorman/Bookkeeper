"""Downloading with a browser extension in your own Waterfox, such as ExLoader (it saves Author.Today, Ficbook and
Readli books as FB2 or EPUB, also where the site itself offers no download).

"Open in my Waterfox" opens the book's page in your normal Waterfox, where your extensions are. Download the book
with the extension there. For the next 30 minutes Bookkeeper watches the folder your Waterfox saves downloads to; when
a book file appears, it is copied into data/downloads and listed under that book and on the Downloads page."""
import logging
import re
import shutil
import threading
import time
from pathlib import Path

from . import config, db
from .browser import open_in_user_browser, user_downloads_dir
from .db import jdump, now

log = logging.getLogger("bookkeeper.handoff")

BOOK_SUFFIXES = (".fb2.zip", ".epub", ".fb2", ".zip", ".txt", ".docx", ".doc", ".rtf", ".pdf", ".mobi", ".azw3",
                 ".html", ".htm", ".djvu")
WATCH_MINUTES = 30

_pending: dict[int, dict] = {}   # book id -> what we're waiting for
_lock = threading.Lock()
_watcher: threading.Thread | None = None


def _suffix(name: str) -> str | None:
    low = name.lower()
    return next((s for s in BOOK_SUFFIXES if low.endswith(s)), None)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", (text or "").lower().replace("ё", "е")) if len(w) > 2}


def _snapshot(folder: Path) -> dict[str, float]:
    out = {}
    try:
        for f in folder.iterdir():
            if f.is_file() and _suffix(f.name):
                out[f.name] = f.stat().st_mtime
    except OSError:
        pass
    return out


def start(book_id: int) -> dict:
    row = db.conn().execute("SELECT url, title, authors FROM books WHERE id=?", (book_id,)).fetchone()
    if not row:
        raise KeyError(book_id)
    folder = user_downloads_dir()
    if not folder:
        raise RuntimeError("couldn't find your downloads folder; set it on the Sites page")
    browser = open_in_user_browser(row["url"])
    with _lock:
        _pending[book_id] = {"book_id": book_id, "title": row["title"], "authors": row["authors"],
                             "folder": str(folder), "started": time.time(), "before": _snapshot(folder),
                             "sizes": {}, "browser": browser}
    _ensure_watcher()
    return status(book_id)


def cancel(book_id: int) -> None:
    with _lock:
        _pending.pop(book_id, None)


def status(book_id: int) -> dict | None:
    p = _pending.get(book_id)
    if not p:
        return None
    left = max(0, int(WATCH_MINUTES * 60 - (time.time() - p["started"])))
    return {"waiting": True, "folder": p["folder"], "browser": p["browser"], "seconds_left": left}


def _ensure_watcher():
    global _watcher
    if _watcher is None or not _watcher.is_alive():
        _watcher = threading.Thread(target=_watch, name="download-watcher", daemon=True)
        _watcher.start()


def _watch():
    while True:
        time.sleep(3)
        with _lock:
            if not _pending:
                return
            jobs = list(_pending.values())
        for p in jobs:
            try:
                _check(p)
            except Exception as e:  # pragma: no cover - never stop watching over one bad file
                log.warning("download watcher: %s", e)


def _new_files(p: dict) -> list[Path]:
    folder = Path(p["folder"])
    out = []
    for name, mtime in _snapshot(folder).items():
        if name in p["before"] and p["before"][name] >= mtime:
            continue
        if mtime < p["started"] - 5:
            continue
        if (folder / (name + ".part")).exists():
            continue  # still downloading
        out.append(folder / name)
    return out


def _check(p: dict):
    if time.time() - p["started"] > WATCH_MINUTES * 60:
        cancel(p["book_id"])
        return
    for f in _new_files(p):
        try:
            size = f.stat().st_size
        except OSError:
            continue
        if size == 0 or p["sizes"].get(f.name) != size:
            p["sizes"][f.name] = size  # wait until the size stops changing
            continue
        owner = _best_owner(f.name, p)
        if owner is not p:
            continue
        _import(f, p)
        cancel(p["book_id"])
        return


def _best_owner(filename: str, fallback: dict) -> dict:
    """With several books waiting, the one whose title (and author) best matches the file name."""
    with _lock:
        jobs = list(_pending.values())
    if len(jobs) <= 1:
        return fallback
    words = _words(filename)
    scored = sorted(jobs, key=lambda j: (len(words & (_words(j["title"]) | _words(j["authors"]))), -j["started"]),
                    reverse=True)
    best = scored[0]
    return best if words & (_words(best["title"]) | _words(best["authors"])) else min(jobs, key=lambda j: j["started"])


def _import(f: Path, p: dict):
    config.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    target = config.DOWNLOADS_DIR / f.name
    n = 2
    while target.exists():
        suffix = _suffix(f.name) or f.suffix
        target = config.DOWNLOADS_DIR / f"{f.name[:-len(suffix)]} ({n}){suffix}"
        n += 1
    shutil.copy2(f, target)
    suffix = (_suffix(f.name) or f.suffix).lstrip(".")
    fmt = {"fb2.zip": "fb2", "htm": "html"}.get(suffix, suffix)
    db.conn().execute(
        "INSERT INTO downloads(book_id, fmt, state, progress, total, file, options, created_at, finished_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (p["book_id"], fmt, "done", 1, 1, target.name,
         jdump({"note": f"saved by a browser extension in {p['browser']}", "via": "browser"}), now(), now()))
    log.info("picked up %s from %s for book %s", f.name, p["folder"], p["book_id"])
