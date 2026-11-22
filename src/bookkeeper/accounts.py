"""Logging in to sites, so Bookkeeper sees what your account sees: 18+ books, and chapters you bought.

Three ways to log in, all from the Sites page:
  1. "Log in…": a Waterfox window opens on the site's login page and you log in as usual (captchas, codes from
     e-mail and "log in with VK" all work). If you saved your login and password, Bookkeeper fills them in for you.
  2. Saved login and password: Bookkeeper logs in by itself in a hidden window, and again whenever the session runs out
     ("auto login"). The password is encrypted with your Windows account (see secret.py).
  3. "Use my Waterfox login": copies the login from your own Waterfox, if you're already logged in there. That's the
     way for logins through Google, which refuses to sign in inside a browser window a program opened. Cookies that
     last only while Waterfox runs (many sites keep their login in one) come from Waterfox's session store.

The session (cookies, plus RanobeLib's access token) is saved encrypted in data/accounts/<site>.session, and used for
the site's requests and its browser profile."""
import json
import logging
import shutil
import sqlite3
import struct
import tempfile
import time
from pathlib import Path

from . import config, db, secret
from .browser import Browser, BrowserClosed, BrowserUnavailable, user_profile_dir
from .db import now

log = logging.getLogger("bookkeeper.accounts")


def _dir() -> Path:
    return config.DATA_DIR / "accounts"


# ---------------------------------------------------------------- saved login and password
def credentials(site_id: str) -> dict | None:
    raw = secret.read(_dir() / f"{site_id}.login")
    return json.loads(raw) if raw else None


def save_credentials(site_id: str, login: str, password: str | None) -> None:
    if not secret.available():
        raise RuntimeError("saving passwords needs Windows (they are encrypted with your Windows account)")
    old = credentials(site_id) or {}
    data = {"login": login.strip(), "password": password if password else old.get("password", "")}
    secret.write(_dir() / f"{site_id}.login", json.dumps(data).encode())


def forget_credentials(site_id: str) -> None:
    (_dir() / f"{site_id}.login").unlink(missing_ok=True)


# ---------------------------------------------------------------- secret site settings (API tokens)
def secret_setting(site_id: str, key: str) -> str:
    """A site setting marked "secret" (an API token): kept encrypted next to saved passwords, not in the library."""
    raw = secret.read(_dir() / f"{site_id}.{key}.secret")
    return raw.decode("utf-8") if raw else ""


def save_secret_setting(site_id: str, key: str, value: str) -> None:
    value = (value or "").strip()
    if not value:
        (_dir() / f"{site_id}.{key}.secret").unlink(missing_ok=True)
        return
    if not secret.available():
        raise RuntimeError("saving tokens needs Windows (they are encrypted with your Windows account)")
    secret.write(_dir() / f"{site_id}.{key}.secret", value.encode("utf-8"))


# ---------------------------------------------------------------- the session
def session(site_id: str) -> dict | None:
    raw = secret.read(_dir() / f"{site_id}.session")
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def save_session(site_id: str, data: dict) -> None:
    secret.write(_dir() / f"{site_id}.session", json.dumps(data, ensure_ascii=False).encode())


def forget_session(site_id: str) -> None:
    (_dir() / f"{site_id}.session").unlink(missing_ok=True)


def _state(site_id: str) -> dict:
    return db.get_setting(f"account:{site_id}", {}) or {}


def set_state(site_id: str, **fields) -> None:
    st = _state(site_id)
    st.update(fields)
    db.set_setting(f"account:{site_id}", st)


def status(site_cls) -> dict:
    """What the Sites page shows about the account."""
    site_id = site_cls.id
    sess = session(site_id) or {}
    creds = credentials(site_id) or {}
    st = _state(site_id)
    return {
        "supported": bool(site_cls.login_url),
        "why": site_cls.login_benefit,
        # Sites that log in with a token (RanobeLib) are logged in only when the token is there.
        "logged_in": bool(sess.get("token")) if site_cls.token_js else bool(sess.get("cookies")),
        "user": sess.get("user"), "since": sess.get("at"), "how": sess.get("how"),
        "saved_login": creds.get("login"), "has_password": bool(creds.get("password")),
        "auto": bool(creds.get("password")) and st.get("auto", True),
        "auto_pref": st.get("auto", True),
        "can_save_password": secret.available(),
        "state": st.get("state"), "message": st.get("message"), "checked_at": st.get("checked_at"),
        "user_waterfox": bool(user_profile_dir()) and site_cls.login_import,
        "auto_failed": bool(st.get("auto_failed")),
    }


def domains_match(cookie_domain: str, site_domains: tuple[str, ...]) -> bool:
    d = cookie_domain.lstrip(".").lower()
    return any(d == s or d.endswith("." + s) for s in site_domains)


# Cloudflare's own cookies ("you passed the check") belong to the browser that passed the check; Bookkeeper keeps
# only the site's login cookies, so it never presents a check it didn't pass itself.
_CLOUDFLARE = ("cf_clearance", "__cf_bm", "__cflb", "_cfuvid", "__cfruid", "__cfwaitingroom", "cf_chl_", "__cf")


def _site_cookie(name: str) -> bool:
    return not any(name == c or name.startswith(c) for c in _CLOUDFLARE)


def apply(site, http) -> bool:
    """Use the saved session for this site's requests. Returns True if there was one."""
    sess = session(site.id)
    if not sess:
        return False
    for c in sess.get("cookies") or []:
        if not _site_cookie(c.get("name", "")):
            continue  # sessions saved by older versions may still hold Cloudflare's cookies
        http.client.cookies.set(c["name"], c.get("value", ""), domain=c.get("domain", "").lstrip(".") or None,
                                path=c.get("path") or "/")
    if sess.get("user_agent"):
        http.client.headers["User-Agent"] = sess["user_agent"]
    site.session_token = sess.get("token")
    return True


def clear_applied(site, http) -> None:
    http.client.cookies.clear()
    site.session_token = None


# ---------------------------------------------------------------- filling in the form
FILL_JS = """(() => {
  const visible = (el) => !!el && el.offsetParent !== null && !el.disabled && getComputedStyle(el).visibility !== "hidden";
  const pick = (sel) => { if (!sel) return null; for (const el of document.querySelectorAll(sel)) if (visible(el)) return el; return null; };
  const pwd = pick(%(password_sel)s) || pick('input[type="password"]');
  if (!pwd) return {state: "no-form"};
  let user = pick(%(user_sel)s);
  if (!user) {
    const scope = pwd.form || document;
    const inputs = [...scope.querySelectorAll('input')].filter((el) => visible(el) && /^(text|email|tel|)$/.test(el.type || ""));
    const before = inputs.filter((el) => el.compareDocumentPosition(pwd) & Node.DOCUMENT_POSITION_FOLLOWING);
    user = before.length ? before[before.length - 1] : inputs[0];
  }
  const set = (el, value) => {
    el.focus();
    const proto = Object.getPrototypeOf(el);
    const setter = Object.getOwnPropertyDescriptor(proto, "value") || Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
    setter.set.call(el, value);
    el.dispatchEvent(new Event("input", {bubbles: true}));
    el.dispatchEvent(new Event("change", {bubbles: true}));
  };
  if (user) set(user, %(login)s);
  set(pwd, %(password)s);
  const remember = (pwd.form || document).querySelector('input[type="checkbox"][name*="emember" i]');
  if (remember && !remember.checked) remember.click();
  setTimeout(() => {
    const form = pwd.form;
    const button = pick(%(submit_sel)s) || (form && [...form.querySelectorAll('button, input[type="submit"]')].find(visible));
    if (button) button.click(); else if (form) form.requestSubmit ? form.requestSubmit() : form.submit();
  }, 300);
  return {state: "submitted", user: !!user};
})()"""


def _fill(browser, site_cls, creds: dict) -> str:
    js = FILL_JS % {
        "password_sel": json.dumps(site_cls.login_form.get("password")),
        "user_sel": json.dumps(site_cls.login_form.get("user")),
        "submit_sel": json.dumps(site_cls.login_form.get("submit")),
        "login": json.dumps(creds.get("login", "")), "password": json.dumps(creds.get("password", "")),
    }
    return (browser.evaluate(js) or {}).get("state", "")


def _logged_in(browser, site_cls) -> bool:
    try:
        return bool(browser.evaluate(site_cls.logged_in_js))
    except (BrowserClosed, BrowserUnavailable):
        raise
    except Exception:
        return False  # the page is in the middle of loading


def _collect(browser, site_cls, how: str) -> dict:
    cookies = [c for c in browser.cookies() if domains_match(c.get("domain", ""), site_cls.cookie_domains())
               and _site_cookie(c.get("name", ""))]
    data = {"cookies": cookies, "user_agent": browser.user_agent(), "at": now(), "how": how}
    if site_cls.token_js:
        try:
            data["token"] = browser.evaluate(site_cls.token_js)
        except Exception:
            data["token"] = None
    if site_cls.user_js:
        try:
            data["user"] = browser.evaluate(site_cls.user_js)
        except Exception:
            pass
    return data


def login_in_browser(site_cls, interactive: bool, report=lambda msg: None) -> dict:
    """Log in through this site's own Bookkeeper browser profile. Raises RuntimeError with a readable reason."""
    creds = credentials(site_cls.id) or {}
    if not interactive and not creds.get("password"):
        raise RuntimeError("no saved login and password")
    browser = Browser(site_cls.id, headless=not interactive)
    try:
        report("Opening the login page…")
        browser.goto(site_cls.login_url, 60)
        time.sleep(2)
        if _logged_in(browser, site_cls):
            return _collect(browser, site_cls, "window" if interactive else "auto")
        filled = False
        deadline = time.time() + (600 if interactive else 75)
        while time.time() < deadline:
            if not filled and creds.get("password"):
                state = _fill(browser, site_cls, creds)
                if state == "submitted":
                    filled = True
                    report("Filled in your saved login and password…" if interactive else "Logging in…")
                    time.sleep(4)
            elif interactive:
                report("Log in in the browser window that opened. Bookkeeper continues by itself once you're in.")
            if _logged_in(browser, site_cls):
                report("Logged in. Saving the session…")
                return _collect(browser, site_cls, "window" if interactive else "auto")
            time.sleep(2)
        if interactive:
            raise RuntimeError("the login wasn't finished within 10 minutes")
        raise RuntimeError("the site didn't accept the saved login and password, or showed a check that needs you. "
                           "Press “Log in…” to log in yourself.")
    except BrowserClosed:
        raise RuntimeError("the browser window was closed before the login finished")
    finally:
        browser.close()


# ---------------------------------------------------------------- your own Waterfox
# Waterfox (like Firefox) writes cookies that have no expiry date, which last only while it runs, not to cookies.sqlite
# but to its session store, a compressed JSON file it rewrites every few seconds while it's open.
SESSION_FILES = ("sessionstore-backups/recovery.jsonlz4", "sessionstore-backups/recovery.baklz4",
                 "sessionstore.jsonlz4")


def _lz4_block(src: bytes, size: int) -> bytes:
    """Decompress one LZ4 block: sequences of literal bytes, each followed by a copy of earlier output."""
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        token = src[i]
        i += 1
        length = token >> 4
        if length == 15:
            while True:
                b = src[i]
                i += 1
                length += b
                if b != 255:
                    break
        out += src[i:i + length]
        i += length
        if i >= n:  # the last sequence has literals only
            break
        offset = src[i] | (src[i + 1] << 8)
        i += 2
        length = token & 15
        if length == 15:
            while True:
                b = src[i]
                i += 1
                length += b
                if b != 255:
                    break
        length += 4
        start = len(out) - offset
        if start < 0 or offset == 0:
            raise ValueError("corrupt LZ4 data")
        if offset >= length:
            out += out[start:start + length]
        else:  # the copy overlaps what it writes: byte by byte
            for k in range(length):
                out.append(out[start + k])
    return bytes(out[:size])


def read_mozlz4(path: Path) -> bytes:
    """A Firefox ".jsonlz4" file: "mozLz40\\0", the size, then one LZ4 block."""
    raw = path.read_bytes()
    if raw[:8] != b"mozLz40\0" or len(raw) < 12:
        raise ValueError("not a Firefox session file")
    return _lz4_block(raw[12:], struct.unpack("<I", raw[8:12])[0])


def session_store_cookies(prof: Path) -> list[dict]:
    """The cookies in your Waterfox's session store (the newest copy that can be read)."""
    for rel in SESSION_FILES:
        try:
            data = json.loads(read_mozlz4(prof / rel))
        except (OSError, ValueError, IndexError, struct.error):
            continue
        out = []
        for c in data.get("cookies") or []:
            attrs = c.get("originAttributes") or {}
            if c.get("isPartitioned") or attrs.get("userContextId") or attrs.get("privateBrowsingId"):
                continue  # third-party partitions, container tabs and private windows aren't your normal login
            if c.get("name") and c.get("host"):
                out.append({"name": c["name"], "value": c.get("value", ""), "domain": c["host"],
                            "path": c.get("path") or "/", "secure": bool(c.get("secure")),
                            "httpOnly": bool(c.get("httponly")), "expires": None})
        return out
    return []


def import_from_user_waterfox(site_cls) -> dict:
    """Copy this site's login cookies from your own Waterfox profile (it can stay open)."""
    prof = user_profile_dir()
    if not prof or not (prof / "cookies.sqlite").exists():
        raise RuntimeError("couldn't find your Waterfox profile")
    tmp = Path(tempfile.mkdtemp(prefix="bk-cookies-"))
    try:
        for name in ("cookies.sqlite", "cookies.sqlite-wal"):
            if (prof / name).exists():
                shutil.copy2(prof / name, tmp / name)
        con = sqlite3.connect(tmp / "cookies.sqlite")
        try:
            rows = con.execute("SELECT name, value, host, path, isSecure, isHttpOnly, expiry FROM moz_cookies").fetchall()
        finally:
            con.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    domains = site_cls.cookie_domains()
    now_s = time.time()
    cookies = []
    for name, value, host, path, secure, http_only, expiry in rows:
        if not domains_match(host or "", domains) or not _site_cookie(name or ""):
            continue
        exp = int(expiry) / 1000 if expiry and int(expiry) > 10 ** 11 else expiry  # some versions store milliseconds
        if exp and exp < now_s:
            continue
        cookies.append({"name": name, "value": value, "domain": host, "path": path or "/", "secure": bool(secure),
                        "httpOnly": bool(http_only), "expires": int(exp) if exp else None})
    # Cookies that last only while Waterfox runs (Booknet keeps its login in one) are in the session store instead.
    seen = {(c["domain"], c["path"], c["name"]) for c in cookies}
    for c in session_store_cookies(prof):
        key = (c["domain"], c["path"], c["name"])
        if key not in seen and domains_match(c["domain"], domains) and _site_cookie(c["name"]):
            seen.add(key)
            cookies.append(c)
    if not cookies:
        raise RuntimeError(f"your Waterfox has no login for {site_cls.name}. Log in there first, or use “Log in…”")
    return {"cookies": cookies, "user_agent": _waterfox_user_agent(), "at": now(), "how": "waterfox"}


def _waterfox_user_agent() -> str | None:
    """The User-Agent your Waterfox sends, so requests made with its login look the same."""
    from .browser import find_firefox_family
    import re
    exe = find_firefox_family()
    if not exe:
        return None
    major = None
    for ini in ("platform.ini", "application.ini"):
        try:
            text = (exe.parent / ini).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(r"^(?:Milestone|Version)=(\d+)\.", text, re.M)
        if m:
            major = m.group(1)
            break
    if not major:
        return None
    return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{major}.0) Gecko/20100101 Firefox/{major}.0"
