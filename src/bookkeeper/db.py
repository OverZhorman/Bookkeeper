"""SQLite storage. One connection per thread; WAL mode so the crawler and the web UI can work at once."""
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import config

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS sites(
    id         TEXT PRIMARY KEY,
    enabled    INTEGER NOT NULL DEFAULT 0,
    settings   TEXT NOT NULL DEFAULT '{}',   -- JSON: speed, cookies, scope...
    state      TEXT NOT NULL DEFAULT '{}',   -- JSON: where catalog discovery stopped, last runs
    status     TEXT NOT NULL DEFAULT 'idle', -- idle / running / blocked / error / done
    status_msg TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS books(
    id             INTEGER PRIMARY KEY,
    site           TEXT NOT NULL,
    sid            TEXT NOT NULL,            -- the book's id on its site
    url            TEXT NOT NULL,
    title          TEXT NOT NULL,
    alt_titles     TEXT NOT NULL DEFAULT '[]',
    authors        TEXT NOT NULL DEFAULT '[]',
    author_sort    TEXT,
    description    TEXT,
    cover          TEXT,
    lang           TEXT,                     -- ru / en / uk / ...
    status         TEXT,                     -- ongoing / completed / frozen / unknown
    is_translation INTEGER,                  -- 1 translation, 0 original, NULL unknown
    origin         TEXT,                     -- original country / language of translated works
    chapters       INTEGER,
    words          INTEGER,
    rating         REAL,                     -- 0..10
    votes          INTEGER,
    views          INTEGER,
    likes          INTEGER,
    pop_raw        REAL,                     -- site-specific popularity number
    popularity     REAL,                     -- 0..1, rank within its site
    adult          INTEGER NOT NULL DEFAULT 0,
    access         TEXT,                     -- free / partial / paid
    created_at     TEXT,
    updated_at     TEXT,
    added_at       TEXT NOT NULL,
    meta_at        TEXT,                     -- when full details were fetched
    analyzed_at    TEXT,                     -- when chapter text was analysed (or attempted)
    work_id        INTEGER,                  -- groups copies of the same book on different sites
    is_primary     INTEGER NOT NULL DEFAULT 1,
    pov            TEXT,                     -- effective narration: first / third / second / mixed / unsure
    pov_source     TEXT,                     -- user / site / text / other-site
    narrator       TEXT,                     -- male / female (Russian/Ukrainian first-person books)
    extra          TEXT NOT NULL DEFAULT '{}',
    UNIQUE(site, sid)
);
CREATE INDEX IF NOT EXISTS books_site_meta     ON books(site, meta_at);
CREATE INDEX IF NOT EXISTS books_site_analyzed ON books(site, analyzed_at);
CREATE INDEX IF NOT EXISTS books_pov           ON books(pov);
CREATE INDEX IF NOT EXISTS books_popularity    ON books(popularity);
CREATE INDEX IF NOT EXISTS books_updated       ON books(updated_at);
CREATE INDEX IF NOT EXISTS books_work          ON books(work_id);
CREATE INDEX IF NOT EXISTS books_pop_raw       ON books(site, pop_raw);

CREATE TABLE IF NOT EXISTS tags(
    id       TEXT PRIMARY KEY,               -- canonical tag id
    label    TEXT NOT NULL,                  -- display label
    label_ru TEXT,
    category TEXT,
    known    INTEGER NOT NULL DEFAULT 0,     -- 1 = from the built-in shared tag list
    books    INTEGER NOT NULL DEFAULT 0      -- cached number of books with this tag
);

CREATE TABLE IF NOT EXISTS book_tags(
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    tag     TEXT NOT NULL,
    source  TEXT NOT NULL,                   -- site / rule / text / other-site / user
    raw     TEXT,                            -- the label as written on the site
    PRIMARY KEY(book_id, tag, source)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS book_tags_tag ON book_tags(tag, book_id);

CREATE TABLE IF NOT EXISTS analysis(
    book_id     INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,
    pov         TEXT,
    confidence  REAL,
    narrator    TEXT,
    tense       TEXT,
    game_system INTEGER,
    chapters    INTEGER,
    words       INTEGER,
    details     TEXT,
    version     INTEGER,
    error       TEXT,
    attempts    INTEGER NOT NULL DEFAULT 0,
    at          TEXT
);

CREATE TABLE IF NOT EXISTS user_books(
    book_id    INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,
    shelf      TEXT,                         -- read / reading / want / dropped / hidden
    favorite   INTEGER NOT NULL DEFAULT 0,
    pov        TEXT,                         -- your own correction of the narration
    note       TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS saved_searches(
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    query      TEXT NOT NULL,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS queue(           -- "analyse this now" requests from the UI
    book_id      INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,
    priority     INTEGER NOT NULL DEFAULT 0,
    requested_at TEXT
);

CREATE TABLE IF NOT EXISTS downloads(
    id          INTEGER PRIMARY KEY,
    book_id     INTEGER NOT NULL,
    fmt         TEXT NOT NULL,
    state       TEXT NOT NULL,               -- queued / running / done / error
    progress    INTEGER NOT NULL DEFAULT 0,
    total       INTEGER NOT NULL DEFAULT 0,
    file        TEXT,
    error       TEXT,
    options     TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS match_keys(       -- normalized title(+author) keys for finding the same book elsewhere
    key     TEXT NOT NULL,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    site    TEXT NOT NULL,
    PRIMARY KEY(key, book_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS match_keys_book ON match_keys(book_id);

CREATE TABLE IF NOT EXISTS mentions(          -- books mentioned in forum posts, matched to the library over time
    id       INTEGER PRIMARY KEY,
    source   TEXT NOT NULL,
    post_url TEXT NOT NULL,
    at       TEXT,
    site     TEXT,                            -- for links to a known site: which site and which book there
    sid      TEXT,
    url      TEXT,
    title    TEXT,                            -- for "Author «Title»" in the text
    author   TEXT,
    matched  INTEGER NOT NULL DEFAULT 0,
    UNIQUE(source, post_url, site, sid, url, title, author)
);
CREATE INDEX IF NOT EXISTS mentions_open ON mentions(matched);

CREATE TABLE IF NOT EXISTS recommendations(  -- books recommended on forums (Kubikus)
    book_id  INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    source   TEXT NOT NULL,
    post_url TEXT NOT NULL,
    at       TEXT,
    PRIMARY KEY(book_id, source, post_url)
) WITHOUT ROWID;

CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5(
    title, alt_titles, authors, description,
    content='books', content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);
CREATE TRIGGER IF NOT EXISTS books_fts_ai AFTER INSERT ON books BEGIN
    INSERT INTO books_fts(rowid, title, alt_titles, authors, description)
    VALUES (new.id, new.title, new.alt_titles, new.authors, new.description);
END;
CREATE TRIGGER IF NOT EXISTS books_fts_ad AFTER DELETE ON books BEGIN
    INSERT INTO books_fts(books_fts, rowid, title, alt_titles, authors, description)
    VALUES ('delete', old.id, old.title, old.alt_titles, old.authors, old.description);
END;
CREATE TRIGGER IF NOT EXISTS books_fts_au AFTER UPDATE OF title, alt_titles, authors, description ON books BEGIN
    INSERT INTO books_fts(books_fts, rowid, title, alt_titles, authors, description)
    VALUES ('delete', old.id, old.title, old.alt_titles, old.authors, old.description);
    INSERT INTO books_fts(rowid, title, alt_titles, authors, description)
    VALUES (new.id, new.title, new.alt_titles, new.authors, new.description);
END;
"""

# Columns added after the first release: (table, column, definition). Applied on start if missing.
MIGRATIONS = [
    ("analysis", "attempts", "INTEGER NOT NULL DEFAULT 0"),
    ("tags", "label_uk", "TEXT"),
]

_local = threading.local()
_init_lock = threading.Lock()
_initialized_path: Path | None = None


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def jdump(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def jload(text, default=None):
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA cache_size=-65536")
    # SQLite's own lower() only handles A-Z; this one handles Cyrillic too.
    conn.create_function("ulower", 1, lambda s: s.lower() if isinstance(s, str) else s, deterministic=True)
    return conn


def init(path: Path | None = None) -> None:
    """Create tables if needed. Safe to call many times."""
    global _initialized_path
    path = Path(path or config.DB_PATH)
    with _init_lock:
        if _initialized_path == path:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = _connect(path)
        conn.executescript(SCHEMA)
        for table, column, definition in MIGRATIONS:
            have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if column not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(SCHEMA_VERSION),),
        )
        conn.close()
        _initialized_path = path
        _local.__dict__.clear()


def conn() -> sqlite3.Connection:
    """The calling thread's connection."""
    if _initialized_path is None:
        init()
    c = getattr(_local, "conn", None)
    if c is None or getattr(_local, "path", None) != _initialized_path:
        c = _connect(_initialized_path)
        _local.conn = c
        _local.path = _initialized_path
    return c


class transaction:
    """`with transaction() as c:` runs the block in one write transaction."""

    def __enter__(self) -> sqlite3.Connection:
        self.c = conn()
        self.c.execute("BEGIN IMMEDIATE")
        return self.c

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.c.execute("COMMIT")
        else:
            self.c.execute("ROLLBACK")
        return False


def get_setting(key: str, default=None):
    row = conn().execute("SELECT value FROM meta WHERE key=?", (f"setting:{key}",)).fetchone()
    return jload(row["value"], default) if row else default


def set_setting(key: str, value) -> None:
    conn().execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (f"setting:{key}", jdump(value)),
    )
