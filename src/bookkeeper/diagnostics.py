"""Site tests for the sites that don't have a connector yet.

Some sites block the server these connectors were developed on, so their connectors have to be written from
pages seen on your computer. A test visits a few pages of a site (home, catalog, one book, one chapter),
slowly, the way your browser would, and saves what it saw into data/diagnostics/<site>.zip.
Send that ZIP to whoever is writing the connector.

If a page shows a bot check, the test can open it in a normal, visible Waterfox window (Edge if Waterfox is not installed), so that you can
pass the check yourself, and saves the page once it has loaded."""
import json
import re
import threading
import zipfile
from datetime import datetime
from urllib.parse import urljoin

from . import __version__, config
from .http import Blocked, Http, looks_like_bot_check

# Each step opens `url`, or the first link matching `pattern` found on the page of step `from`.
STEPS: dict[str, list[dict]] = {
    "ficbook": [
        {"label": "home", "url": "https://ficbook.net/"},
        {"label": "catalog", "url": "https://ficbook.net/popular-fanfics-376846"},
        {"label": "book", "from": "catalog", "pattern": r'href="(/readfic/[^"#?]+)"'},
        {"label": "chapter", "from": "book", "pattern": r'href="(/readfic/[^"#?]+/\d+)[#"]'},
    ],
    "scribblehub": [
        {"label": "home", "url": "https://www.scribblehub.com/"},
        {"label": "catalog", "url": "https://www.scribblehub.com/series-ranking/?sort=1&order=1"},
        {"label": "book", "from": "catalog", "pattern": r'href="(https://www\.scribblehub\.com/series/\d+/[^"]+)"'},
        {"label": "chapter", "from": "book", "pattern": r'href="(https://www\.scribblehub\.com/read/[^"]+/chapter/\d+/?)"'},
    ],
    "webnovel": [
        {"label": "home", "url": "https://www.webnovel.com/"},
        {"label": "catalog", "url": "https://www.webnovel.com/stories/novel?orderBy=1"},
        {"label": "book", "from": "catalog", "pattern": r'href="(/(?:ru/)?book/[^"/]+_\d+)"'},
        {"label": "chapter", "from": "book", "pattern": r'href="(/(?:ru/)?book/[^"/]+_\d+/[^"/]+_\d+)"'},
    ],
    "fanfiction": [
        {"label": "home", "url": "https://www.fanfiction.net/"},
        {"label": "catalog", "url": "https://www.fanfiction.net/book/Harry-Potter/?&srt=1&r=10"},
        {"label": "book", "from": "catalog", "pattern": r'href="(/s/\d+/1/[^"]+)"'},
    ],
    "novelupdates": [
        {"label": "home", "url": "https://www.novelupdates.com/"},
        {"label": "catalog", "url": "https://www.novelupdates.com/series-ranking/?rank=popmonth"},
        {"label": "book", "from": "catalog", "pattern": r'href="(https://www\.novelupdates\.com/series/[^"]+/)"'},
    ],
    "royalroad": [
        {"label": "home", "url": "https://www.royalroad.com/"},
        {"label": "catalog", "url": "https://www.royalroad.com/fictions/best-rated"},
        {"label": "book", "from": "catalog", "pattern": r'href="(/fiction/\d+/[^"/]+)"'},
        {"label": "chapter", "from": "book", "pattern": r'href="(/fiction/\d+/[^"/]+/chapter/\d+/[^"]+)"'},
    ],
    "rulate": [
        {"label": "home", "url": "https://tl.rulate.ru/"},
        {"label": "catalog", "url": "https://tl.rulate.ru/search?t=&sort=4"},
        {"label": "book", "from": "catalog", "pattern": r'href="((?:https://tl\.rulate\.ru)?/book/\d+)"'},
        {"label": "chapter", "from": "book", "pattern": r'href="((?:https://tl\.rulate\.ru)?/book/\d+/\d+(?:/ready)?)"'},
    ],
    "royallib": [
        {"label": "home", "url": "https://royallib.com/"},
        {"label": "book", "from": "home", "pattern": r'href="((?:https:)?//royallib\.com/book/[^"]+\.html)"'},
    ],
    "ao3": [
        {"label": "home", "url": "https://archiveofourown.org/"},
        {"label": "catalog", "url": "https://archiveofourown.org/works/search?work_search%5Bquery%5D=%22first+person%22"},
        {"label": "book", "from": "catalog", "pattern": r'href="(/works/\d+)"'},
    ],
    "samlib": [
        {"label": "home", "url": "http://samlib.ru/"},
        {"label": "catalog", "url": "http://samlib.ru/rating/top40/"},
        {"label": "book", "from": "catalog", "pattern": r'href="(/[a-z]/[^"]+/[^"]+\.shtml)"'},
    ],
    "ranobehub": [
        {"label": "home", "url": "https://ranobehub.org/"},
        {"label": "book", "from": "home", "pattern": r'href="(/ranobe/\d+-[^"?]+)'},
    ],
    "ranobes": [
        {"label": "home", "url": "https://ranobes.com/"},
        {"label": "book", "from": "home", "pattern": r'href="(https://ranobes\.com/ranobe/[^"]+\.html)"'},
    ],
    "litmir": [
        {"label": "home", "url": "https://litmir.club/"},
        {"label": "book", "from": "home", "pattern": r'href="(/bd/\?b=\d+[^"]*)"'},
    ],
    "rulit": [
        {"label": "home", "url": "https://www.rulit.me/"},
        {"label": "book", "from": "home", "pattern": r'href="(https://www\.rulit\.me/books/[^"]+\.html)"'},
    ],
    "litvek": [
        {"label": "home", "url": "https://litvek.com/"},
        {"label": "book", "from": "home", "pattern": r'href="(/br/\d+[^"]*|/book-read/[^"]+)"'},
    ],
    "kubikus": [
        {"label": "home", "url": "https://www.kubikus.ru/"},
        {"label": "forum", "url": "https://www.kubikus.ru/forum/"},
        {"label": "topic", "from": "forum", "pattern": r'href="(\./viewtopic\.php\?[^"]+|viewtopic\.php\?[^"]+)"'},
    ],
}

_runs: dict[str, dict] = {}
_lock = threading.Lock()
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def status(site_id: str) -> dict | None:
    run = _runs.get(site_id)
    if run:
        return run
    path = config.DATA_DIR / "diagnostics" / f"{site_id}.zip"
    return {"state": "done", "zip": path.name, "summary": "Earlier test result saved."} if path.exists() else None


def start(site_id: str, allow_browser: bool = True) -> dict:
    if site_id not in STEPS:
        raise KeyError(site_id)
    with _lock:
        if _runs.get(site_id, {}).get("state") == "running":
            return _runs[site_id]
        _runs[site_id] = {"state": "running", "steps": [], "summary": "Starting…"}
    threading.Thread(target=_run, args=(site_id, allow_browser), name=f"test-{site_id}", daemon=True).start()
    return _runs[site_id]


def _run(site_id: str, allow_browser: bool):
    run = _runs[site_id]
    folder = config.DATA_DIR / "diagnostics" / site_id
    folder.mkdir(parents=True, exist_ok=True)
    http = Http(f"test-{site_id}", min_interval=3.0)
    pages: dict[str, tuple[str, str]] = {}  # label -> (url, html)
    browser = None
    try:
        for step in STEPS[site_id]:
            entry = {"label": step["label"], "url": None, "result": None}
            run["steps"].append(entry)
            url = step.get("url")
            if not url:
                base_url, base_html = pages.get(step["from"], (None, None))
                m = re.search(step["pattern"], base_html or "")
                if not m:
                    entry["result"] = f"no link found on the {step['from']} page"
                    continue
                url = urljoin(base_url, m.group(1).replace("&amp;", "&"))
            entry["url"] = url
            run["summary"] = f"Opening the {step['label']} page…"
            html, how = None, "plain request"
            try:
                p = http.get(url, retries=1, ok_status=(403, 404, 418, 429, 503))
                html = p.text
                reason = looks_like_bot_check(p.status, p.headers, p.content)
                entry["result"] = f"HTTP {p.status}" + (f", {reason}" if reason else "")
                entry["bot_check"] = bool(reason)
                if reason:
                    html = None
                elif p.status >= 400:
                    entry["bot_check"] = p.status in (403, 429, 503)
            except Blocked as e:
                entry["result"], entry["bot_check"] = str(e), True
            except Exception as e:  # network trouble, timeouts
                entry["result"] = f"{type(e).__name__}: {str(e)[:150]}"
            if html is None and entry.get("bot_check") and allow_browser:
                run["summary"] = (f"The {step['label']} page showed a bot check. Opening it in a browser window: "
                                  "if a check appears there, please complete it.")
                try:
                    if browser is None:
                        from .browser import Browser
                        browser = Browser(site_id, headless=False)
                    html = _browser_page(browser, url)
                    how = "browser window"
                    entry["result"] += "; opened fine in the browser" if html else "; the browser didn't get past it"
                except Exception as e:
                    entry["result"] += f"; browser failed: {type(e).__name__}: {str(e).splitlines()[0][:120]}"
            if html:
                pages[step["label"]] = (url, html)
                (folder / f"{len(pages):02d}-{step['label']}.html").write_text(html[:3_000_000], encoding="utf-8")
                t = _TITLE.search(html)
                entry["title"] = re.sub(r"\s+", " ", t.group(1)).strip()[:120] if t else None
                entry["via"] = how
        ok = sum(1 for s in run["steps"] if s.get("title"))
        blocked = any(s.get("bot_check") for s in run["steps"])
        report = {"site": site_id, "app_version": __version__, "when": datetime.now().isoformat(timespec="seconds"),
                  "steps": run["steps"]}
        (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        zip_path = config.DATA_DIR / "diagnostics" / f"{site_id}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(folder.iterdir()):
                z.write(f, f"{site_id}/{f.name}")
        run["zip"] = zip_path.name
        run["state"] = "done"
        run["summary"] = (f"Saved {ok} of {len(run['steps'])} pages"
                          + (" (the site showed a bot check to plain requests)" if blocked else "")
                          + ". Send the ZIP file to finish this site's connector.")
    except Exception as e:  # pragma: no cover - shown in the UI
        run["state"] = "error"
        run["summary"] = f"The test failed: {type(e).__name__}: {e}"
    finally:
        http.close()
        if browser:
            try:
                browser.close()
            except Exception:
                pass


def _browser_page(browser, url: str, wait_seconds: int = 120) -> str | None:
    """Open a page in a visible window and return its HTML once real content (not a check page) is showing."""
    from .browser import BrowserClosed
    try:
        return browser.page_html(url, wait_seconds)
    except BrowserClosed:
        raise RuntimeError("the browser window was closed before the check was completed. Keep it open until "
                           "the page has loaded")


def zip_file(site_id: str):
    path = config.DATA_DIR / "diagnostics" / f"{site_id}.zip"
    return path if path.exists() else None
