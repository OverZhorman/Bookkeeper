"""Start Bookkeeper: the background collectors plus the interface at http://127.0.0.1:8765/."""
import argparse
import logging
import logging.handlers
import shutil
import socket
import sqlite3
import sys
import threading
import webbrowser
from pathlib import Path

from . import __version__, config, db, sharing, tags


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) != 0


def _take_in(file: str) -> None:
    """Make a library someone shared with you the one Bookkeeper opens (see sharing.py)."""
    shown = [-1]

    def bar(done: int, total: int) -> None:
        pct = done * 100 // max(total, 1)
        if pct // 5 != shown[0]:
            shown[0] = pct // 5
            print(f"\r  {pct}%", end="", flush=True)

    print(f"\n  Taking in the library from {Path(file).name}...", flush=True)
    try:
        res = sharing.take_in(Path(file), report=lambda m: print(f"  {m}", flush=True), progress=bar)
    except sharing.ShareError as e:
        print(f"\n\n  Couldn't take in that library. {e}\n", flush=True)
        sys.exit(1)
    print(f"\n  Done: {res['books']:,} books from {res['sites']} sites. Every site starts switched off: switch on "
          f"the ones you want on the Sites page, and they carry on collecting where the copy left off.", flush=True)
    if res["kept"]:
        print(f"  The library you had before is kept as {res['kept']}", flush=True)
    if res["kept_tags"]:
        print(f"  Your own tag settings are kept as {res['kept_tags']}", flush=True)


def main():
    ap = argparse.ArgumentParser(prog="bookkeeper", description="Your personal book and web-novel catalog")
    ap.add_argument("library", nargs="?", metavar="FILE",
                    help="a library someone shared with you (the .zip file): Bookkeeper takes it in, then starts. "
                         "Dragging the file onto Bookkeeper.bat does the same")
    ap.add_argument("--port", type=int, default=config.DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1", help="127.0.0.1 = only this computer can open it")
    ap.add_argument("--no-browser", action="store_true", help="don't open the interface automatically")
    args = ap.parse_args()

    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '') else args.host}:{args.port}/"
    if not _port_free("127.0.0.1", args.port):
        if args.library:
            print("\n  Bookkeeper is running. Close its window first, then drag the file onto Bookkeeper.bat "
                  "again.\n")
            sys.exit(1)
        print(f"Bookkeeper already seems to be running. Opening {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return

    print(f"\n  Starting Bookkeeper {__version__}...", flush=True)
    config.ensure_dirs()
    handler = logging.handlers.RotatingFileHandler(config.LOG_DIR / "bookkeeper.log", maxBytes=5_000_000,
                                                   backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.WARNING)
    logging.getLogger().addHandler(console)
    shutil.rmtree(config.DATA_DIR / sharing.WORK, ignore_errors=True)  # left by a copy to share that was cut short
    if args.library:
        _take_in(args.library)

    print("  Opening your library...", flush=True)
    try:
        db.init(progress=lambda msg: print(f"  {msg}", flush=True))
    except sqlite3.OperationalError as e:
        if "locked" in str(e):
            print("\n  Your library is in use by another copy of Bookkeeper that is still running.\n"
                  "  Close its window, or end any leftover \"python.exe\" in Task Manager, then start again.\n")
            sys.exit(1)
        raise
    tags.ensure_user_file()
    print("  Starting the background collectors...", flush=True)

    from .crawler import Manager
    from .web.app import create_app
    manager = Manager()
    manager.start()
    app = create_app(manager, lan=args.host not in ("127.0.0.1", "localhost", "::1"))

    print(f"\n  Bookkeeper {__version__} is running.\n"
          f"  Open {url} in your browser (it should open by itself).\n"
          f"  Your library is stored in: {config.DATA_DIR}\n"
          f"  Close this window to stop Bookkeeper.\n")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    import uvicorn
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    finally:
        manager.stop()


if __name__ == "__main__":
    main()
