"""Real browsers, for the things plain requests can't do:

- Author.Today scrambles chapter text in transit and its own reader unscrambles it on screen, so we read the screen
  text, the same way you would;
- logging in to a site (you type your password, or Bookkeeper fills in the one you saved);
- site tests, when a page shows an "are you human?" check that you complete yourself.

Bookkeeper prefers Waterfox (or another Firefox) when it is installed, and falls back to Microsoft Edge or Google
Chrome. Waterfox is driven through WebDriver BiDi, the remote-control protocol built into Firefox, so nothing extra is
downloaded. Each site gets its own browser profile in data/browser-profile, so a login made there is remembered.
A Browser object must only be used from one thread at a time."""
import json
import logging
import os
import queue
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import config

log = logging.getLogger("bookkeeper.browser")

# Pages that are a bot check or a "please wait" screen rather than the page itself.
CHECK_TITLE = re.compile(r"just a moment|attention required|один момент|проверка|checking|security check|"
                         r"ddos-guard|access denied|captcha|подождите", re.I)


class BrowserUnavailable(Exception):
    pass


class BrowserClosed(Exception):
    """The browser window was closed (usually by you) while Bookkeeper was still using it."""


# ---------------------------------------------------------------- finding Waterfox / Firefox
def _registry_app_path(exe: str) -> Path | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg
    except ImportError:
        return None
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as k:
                value, _ = winreg.QueryValueEx(k, "")
                if value and Path(value).exists():
                    return Path(value)
        except OSError:
            continue
    return None


def _candidates(name: str, exe: str) -> list[Path]:
    out = []
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        if os.environ.get(env):
            out.append(Path(os.environ[env]) / name / exe)
    if os.environ.get("LOCALAPPDATA"):
        out += [Path(os.environ["LOCALAPPDATA"]) / name / exe, Path(os.environ["LOCALAPPDATA"]) / "Programs" / name / exe]
    if sys.platform != "win32":
        base = exe.replace(".exe", "")
        out += [Path("/usr/bin") / base, Path("/usr/local/bin") / base, Path(f"/opt/{base}/{base}"),
                Path(f"/Applications/{name}.app/Contents/MacOS/{base}")]
    return out


def find_firefox_family(prefer: str = "waterfox") -> Path | None:
    """Waterfox (or, failing that, Firefox). The path can also be set on the Sites page or in BOOKKEEPER_WATERFOX."""
    from . import db
    custom = os.environ.get("BOOKKEEPER_WATERFOX") or db.get_setting("waterfox_path", "")
    if custom and Path(custom).exists():
        return Path(custom)
    names = [("Waterfox", "waterfox.exe"), ("Mozilla Firefox", "firefox.exe")]
    if prefer == "firefox":
        names.reverse()
    for name, exe in names:
        p = _registry_app_path(exe)
        if p:
            return p
        for c in _candidates(name, exe if sys.platform == "win32" else exe.replace(".exe", "")):
            if c.exists():
                return c
    return None


def engine_choice() -> str:
    """'waterfox' or 'edge', from the setting on the Sites page ('auto' = Waterfox when it is installed)."""
    from . import db
    choice = os.environ.get("BOOKKEEPER_BROWSER_ENGINE") or db.get_setting("browser", "auto")
    if choice == "edge":
        return "edge"
    if find_firefox_family():
        return "waterfox"
    return "edge"


def engine_label(engine: str | None = None) -> str:
    engine = engine or engine_choice()
    if engine == "waterfox":
        p = find_firefox_family()
        return "Firefox" if p and "firefox" in p.name.lower() else "Waterfox"
    return "Microsoft Edge"


# ---------------------------------------------------------------- your own Waterfox (profile, downloads folder)
def user_profile_dir() -> Path | None:
    """The profile your own Waterfox uses (where your extensions, logins and settings are)."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    for app in ("Waterfox", r"Mozilla\Firefox"):
        root = Path(appdata) / app
        ini = root / "profiles.ini"
        if not ini.exists():
            continue
        text = ini.read_text(encoding="utf-8", errors="replace")
        sections, current = {}, None
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                current = sections.setdefault(line[1:-1], {})
            elif "=" in line and current is not None:
                k, v = line.split("=", 1)
                current[k.strip()] = v.strip()
        paths = [s["Default"] for name, s in sections.items() if name.startswith("Install") and s.get("Default")]
        paths += [s["Path"] for s in sections.values() if s.get("Default") == "1" and s.get("Path")]
        paths += [s["Path"] for s in sections.values() if s.get("Path")]
        for rel in paths:
            p = Path(rel) if Path(rel).is_absolute() else root / rel
            if (p / "prefs.js").exists():
                return p
    return None


def _known_downloads_folder() -> Path | None:
    if sys.platform != "win32":
        p = Path.home() / "Downloads"
        return p if p.exists() else None
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                        ("Data4", wintypes.BYTE * 8)]

        g = GUID(0x374DE290, 0x123F, 0x4565, (wintypes.BYTE * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B))
        ptr = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(ptr)) == 0:
            value = ptr.value
            ctypes.windll.ole32.CoTaskMemFree(ptr)
            return Path(value)
    except Exception:
        pass
    p = Path.home() / "Downloads"
    return p if p.exists() else None


def user_downloads_dir() -> Path | None:
    """Where your own Waterfox saves downloads (its setting, else the Windows Downloads folder)."""
    from . import db
    custom = db.get_setting("browser_downloads_dir", "")
    if custom and Path(custom).is_dir():
        return Path(custom)
    prof = user_profile_dir()
    if prof:
        prefs = (prof / "prefs.js").read_text(encoding="utf-8", errors="replace")
        folder_list = re.search(r'user_pref\("browser\.download\.folderList",\s*(\d+)\)', prefs)
        folder = re.search(r'user_pref\("browser\.download\.dir",\s*"((?:[^"\\]|\\.)*)"\)', prefs)
        if folder_list and folder_list.group(1) == "2" and folder:
            p = Path(json.loads(f'"{folder.group(1)}"'))
            if p.is_dir():
                return p
        if folder_list and folder_list.group(1) == "0":
            return Path.home() / "Desktop"
    return _known_downloads_folder()


def open_in_user_browser(url: str) -> str:
    """Open a page in your own Waterfox (with your extensions, like ExLoader). Returns the browser's name."""
    exe = find_firefox_family()
    if exe:
        subprocess.Popen([str(exe), "-new-tab", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0)
        return engine_label("waterfox")
    import webbrowser
    webbrowser.open(url)
    return "your default browser"


# ---------------------------------------------------------------- common interface
class BaseBrowser:
    engine = ""

    def __init__(self, site_id: str, headless: bool = True):
        self.site_id = site_id
        self.headless = headless
        self.initial_cookies: list[dict] = []   # e.g. your saved login, added whenever the browser starts

    def _apply_initial_cookies(self):
        if self.initial_cookies:
            try:
                self.add_cookies(self.initial_cookies)
            except Exception as e:
                log.info("couldn't add the saved login to the %s browser: %s", self.site_id, e)

    # The visible text of `selector` once it has at least `min_chars` characters; None straight away if the page
    # text matches `locked_pattern` (a paywall or login notice).
    def text(self, url: str, selector: str, min_chars: int = 200, timeout: float = 40.0,
             locked_pattern: str | None = None) -> str | None:
        self.goto(url, timeout)
        deadline = time.time() + timeout
        js = """(() => {
            const el = document.querySelector(%s);
            if (el && el.innerText.trim().length > %d) return {state: "text", text: el.innerText};
            const locked = %s;
            if (locked && document.body && new RegExp(locked, "i").test(document.body.innerText)) return {state: "locked"};
            return {state: "wait"};
        })()""" % (json.dumps(selector), min_chars, json.dumps(locked_pattern))
        while time.time() < deadline:
            r = self.evaluate(js) or {}
            if r.get("state") == "text":
                return r.get("text") or ""
            if r.get("state") == "locked":
                return None
            time.sleep(0.5)
        raise TimeoutError(f"the text didn't appear within {int(timeout)} s")

    def page_html(self, url: str, wait_seconds: int = 90) -> str | None:
        """Open a page and return its HTML once real content (not a check page) is showing; None if it never does."""
        self.goto(url, 60)
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            info = self.evaluate("({title: document.title || '', len: document.body ? document.body.innerText.length : 0})") or {}
            if info.get("len", 0) > 1500 and not CHECK_TITLE.search(info.get("title", "")):
                return self.evaluate("document.documentElement.outerHTML")
            time.sleep(2)
        return None

    def current_url(self) -> str:
        return self.evaluate("location.href") or ""

    def goto(self, url: str, timeout: float = 60.0):
        raise NotImplementedError

    def evaluate(self, expression: str):
        """Run JavaScript in the page and return its (JSON-compatible) value."""
        raise NotImplementedError

    def cookies(self) -> list[dict]:
        """All cookies as {name, value, domain, path, secure, httpOnly, expires}."""
        raise NotImplementedError

    def add_cookies(self, cookies: list[dict]):
        raise NotImplementedError

    def user_agent(self) -> str:
        return self.evaluate("navigator.userAgent") or ""

    def is_running(self) -> bool:
        raise NotImplementedError

    def open_for_login(self, url: str):
        """Show a visible window at `url` (the session is kept in this site's profile)."""
        self.close()
        self.headless = False
        self.goto(url)

    def close(self):
        raise NotImplementedError


# ---------------------------------------------------------------- Waterfox / Firefox over WebDriver BiDi
USER_JS = """// Written by Bookkeeper for its own browser profile (your normal Waterfox profile is not touched).
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("browser.startup.page", 0);
user_pref("browser.aboutwelcome.enabled", false);
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("browser.tabs.warnOnClose", false);
user_pref("browser.warnOnQuit", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);
user_pref("intl.accept_languages", "ru-RU, ru, en-US, en");
user_pref("signon.rememberSignons", false);
"""


class WaterfoxBrowser(BaseBrowser):
    engine = "waterfox"

    def __init__(self, site_id: str, headless: bool = True, profile: Path | None = None):
        super().__init__(site_id, headless)
        self.profile = profile or (config.BROWSER_PROFILE_DIR / "waterfox" / site_id)
        self._proc: subprocess.Popen | None = None
        self._ws = None
        self._ctx: str | None = None
        self._next_id = 0
        self._pending: dict[int, queue.Queue] = {}
        self._send_lock = threading.Lock()
        self._closed = threading.Event()

    # ----- process and connection
    def _start(self):
        exe = find_firefox_family()
        if not exe:
            raise BrowserUnavailable("Waterfox isn't installed (or Bookkeeper can't find it)")
        try:
            from websockets.sync.client import connect
        except ImportError as e:
            raise BrowserUnavailable("the browser helper (websockets) is not installed; run Update.bat") from e
        self.profile.mkdir(parents=True, exist_ok=True)
        (self.profile / "user.js").write_text(USER_JS, encoding="utf-8")
        args = [str(exe), "-profile", str(self.profile), "-no-remote", "-new-instance",
                "--remote-debugging-port", "0"]
        if self.headless:
            args.append("-headless")
        args.append("about:blank")
        self._closed.clear()
        self._proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                      text=True, encoding="utf-8", errors="replace",
                                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0)
        found: queue.Queue = queue.Queue()

        def pump(stream):
            for line in stream:  # keep reading so the browser never blocks on a full pipe
                m = re.search(r"WebDriver BiDi listening on (ws://\S+)", line)
                if m:
                    found.put(m.group(1))
                elif "already running" in line.lower():
                    found.put("in-use")
            found.put(None)

        threading.Thread(target=pump, args=(self._proc.stdout,), name=f"waterfox-log-{self.site_id}",
                         daemon=True).start()
        try:
            url = found.get(timeout=45)
        except queue.Empty:
            url = None
        if not url or url == "in-use":
            self._kill()
            raise BrowserUnavailable("Waterfox didn't start" + (" (its Bookkeeper profile is in use by another "
                                                                 "Waterfox window)" if url == "in-use" else ""))
        self._ws = connect(url.rstrip("/") + "/session", max_size=256 * 1024 * 1024, open_timeout=30,
                           ping_interval=None, close_timeout=5)
        self._ws.__enter__()  # websockets >= 17 wants the connection used as a context manager
        threading.Thread(target=self._reader, name=f"waterfox-bidi-{self.site_id}", daemon=True).start()
        self._cmd("session.new", {"capabilities": {}})
        self._cmd("session.subscribe", {"events": ["browsingContext.contextDestroyed"]})
        self._ctx = self._top_context()
        self._apply_initial_cookies()

    def _reader(self):
        try:
            while True:
                msg = json.loads(self._ws.recv())
                q = self._pending.pop(msg.get("id"), None) if "id" in msg else None
                if q is not None:
                    q.put(msg)
                elif msg.get("method") == "browsingContext.contextDestroyed":
                    if (msg.get("params") or {}).get("context") == self._ctx:
                        self._ctx = None
        except Exception:
            pass
        finally:
            self._closed.set()
            for q in list(self._pending.values()):
                q.put({"type": "error", "error": "closed", "message": "the browser was closed"})
            self._pending.clear()

    def _cmd(self, method: str, params: dict | None = None, timeout: float = 90.0):
        if self._ws is None or self._closed.is_set():
            raise BrowserClosed("the browser window was closed")
        q: queue.Queue = queue.Queue()
        with self._send_lock:
            self._next_id += 1
            cid = self._next_id
            self._pending[cid] = q
            self._ws.send(json.dumps({"id": cid, "method": method, "params": params or {}}))
        try:
            msg = q.get(timeout=timeout)
        except queue.Empty:
            self._pending.pop(cid, None)
            raise TimeoutError(f"the browser didn't answer {method} within {int(timeout)} s")
        if msg.get("type") == "error":
            if msg.get("error") == "closed":
                raise BrowserClosed("the browser window was closed")
            if msg.get("error") == "no such frame":
                self._ctx = None
                raise BrowserClosed("the browser tab was closed")
            raise RuntimeError(f"{method}: {msg.get('error')}: {msg.get('message', '')[:200]}")
        return msg.get("result") or {}

    def _top_context(self) -> str:
        contexts = self._cmd("browsingContext.getTree", {"maxDepth": 0}).get("contexts") or []
        if contexts:
            return contexts[0]["context"]
        return self._cmd("browsingContext.create", {"type": "tab"})["context"]

    def _ensure(self):
        if self._proc is None or self._proc.poll() is not None or self._closed.is_set():
            if self._proc is not None and not self.headless:
                self._cleanup()
                raise BrowserClosed("the browser window was closed")
            self._cleanup()
            self._start()
        if self._ctx is None:
            self._ctx = self._top_context()

    # ----- the interface
    def goto(self, url: str, timeout: float = 60.0):
        self._ensure()
        try:
            self._cmd("browsingContext.navigate", {"context": self._ctx, "url": url, "wait": "interactive"},
                      timeout=timeout)
        except TimeoutError:
            pass  # a slow page: carry on with what has loaded so far

    def evaluate(self, expression: str):
        self._ensure()
        r = self._cmd("script.evaluate", {
            "expression": f"(async () => JSON.stringify(await ({expression})))()",
            "target": {"context": self._ctx}, "awaitPromise": True, "resultOwnership": "none"}, timeout=60)
        if r.get("type") == "exception":
            details = r.get("exceptionDetails") or {}
            raise RuntimeError(f"page script failed: {details.get('text', '')[:200]}")
        value = (r.get("result") or {}).get("value")
        return json.loads(value) if isinstance(value, str) else None

    def cookies(self) -> list[dict]:
        self._ensure()
        out = []
        for c in self._cmd("storage.getCookies", {}).get("cookies") or []:
            v = c.get("value") or {}
            out.append({"name": c.get("name"), "value": v.get("value", "") if isinstance(v, dict) else str(v),
                        "domain": c.get("domain", ""), "path": c.get("path", "/"), "secure": bool(c.get("secure")),
                        "httpOnly": bool(c.get("httpOnly")), "expires": c.get("expiry")})
        return out

    def add_cookies(self, cookies: list[dict]):
        self._ensure()
        for c in cookies:
            cookie = {"name": c["name"], "value": {"type": "string", "value": c.get("value", "")},
                      "domain": c.get("domain", ""), "path": c.get("path") or "/",
                      "secure": bool(c.get("secure")), "httpOnly": bool(c.get("httpOnly")), "sameSite": "lax"}
            if c.get("expires"):
                cookie["expiry"] = int(c["expires"])
            try:
                self._cmd("storage.setCookie", {"cookie": cookie})
            except RuntimeError as e:
                log.info("couldn't set cookie %s for %s: %s", c.get("name"), c.get("domain"), e)

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None and not self._closed.is_set()

    def open_for_login(self, url: str):
        if self.headless or not self.is_running():
            self.close()
            self.headless = False
        self.goto(url)

    def _kill(self):
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.kill()
            except Exception:
                pass

    def _cleanup(self):
        try:
            if self._ws is not None:
                self._ws.close()
        except Exception:
            pass
        self._ws, self._ctx = None, None
        if self._proc is not None:
            try:
                self._proc.wait(10)
            except Exception:
                self._kill()
        self._proc = None

    def close(self):
        if self._ws is not None and not self._closed.is_set():
            try:
                self._cmd("browser.close", {}, timeout=10)
            except Exception:
                pass
        self._cleanup()


# ---------------------------------------------------------------- Edge / Chrome through Playwright
class EdgeBrowser(BaseBrowser):
    engine = "edge"

    def __init__(self, site_id: str, headless: bool = True):
        super().__init__(site_id, headless)
        self._pw = None
        self._ctx = None
        self._page = None

    def _start(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise BrowserUnavailable("the browser helper (playwright) is not installed") from e
        self._pw = sync_playwright().start()
        profile = config.BROWSER_PROFILE_DIR / self.site_id
        profile.mkdir(parents=True, exist_ok=True)
        attempts = []
        if os.environ.get("BOOKKEEPER_BROWSER"):
            attempts.append({"executable_path": os.environ["BOOKKEEPER_BROWSER"]})
        attempts += [{"channel": "msedge"}, {"channel": "chrome"}, {}]
        errors = []
        for opts in attempts:
            try:
                self._ctx = self._pw.chromium.launch_persistent_context(
                    str(profile), headless=self.headless, locale="ru-RU", **opts)
                self._apply_initial_cookies()
                return
            except Exception as e:  # this browser isn't installed: try the next one
                errors.append(f"{opts.get('channel') or opts.get('executable_path') or 'built-in'}: "
                              f"{str(e).splitlines()[0][:120]}")
        self._pw.stop()
        self._pw = None
        raise BrowserUnavailable("no usable browser found (tried Edge, Chrome and the built-in one): "
                                 + "; ".join(errors))

    def _page_obj(self):
        if self._ctx is None:
            self._start()
        if self._page is None or self._page.is_closed():
            try:
                self._page = self._ctx.new_page()
            except Exception as e:
                if not self.headless:
                    raise BrowserClosed("the browser window was closed") from e
                self.close()
                self._start()
                self._page = self._ctx.new_page()
        return self._page

    def goto(self, url: str, timeout: float = 60.0):
        page = self._page_obj()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        except Exception as e:
            if "closed" in str(e).lower():
                raise BrowserClosed("the browser window was closed") from e
            if "timeout" not in str(e).lower():
                raise

    def evaluate(self, expression: str):
        try:
            return self._page_obj().evaluate(f"async () => await ({expression})")
        except Exception as e:
            if "closed" in str(e).lower():
                raise BrowserClosed("the browser window was closed") from e
            raise

    def cookies(self) -> list[dict]:
        if self._ctx is None:
            self._start()
        return [{"name": c["name"], "value": c["value"], "domain": c["domain"], "path": c.get("path", "/"),
                 "secure": c.get("secure", False), "httpOnly": c.get("httpOnly", False),
                 "expires": c.get("expires") if (c.get("expires") or -1) > 0 else None}
                for c in self._ctx.cookies()]

    def add_cookies(self, cookies: list[dict]):
        if self._ctx is None:
            self._start()
        self._ctx.add_cookies([{"name": c["name"], "value": c.get("value", ""), "domain": c["domain"],
                                "path": c.get("path") or "/", "secure": bool(c.get("secure")),
                                "httpOnly": bool(c.get("httpOnly")),
                                **({"expires": float(c["expires"])} if c.get("expires") else {})} for c in cookies])

    def is_running(self) -> bool:
        return self._ctx is not None

    def close(self):
        try:
            if self._ctx is not None:
                self._ctx.close()
        except Exception:
            pass
        finally:
            self._ctx = None
            self._page = None
            if self._pw is not None:
                try:
                    self._pw.stop()
                except Exception:
                    pass
                self._pw = None


def Browser(site_id: str, headless: bool = True, engine: str | None = None) -> BaseBrowser:
    """A browser for `site_id`: Waterfox when it's installed (or chosen on the Sites page), else Edge / Chrome."""
    engine = engine or engine_choice()
    if engine == "waterfox":
        return WaterfoxBrowser(site_id, headless)
    return EdgeBrowser(site_id, headless)
