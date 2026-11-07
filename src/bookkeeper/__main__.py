"""Start Bookkeeper: the background collectors plus the interface at http://127.0.0.1:8765/."""
import argparse
import logging
import logging.handlers
import socket
import sys
import threading
import webbrowser

from . import __version__, config, db, tags


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) != 0


def main():
    ap = argparse.ArgumentParser(prog="bookkeeper", description="Your personal book and web-novel catalog")
    ap.add_argument("--port", type=int, default=config.DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1", help="127.0.0.1 = only this computer can open it")
    ap.add_argument("--no-browser", action="store_true", help="don't open the interface automatically")
    args = ap.parse_args()

    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '') else args.host}:{args.port}/"
    if not _port_free("127.0.0.1", args.port):
        print(f"Bookkeeper already seems to be running. Opening {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return

    config.ensure_dirs()
    handler = logging.handlers.RotatingFileHandler(config.LOG_DIR / "bookkeeper.log", maxBytes=5_000_000,
                                                   backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.WARNING)
    logging.getLogger().addHandler(console)

    db.init()
    tags.ensure_user_file()

    from .crawler import Manager
    from .web.app import create_app
    manager = Manager()
    manager.start()
    app = create_app(manager)

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
