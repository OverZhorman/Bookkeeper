"""Where things live on disk, plus a few app-wide constants."""
import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent.parent

# Everything personal (database, downloads, logs, browser profile) goes into one folder,
# by default "data" next to Bookkeeper.bat, so it is easy to find and back up.
DATA_DIR = Path(os.environ.get("BOOKKEEPER_DATA") or PROJECT_DIR / "data")
DB_PATH = DATA_DIR / "library.db"
DOWNLOADS_DIR = DATA_DIR / "downloads"
CACHE_DIR = DATA_DIR / "cache"
LOG_DIR = DATA_DIR / "logs"
BROWSER_PROFILE_DIR = DATA_DIR / "browser-profile"
USER_TAGS_FILE = DATA_DIR / "my_tags.toml"

DEFAULT_PORT = 8765

# A normal desktop-browser User-Agent. Some sites refuse unknown clients outright.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def ensure_dirs() -> None:
    for d in (DATA_DIR, DOWNLOADS_DIR, CACHE_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
