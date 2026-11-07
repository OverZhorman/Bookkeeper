"""A polite HTTP client: one per site, with a minimum pause between requests, retries with backoff,
and recognition of bot-check pages so we stop instead of hammering a site that doesn't want us."""
import json
import random
import re
import threading
import time

import httpx

from .config import USER_AGENT


class Blocked(Exception):
    """The site answered with a bot check, an IP block or a login wall."""


class NotFound(Exception):
    pass


class Stopped(Exception):
    """The user paused this site (or the app is shutting down)."""


_META_CHARSET = re.compile(rb"""<meta[^>]+charset=["']?([\w-]+)""", re.I)


def decode_bytes(content: bytes, content_type: str = "", forced: str | None = None) -> str:
    """Bytes to text: forced encoding, else HTTP header, else <meta charset>, else UTF-8, else Windows-1251."""
    if forced:
        return content.decode(forced, "replace")
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    enc = m.group(1) if m else None
    if not enc:
        m2 = _META_CHARSET.search(content[:4096])
        enc = m2.group(1).decode("ascii", "ignore") if m2 else None
    if enc:
        try:
            return content.decode(enc, "replace")
        except LookupError:
            pass
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("cp1251", "replace")


class Page:
    def __init__(self, url: str, status: int, headers: httpx.Headers, content: bytes, encoding: str | None = None):
        self.url = url
        self.status = status
        self.headers = headers
        self.content = content
        self._encoding = encoding
        self._text: str | None = None

    @property
    def text(self) -> str:
        if self._text is None:
            self._text = decode_bytes(self.content, self.headers.get("content-type", ""), self._encoding)
        return self._text

    def json(self):
        return json.loads(self.text)


CHALLENGE_TEXT = (
    "Just a moment...", "Checking your browser", "cf-chl-", "challenge-platform",
    "ddos-guard/js-challenge", "Проверка браузера", "DDoS-Guard is not available",
    "Request temporarily denied",
)


def looks_like_bot_check(status: int, headers: httpx.Headers, body: bytes) -> str | None:
    if headers.get("cf-mitigated") == "challenge":
        return "Cloudflare bot check"
    if status in (403, 429, 503, 418):
        head = body[:20000].decode("utf-8", "ignore")
        for marker in CHALLENGE_TEXT:
            if marker in head:
                if "ddos" in marker.lower() or "DDoS" in head:
                    return "DDoS-Guard block"
                return "bot check"
        if status == 403 and "ddos-guard" in headers.get("server", "").lower():
            return "DDoS-Guard block"
    return None


class Http:
    def __init__(self, site_id: str, min_interval: float = 1.0, headers: dict | None = None,
                 cookies: dict | None = None, timeout: float = 40.0, stop: threading.Event | None = None):
        self.site_id = site_id
        self.min_interval = min_interval
        self.stop = stop or threading.Event()
        base_headers = {
            "User-Agent": USER_AGENT,
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
        }
        base_headers.update(headers or {})
        self.client = httpx.Client(headers=base_headers, cookies=cookies, follow_redirects=True,
                                   timeout=httpx.Timeout(timeout, connect=20.0))
        self._lock = threading.Lock()
        self._next_at = 0.0
        self.requests = 0

    def close(self):
        self.client.close()

    def _sleep(self, seconds: float):
        if self.stop.wait(max(0.0, seconds)):
            raise Stopped()

    def _pace(self):
        with self._lock:
            now = time.monotonic()
            wait = self._next_at - now
            self._next_at = max(now, self._next_at) + self.min_interval * (1 + random.random() * 0.25)
        if wait > 0:
            self._sleep(wait)
        if self.stop.is_set():
            raise Stopped()

    def request(self, method: str, url: str, *, params=None, data=None, json_body=None, headers=None,
                encoding: str | None = None, max_bytes: int | None = None, retries: int = 3,
                ok_status: tuple = ()) -> Page:
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            self._pace()
            self.requests += 1
            try:
                with self.client.stream(method, url, params=params, data=data, json=json_body,
                                        headers=headers) as r:
                    chunks, size = [], 0
                    for chunk in r.iter_bytes():
                        chunks.append(chunk)
                        size += len(chunk)
                        if max_bytes and size >= max_bytes:
                            break
                    body = b"".join(chunks)
                    status, resp_headers, final_url = r.status_code, r.headers, str(r.url)
            except httpx.HTTPError as e:  # network trouble: back off and retry
                last_error = e
                self._sleep(min(60, 3 * 2 ** attempt))
                continue

            reason = looks_like_bot_check(status, resp_headers, body)
            if reason:
                raise Blocked(f"{reason} (HTTP {status})")
            if status in ok_status or 200 <= status < 300:
                return Page(final_url, status, resp_headers, body, encoding)
            if status == 404 or status == 410:
                raise NotFound(url)
            if status == 429 or status >= 500:
                retry_after = resp_headers.get("retry-after", "")
                delay = float(retry_after) if retry_after.isdigit() else min(120, 5 * 2 ** attempt)
                last_error = httpx.HTTPStatusError(f"HTTP {status}", request=None, response=None)
                if attempt < retries:
                    self._sleep(delay)
                    continue
                if status == 429:
                    raise Blocked("rate limited (HTTP 429)")
            if status in (401, 403):
                raise Blocked(f"access denied (HTTP {status})")
            raise httpx.HTTPStatusError(f"HTTP {status} for {url}", request=None, response=None)
        raise last_error or RuntimeError("request failed")

    def get(self, url: str, **kw) -> Page:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw) -> Page:
        return self.request("POST", url, **kw)

    def get_json(self, url: str, **kw):
        return self.get(url, **kw).json()
