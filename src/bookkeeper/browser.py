"""A real browser for sites whose chapter text only appears inside a browser (Author.Today scrambles the text in
transit and its own reader unscrambles it on screen; we read the screen text, the same way you would).

On Windows this uses the Microsoft Edge that is already installed, so nothing extra is downloaded.
Each site gets its own browser profile in data/browser-profile/<site>, so a login you make there is remembered.
A Browser must only be used from the thread that created it."""
import os

from . import config


class BrowserUnavailable(Exception):
    pass


class Browser:
    def __init__(self, site_id: str, headless: bool = True):
        self.site_id = site_id
        self.headless = headless
        self._pw = None
        self._ctx = None

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
                return
            except Exception as e:  # this browser isn't installed: try the next one
                errors.append(f"{opts.get('channel') or opts.get('executable_path') or 'built-in'}: "
                              f"{str(e).splitlines()[0][:120]}")
        self._pw.stop()
        self._pw = None
        raise BrowserUnavailable("no usable browser found (tried Edge, Chrome and the built-in one): "
                                 + "; ".join(errors))

    def text(self, url: str, selector: str, min_chars: int = 200, timeout: float = 40.0,
             locked_pattern: str | None = None) -> str | None:
        """Open a page and return the visible text of `selector` once it has at least `min_chars` characters.
        Returns None straight away if visible page text matches `locked_pattern` (a paywall or login notice)."""
        if self._ctx is None:
            self._start()
        page = self._ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            handle = page.wait_for_function(
                """([sel, n, locked]) => {
                    const el = document.querySelector(sel);
                    if (el && el.innerText.trim().length > n) return "text";
                    if (locked && document.body && new RegExp(locked, "i").test(document.body.innerText)) return "locked";
                    return false;
                }""",
                arg=[selector, min_chars, locked_pattern], timeout=timeout * 1000, polling=500)
            if handle.json_value() == "locked":
                return None
            return page.inner_text(selector)
        finally:
            page.close()

    def open_for_login(self, url: str):
        """Show a visible window so you can log in; the session is kept in this site's profile."""
        self.close()
        self.headless = False
        self._start()
        page = self._ctx.new_page()
        page.goto(url)
        return page

    def close(self):
        try:
            if self._ctx is not None:
                self._ctx.close()
        finally:
            self._ctx = None
            if self._pw is not None:
                self._pw.stop()
                self._pw = None
