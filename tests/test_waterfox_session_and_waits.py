"""Logins kept in cookies that last only while Waterfox runs (Booknet with Google), and sites that ask to wait."""
import importlib
import json
import sqlite3
import struct
import time

import httpx
import pytest


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKKEEPER_DATA", str(tmp_path / "data"))
    from bookkeeper import config
    importlib.reload(config)
    from bookkeeper import db
    importlib.reload(db)
    db.init(tmp_path / "test.db")
    return tmp_path


def mozlz4(data: bytes) -> bytes:
    """A Firefox .jsonlz4 file holding one LZ4 block of literals only (valid LZ4, just not compressed)."""
    n = len(data)
    if n < 15:
        block = bytes([n << 4]) + data
    else:
        rest, ext = n - 15, bytearray()
        while rest >= 255:
            ext.append(255)
            rest -= 255
        ext.append(rest)
        block = bytes([0xF0]) + bytes(ext) + data
    return b"mozLz40\0" + struct.pack("<I", n) + block


def test_lz4_block_with_overlapping_copy_and_long_literals():
    from bookkeeper.accounts import _lz4_block
    # "abc", then 9 bytes copied from 3 back (overlapping), then the literal "X"
    assert _lz4_block(b"\x35abc\x03\x00\x10X", 13) == b"abcabcabcabcX"
    text = b"twenty literal bytes"  # 20 literals: 15 in the token, 5 in the next byte
    assert _lz4_block(bytes([0xF0, 5]) + text, 20) == text


def test_waterfox_login_from_the_session_store(env, monkeypatch):
    from bookkeeper import accounts
    importlib.reload(accounts)
    from bookkeeper.sites.booknet import Booknet
    profile = env / "profile"
    (profile / "sessionstore-backups").mkdir(parents=True)
    con = sqlite3.connect(profile / "cookies.sqlite")
    con.execute("CREATE TABLE moz_cookies(name, value, host, path, isSecure, isHttpOnly, expiry)")
    con.execute("INSERT INTO moz_cookies VALUES(?,?,?,?,?,?,?)",
                ("service", "ua", "booknet.ua", "/", 1, 0, int(time.time()) + 86400))
    con.commit()
    con.close()
    session = {"windows": [], "cookies": [
        {"host": "booknet.ua", "name": "litera-frontend", "value": "s1", "path": "/", "httponly": True, "secure": True,
         "originAttributes": {"userContextId": 0}},
        {"host": "booknet.ua", "name": "service", "value": "dup", "path": "/"},  # already in cookies.sqlite
        {"host": "booknet.ua", "name": "in-a-container", "value": "c", "path": "/",
         "originAttributes": {"userContextId": 2}},
        {"host": "booknet.ua", "name": "partitioned", "value": "p", "path": "/", "isPartitioned": True},
        {"host": ".booknet.ua", "name": "cf_clearance", "value": "x", "path": "/"},
        {"host": "example.com", "name": "other", "value": "o", "path": "/"}]}
    (profile / "sessionstore-backups" / "recovery.jsonlz4").write_bytes(mozlz4(json.dumps(session).encode()))
    monkeypatch.setattr(accounts, "user_profile_dir", lambda: profile)
    data = accounts.import_from_user_waterfox(Booknet)
    got = {c["name"]: c["value"] for c in data["cookies"]}
    assert got == {"service": "ua", "litera-frontend": "s1"} and data["how"] == "waterfox"


def test_session_store_alone_is_enough(env, monkeypatch):
    from bookkeeper import accounts
    importlib.reload(accounts)
    from bookkeeper.sites.booknet import Booknet
    profile = env / "profile"
    profile.mkdir()
    sqlite3.connect(profile / "cookies.sqlite").execute(
        "CREATE TABLE moz_cookies(name, value, host, path, isSecure, isHttpOnly, expiry)").connection.commit()
    (profile / "sessionstore.jsonlz4").write_bytes(mozlz4(json.dumps(
        {"cookies": [{"host": "booknet.ua", "name": "litera-frontend", "value": "s2", "path": "/"}]}).encode()))
    (profile / "sessionstore-backups").mkdir()
    (profile / "sessionstore-backups" / "recovery.jsonlz4").write_bytes(b"not a session file")  # skipped
    monkeypatch.setattr(accounts, "user_profile_dir", lambda: profile)
    assert [c["value"] for c in accounts.import_from_user_waterfox(Booknet)["cookies"]] == ["s2"]


def test_refusals_say_how_long_the_site_asks_to_wait():
    from bookkeeper.http import Blocked, Http, wait_note
    assert wait_note(httpx.Headers({"retry-after": "358351"})) == "; the site asks to wait about 4 days"
    assert wait_note(httpx.Headers({"retry-after": "7200"})) == "; the site asks to wait about 2 hours"
    assert wait_note(httpx.Headers({"retry-after": "600"})) == "; the site asks to wait about 10 minutes"
    assert wait_note(httpx.Headers({"retry-after": "30"})) == wait_note(httpx.Headers({})) == ""

    def site(status, retry_after):
        http = Http("t", min_interval=0)
        http.client = httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(status, headers={"retry-after": retry_after}, text="no")))
        return http

    with pytest.raises(Blocked, match=r"access denied \(HTTP 403\); the site asks to wait about 4 days"):
        site(403, "358351").get("https://example.org/")
    started = time.time()
    with pytest.raises(Blocked, match=r"rate limited \(HTTP 429\); the site asks to wait about 60 minutes"):
        site(429, "3600").get("https://example.org/")  # says so at once instead of sleeping for an hour
    assert time.time() - started < 5
