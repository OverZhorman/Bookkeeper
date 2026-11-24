"""Sharing your library with a friend.

"Make a copy to share" (on the Downloads page) writes one .zip file: the library as it is now, without anything
personal, plus your tag settings (my_tags.toml). Send it any way you like, for example through Google Drive. Your
friend drags the file onto Bookkeeper.bat (the same as `bookkeeper <file>`), and Bookkeeper takes the library in
before it starts.

The copy keeps the books, their tags and narration checks, matches between sites, forum mentions, narration
corrections, and where each site's collecting got to, so your friend's Bookkeeper carries on from there instead of
starting over. It leaves out logins, saved passwords and the AI key (files in data/accounts, which the copy never
reads), account names and the AI tab's token (settings inside the library), the history of AI imports, shelves,
favorites, notes, saved searches and downloads, and each site's settings and status. Sites start switched off."""
import json
import logging
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import zipfile
import zlib
from datetime import datetime
from pathlib import Path

from . import __version__, config

log = logging.getLogger(__name__)

FORMAT = 1  # raise it when an older Bookkeeper couldn't use a newer copy
MANIFEST = "bookkeeper-library.json"
# The library's own settings that describe the catalog. Every other one (accounts, the AI token, AI history, your
# preferences) stays home.
KEEP_META = ("schema_version", "setting:tags_version", "setting:tags_reviewed", "setting:adult_rescan_done",
             "setting:age_ratings_done")
CLEARED = ("saved_searches", "queue", "downloads")
WORK = "share-tmp"
MB, GB = 1 << 20, 1 << 30


class ShareError(Exception):
    """A problem the person can fix; the message says how."""


def size_text(n: int) -> str:
    return f"{n / GB:.1f} GB" if n >= GB // 2 else f"{max(1, round(n / MB))} MB"


def _unique(path: Path) -> Path:
    """`path`, or "name (2).ext" and so on when it's taken."""
    if not path.exists():
        return path
    for n in range(2, 1000):
        p = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not p.exists():
            return p
    raise ShareError(f"There are too many files named like {path.name} in {path.parent}.")


def _need(folder: Path, n: int) -> None:
    free = shutil.disk_usage(folder).free
    if free < n:
        raise ShareError(f"Not enough free space on {folder.anchor or folder}: this needs about {size_text(n)}, "
                         f"and {size_text(free)} is free.")


# ---------------------------------------------------------------- making a copy
def default_folder() -> Path:
    """Your browser's downloads folder, easy to find when you upload the file."""
    from . import browser
    try:
        folder = browser.user_downloads_dir()
    except Exception:  # noqa: BLE001 - an unreadable browser setting shouldn't stop the copy
        folder = None
    return folder if folder and folder.is_dir() else config.DATA_DIR / "shared"


def make_copy(folder: Path | None = None, progress=lambda stage, done=0, total=0: None) -> dict:
    """Write the copy to share into `folder`. Returns {"file", "size", "books"}. Works while Bookkeeper runs."""
    folder = Path(folder or default_folder())
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("Bookkeeper library *.zip.part"):  # left by a copy that was cut short
        old.unlink(missing_ok=True)
    work = config.DATA_DIR / WORK
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    tmp = work / "library.db"
    try:
        size = config.DB_PATH.stat().st_size
        _need(work, size + 256 * MB)
        secrets = _secrets()
        progress("copy", 0, size)
        _snapshot(tmp)
        progress("clean")
        books, sites = _strip(tmp)
        _check(tmp, secrets)
        _need(folder, tmp.stat().st_size // 2)
        path = _pack(tmp, folder, books, sites, progress)
        return {"file": str(path), "size": path.stat().st_size, "books": books}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _snapshot(tmp: Path) -> None:
    """The library as it is at this moment, written compactly. VACUUM INTO reads one moment's state, so the
    collectors keep working meanwhile."""
    src = sqlite3.connect(config.DB_PATH, timeout=60, isolation_level=None)
    try:
        src.execute("PRAGMA busy_timeout=60000")
        src.execute("VACUUM INTO ?", (str(tmp),))
    finally:
        src.close()


def _strip(tmp: Path) -> tuple[int, dict]:
    """Leave out everything personal. Deleted rows are overwritten with zeros (secure_delete), so nothing of them is
    left in the file's free space. Returns the number of books, and books per site."""
    c = sqlite3.connect(tmp, isolation_level=None)
    try:
        c.execute("PRAGMA journal_mode=DELETE")  # one self-contained file, no -wal beside it
        c.execute("PRAGMA secure_delete=ON")
        c.execute("BEGIN")
        c.execute(f"DELETE FROM meta WHERE key NOT IN ({', '.join('?' * len(KEEP_META))})", KEEP_META)
        for table in CLEARED:
            c.execute(f"DELETE FROM {table}")
        # Shelves, favorites and notes are yours; a corrected narration is about the book, so it stays.
        c.execute("DELETE FROM user_books WHERE pov IS NULL")
        c.execute("UPDATE user_books SET shelf=NULL, favorite=0, note=NULL")
        c.execute("UPDATE sites SET enabled=0, settings='{}', status='idle', status_msg=NULL")
        c.execute("COMMIT")
        sites = dict(c.execute("SELECT site, COUNT(*) FROM books GROUP BY site ORDER BY 2 DESC").fetchall())
        return sum(sites.values()), sites
    finally:
        c.close()


def _secrets() -> list[bytes]:
    """The AI tab's token, the one secret kept inside the library itself: the finished copy is checked for it."""
    c = sqlite3.connect(config.DB_PATH, timeout=60)
    try:
        row = c.execute("SELECT value FROM meta WHERE key='setting:ai_web_token'").fetchone()
    finally:
        c.close()
    try:
        token = json.loads(row[0]) if row and row[0] else ""
    except ValueError:
        token = row[0]
    return [token.encode()] if isinstance(token, str) and len(token) >= 16 else []


def _check(tmp: Path, secrets: list[bytes]) -> None:
    if not secrets:
        return
    overlap, tail = max(map(len, secrets)) - 1, b""
    with open(tmp, "rb") as f:
        while chunk := f.read(16 * MB):
            block = tail + chunk
            if any(s in block for s in secrets):
                raise RuntimeError("the copy still held a private setting, so it wasn't saved")
            tail = block[-overlap:]


def _pack(tmp: Path, folder: Path, books: int, sites: dict, progress) -> Path:
    final = _unique(folder / f"Bookkeeper library {datetime.now():%Y-%m-%d}.zip")
    part = final.with_name(final.name + ".part")
    manifest = {"format": FORMAT, "version": __version__, "made": datetime.now().astimezone().isoformat("T", "seconds"),
                "books": books, "sites": sites}
    total, done = tmp.stat().st_size, 0
    try:
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=1))
            if config.USER_TAGS_FILE.exists():
                z.writestr("my_tags.toml", config.USER_TAGS_FILE.read_bytes())
            with open(tmp, "rb") as f, z.open("library.db", "w", force_zip64=True) as out:
                while chunk := f.read(8 * MB):
                    out.write(chunk)
                    done += len(chunk)
                    progress("pack", done, total)
        part.replace(final)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return final


# ---------------------------------------------------------------- the Downloads page's button
_lock = threading.Lock()
_job: dict = {"state": "idle"}


def status() -> dict:
    with _lock:
        return dict(_job)


def start() -> dict:
    """Start making a copy in the background (one at a time)."""
    with _lock:
        if _job.get("state") != "running":
            _job.clear()
            _job.update(state="running", stage="copy", done=0, total=0, started=time.time())
            threading.Thread(target=_run, name="share-copy", daemon=True).start()
        return dict(_job)


def _progress(stage: str, done: int = 0, total: int = 0) -> None:
    with _lock:
        _job.update(stage=stage, done=done, total=total)


def _run() -> None:
    try:
        result = {**make_copy(progress=_progress), "state": "done"}
    except ShareError as e:
        result = {"state": "error", "error": str(e)}
    except Exception as e:  # noqa: BLE001 - shown on the page; the details go to the log
        log.exception("making a copy to share failed")
        result = {"state": "error", "error": f"Making the copy failed: {e}"}
    with _lock:
        _job.update(result)


def show() -> bool:
    """Open the folder with the finished copy selected, ready to drag into Google Drive."""
    path = Path(status().get("file") or "")
    if not path.is_file():
        return False
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])
    return True


# ---------------------------------------------------------------- taking in a copy
def take_in(path: Path, report=lambda msg: None, progress=lambda done, total: None) -> dict:
    """Make the shared library in `path` this computer's library. Run it before the library is opened. `path` is the
    .zip from "Make a copy to share", or the library.db inside it. The library that was here is kept as
    data/library-before-import-<time>.db (unless it had no books), and my_tags.toml likewise."""
    path = Path(path)
    if not path.is_file():
        raise ShareError(f"Can't find the file {path}.")
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    incoming = config.DATA_DIR / "library.db.importing"
    try:
        if zipfile.is_zipfile(path):
            manifest, tags_file = _unpack(path, incoming, report, progress)
        elif _is_sqlite(path):  # the library.db from inside the .zip
            manifest = {}
            sibling = path.with_name("my_tags.toml")
            tags_file = sibling.read_bytes() if sibling.is_file() else None
            _need(config.DATA_DIR, path.stat().st_size + 256 * MB)
            report(f"Copying the library ({size_text(path.stat().st_size)})...")
            shutil.copyfile(path, incoming)
        else:
            raise ShareError(f"{path.name} isn't a library shared from Bookkeeper.")
        counts = _library_counts(incoming)
        if not counts:
            raise ShareError(f"{path.name} doesn't hold a Bookkeeper library.")
        books, sites = counts
        kept = _set_aside(stamp)
        incoming.replace(config.DB_PATH)
    finally:
        for p in (incoming, *(incoming.with_name(incoming.name + s) for s in ("-wal", "-shm", "-journal"))):
            p.unlink(missing_ok=True)
    kept_tags = _take_tags(tags_file, stamp) if tags_file is not None else None
    return {"books": books, "sites": sites, "made": manifest.get("made"), "from_version": manifest.get("version"),
            "kept": str(kept) if kept else None, "kept_tags": str(kept_tags) if kept_tags else None}


def _unpack(path: Path, incoming: Path, report, progress) -> tuple[dict, bytes | None]:
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        if MANIFEST not in names or "library.db" not in names:
            raise ShareError(f"{path.name} isn't a library shared from Bookkeeper.")
        manifest = json.loads(z.read(MANIFEST))
        if int(manifest.get("format", 0)) > FORMAT:
            raise ShareError(f"This library comes from a newer Bookkeeper ({manifest.get('version')}). Update yours "
                             "first: download the newest ZIP from GitHub and unpack it over this folder.")
        info = z.getinfo("library.db")
        _need(config.DATA_DIR, info.file_size + 256 * MB)
        report(f"Unpacking {int(manifest.get('books') or 0):,} books ({size_text(info.file_size)})...")
        done = 0
        try:
            with z.open(info) as src, open(incoming, "wb") as out:
                while chunk := src.read(8 * MB):
                    out.write(chunk)
                    done += len(chunk)
                    progress(done, info.file_size)
        except (zipfile.BadZipFile, EOFError, zlib.error) as e:
            raise ShareError(f"The file is damaged ({e}). Download it again.") from None
        return manifest, z.read("my_tags.toml") if "my_tags.toml" in names else None


def _is_sqlite(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(16) == b"SQLite format 3\0"
    except OSError:
        return False


def _library_counts(path: Path) -> tuple[int, int] | None:
    """Books and sites in a library file (our own unpacked copy), or None when it isn't a Bookkeeper library."""
    if not _is_sqlite(path):
        return None
    try:
        c = sqlite3.connect(path)
        try:
            have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"books", "meta", "sites"} <= have:
                return None
            return (c.execute("SELECT COUNT(*) FROM books").fetchone()[0],
                    c.execute("SELECT COUNT(DISTINCT site) FROM books").fetchone()[0])
        finally:
            c.close()
    except sqlite3.DatabaseError:
        return None


def _set_aside(stamp: str) -> Path | None:
    """Move the library that was here out of the way: kept beside it, or deleted when it had no books."""
    db_path = config.DB_PATH
    extra = [db_path.with_name(db_path.name + s) for s in ("-wal", "-shm")]
    if not db_path.exists():
        for p in extra:
            p.unlink(missing_ok=True)
        return None
    busy, has_books = False, True
    try:
        c = sqlite3.connect(db_path, timeout=5, isolation_level=None)
        try:
            busy = bool(c.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0])  # the log goes into the file
            has_books = bool(c.execute("SELECT name FROM sqlite_master WHERE name='books'").fetchone()
                             and c.execute("SELECT 1 FROM books LIMIT 1").fetchone())
        finally:
            c.close()
    except sqlite3.OperationalError as e:
        busy = "locked" in str(e) or "busy" in str(e)
    except sqlite3.DatabaseError:
        pass  # not readable as a library: kept aside as it is
    if busy:
        raise ShareError("Your library is in use by another copy of Bookkeeper that is still running. Close its "
                         "window (or end a leftover python.exe in Task Manager), then try again.")
    if not has_books:
        db_path.unlink()
        for p in extra:
            p.unlink(missing_ok=True)
        return None
    kept = _unique(db_path.with_name(f"library-before-import-{stamp}.db"))
    db_path.replace(kept)
    for p in extra:
        if p.exists():
            p.replace(kept.with_name(kept.name + p.name[len(db_path.name):]))
    return kept


def _take_tags(data: bytes, stamp: str) -> Path | None:
    """Use the shared tag settings. Your own file is kept beside them, unless it was still the empty template."""
    from .tags import USER_FILE_TEMPLATE
    cur, kept = config.USER_TAGS_FILE, None
    if cur.exists():
        old = cur.read_bytes()
        if old == data:
            return None
        if old.decode("utf-8", "replace").replace("\r\n", "\n") != USER_FILE_TEMPLATE:
            kept = _unique(cur.with_name(f"my_tags-before-import-{stamp}.toml"))
            cur.replace(kept)
    cur.parent.mkdir(parents=True, exist_ok=True)
    cur.write_bytes(data)
    return kept
