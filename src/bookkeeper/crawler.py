"""Background work: one worker thread per site, plus a housekeeping thread.

Each site worker repeats, in order of priority:
  1. downloads you asked for            (TXT / FB2 / EPUB)
  2. "analyse now" requests from the UI
  3. one page of the site's catalog     (new books)
  4. details for books we only know from the catalog (tags, description...), most popular first
  5. narration analysis of the opening chapters, most popular first
All requests to a site go through that site's polite HTTP client, so the pace is the same whatever it's doing."""
import logging
import threading
import time
import traceback

from . import db, library, matching
from .analysis.pov import analyse
from .browser import Browser, BrowserUnavailable
from .db import jdump, jload, now
from .http import Blocked, Http, NotFound, Stopped
from .sites import SITES
from .sites.base import TemporaryError

log = logging.getLogger("bookkeeper.crawler")


def _hours_ago(hours: float) -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

DEFAULTS = {"min_interval": None, "analyze": True, "include_adult": False, "details_per_cycle": 10,
            "analysis_per_cycle": 4, "pass_interval_hours": 12}


def site_settings(site_id: str) -> dict:
    row = db.conn().execute("SELECT settings FROM sites WHERE id=?", (site_id,)).fetchone()
    return {**DEFAULTS, **(jload(row["settings"], {}) if row else {})}


class SiteWorker(threading.Thread):
    def __init__(self, manager: "Manager", site_id: str):
        super().__init__(name=f"site-{site_id}", daemon=True)
        self.manager = manager
        self.site_id = site_id
        self.cls = SITES[site_id]
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.activity = "starting"
        self.http: Http | None = None
        self.site = None
        self.browser: Browser | None = None
        self.gen = None
        self.state: dict = {}
        self.browser_error: str | None = None

    # ---------- helpers ----------
    def _setup(self):
        s = site_settings(self.site_id)
        self.http = Http(self.site_id, min_interval=s["min_interval"] or self.cls.min_interval, stop=self.stop)
        self.browser = Browser(self.site_id) if self.cls.needs_browser_for_text else None
        self.site = self.cls(self.http, s, self.browser)
        row = db.conn().execute("SELECT state FROM sites WHERE id=?", (self.site_id,)).fetchone()
        self.state = jload(row["state"], {}) if row else {}

    def _save_state(self):
        db.conn().execute("UPDATE sites SET state=?, updated_at=? WHERE id=?",
                          (jdump(self.state), now(), self.site_id))

    def _status(self, status: str, msg: str | None = None):
        db.conn().execute("UPDATE sites SET status=?, status_msg=?, updated_at=? WHERE id=?",
                          (status, msg, now(), self.site_id))

    def _enabled(self) -> bool:
        row = db.conn().execute("SELECT enabled, status FROM sites WHERE id=?", (self.site_id,)).fetchone()
        return bool(row and row["enabled"] and row["status"] != "blocked")

    def _idle(self, seconds: float):
        self.wake.wait(seconds)
        self.wake.clear()

    # ---------- main loop ----------
    def run(self):
        try:
            self._setup()
        except Exception as e:  # pragma: no cover - shown on the Sites page
            self._status("error", f"could not start: {e}")
            return
        while not self.stop.is_set() and not self.manager.shutdown.is_set():
            try:
                did = self.cycle()
                if not did:
                    self.activity = "idle"
                    self._idle(30)
            except Stopped:
                break
            except Blocked as e:
                log.warning("%s blocked: %s", self.site_id, e)
                self._status("blocked", str(e))
                self.activity = "blocked"
                self.gen = None
                self._idle(60)
            except Exception as e:
                log.error("%s error: %s\n%s", self.site_id, e, traceback.format_exc())
                self._status("error", f"{type(e).__name__}: {e}")
                self.activity = "error, retrying in 5 minutes"
                self.gen = None
                self._idle(300)
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass

    def cycle(self) -> bool:
        if self._download_step():
            return True
        if self._queued_analysis_step():
            return True
        if not self._enabled():
            return False
        settings = site_settings(self.site_id)
        self._status("running")
        did = self._discovery_step(settings)
        did = self._details_step(settings) or did
        if settings["analyze"]:
            did = self._analysis_step(settings) or did
        return did

    # ---------- steps ----------
    def _discovery_step(self, settings) -> bool:
        if self.gen is None:
            last = self.state.get("last_pass_end")
            if last and self.state.get("full_done"):
                age_h = (time.time() - last) / 3600
                if age_h < settings["pass_interval_hours"]:
                    return False
            self.gen = self.site.discover(self.state)
        self.activity = "reading the catalog"
        try:
            batch = next(self.gen)
        except StopIteration:
            self.gen = None
            self.state["last_pass_end"] = time.time()
            self.state["passes"] = self.state.get("passes", 0) + 1
            self._save_state()
            self.manager.dirty.add(self.site_id)
            return True
        for info in batch:
            if info.adult and not settings["include_adult"]:
                continue
            library.upsert_book(self.site_id, info)
        self._save_state()
        self.manager.dirty.add(self.site_id)
        return True

    def _details_step(self, settings) -> bool:
        rows = db.conn().execute(
            "SELECT id, sid, extra FROM books WHERE site=? AND meta_at IS NULL "
            "ORDER BY pop_raw DESC NULLS LAST, id LIMIT ?", (self.site_id, settings["details_per_cycle"])).fetchall()
        if not rows:
            return False
        for r in rows:
            book = {"id": r["id"], "sid": r["sid"], "extra": jload(r["extra"], {})}
            self.activity = f"fetching details ({r['sid']})"
            try:
                info = self.site.details(book)
            except NotImplementedError:
                db.conn().execute("UPDATE books SET meta_at=? WHERE id=?", (now(), r["id"]))
                continue
            except NotFound:
                db.conn().execute("UPDATE books SET meta_at=? WHERE id=?", (now(), r["id"]))
                continue
            except (Blocked, Stopped):
                raise
            except Exception as e:
                log.warning("%s details %s failed: %s", self.site_id, r["sid"], e)
                db.conn().execute("UPDATE books SET meta_at=?, extra=json_set(extra, '$.details_error', ?) "
                                  "WHERE id=?", (now(), str(e)[:200], r["id"]))
                continue
            library.upsert_book(self.site_id, info, details=True)
        self.manager.dirty.add(self.site_id)
        return True

    def _analyse_book(self, row) -> None:
        book = {"id": row["id"], "sid": row["sid"], "extra": jload(row["extra"], {})}
        self.activity = f"analysing «{row['title'][:40]}»"
        try:
            texts = self.site.opening_text(book)
        except BrowserUnavailable as e:
            self.browser_error = str(e)
            raise
        except NotFound:
            library.save_analysis(row["id"], None, "not found")
            return
        except (Blocked, Stopped):
            raise
        except TemporaryError as e:
            log.info("%s: temporary problem reading %s: %s", self.site_id, row["sid"], e)
            library.save_analysis(row["id"], None, f"temporary: {e}")
            return
        except Exception as e:
            log.warning("%s: could not read %s: %s", self.site_id, row["sid"], e)
            library.save_analysis(row["id"], None, f"{type(e).__name__}: {str(e)[:200]}")
            return
        if not texts:
            library.save_analysis(row["id"], None, "no free text to read")
            return
        library.save_analysis(row["id"], analyse(texts))

    def _analysis_step(self, settings) -> bool:
        if self.browser_error:
            return False
        rows = db.conn().execute(
            "SELECT id, sid, title, extra FROM books WHERE site=? AND meta_at IS NOT NULL AND analyzed_at IS NULL "
            "AND (adult=0 OR ?) ORDER BY (pov_source='site') ASC, pop_raw DESC NULLS LAST, id LIMIT ?",
            (self.site_id, int(settings["include_adult"]), settings["analysis_per_cycle"])).fetchall()
        if not rows:  # retry books that hit a temporary problem, after a while, at most 3 times
            rows = db.conn().execute(
                "SELECT b.id, b.sid, b.title, b.extra FROM books b JOIN analysis a ON a.book_id=b.id "
                "WHERE b.site=? AND a.error LIKE 'temporary:%' AND a.attempts < 3 AND a.at < ? "
                "ORDER BY b.pop_raw DESC NULLS LAST LIMIT ?",
                (self.site_id, _hours_ago(6), settings["analysis_per_cycle"])).fetchall()
        if not rows:
            return False
        for r in rows:
            try:
                self._analyse_book(r)
            except BrowserUnavailable:
                self._status("running", f"narration analysis is off: {self.browser_error}")
                return True
        self.manager.dirty.add(self.site_id)
        return True

    def _queued_analysis_step(self) -> bool:
        row = db.conn().execute(
            "SELECT b.id, b.sid, b.title, b.extra, b.meta_at FROM queue q JOIN books b ON b.id=q.book_id "
            "WHERE b.site=? ORDER BY q.priority DESC, q.requested_at LIMIT 1", (self.site_id,)).fetchone()
        if not row:
            return False
        db.conn().execute("DELETE FROM queue WHERE book_id=?", (row["id"],))
        if row["meta_at"] is None:
            try:
                info = self.site.details({"id": row["id"], "sid": row["sid"], "extra": jload(row["extra"], {})})
                library.upsert_book(self.site_id, info, details=True)
            except (NotImplementedError, NotFound):
                pass
        if self.browser_error:
            library.save_analysis(row["id"], None, self.browser_error)
            return True
        try:
            self._analyse_book(row)
        except BrowserUnavailable:
            library.save_analysis(row["id"], None, self.browser_error)
        self.manager.dirty.add(self.site_id)
        return True

    def _download_step(self) -> bool:
        row = db.conn().execute(
            "SELECT d.* FROM downloads d JOIN books b ON b.id=d.book_id WHERE b.site=? AND d.state='queued' "
            "ORDER BY d.id LIMIT 1", (self.site_id,)).fetchone()
        if not row:
            return False
        from .export import run_download
        self.activity = "downloading a book"
        run_download(self, row)
        return True


class Manager:
    def __init__(self):
        self.shutdown = threading.Event()
        self.workers: dict[str, SiteWorker] = {}
        self.dirty: set[str] = set()
        self.last_match = 0.0
        self.matching_now = False
        self._housekeeper = threading.Thread(target=self._housekeeping, name="housekeeping", daemon=True)

    def start(self):
        c = db.conn()
        for site_id in SITES:
            c.execute("INSERT OR IGNORE INTO sites(id, enabled, updated_at) VALUES(?, 0, ?)", (site_id, now()))
            # A block from last time may be over: try again on start.
            c.execute("UPDATE sites SET status='idle' WHERE id=? AND status IN ('running','blocked','error')",
                      (site_id,))
            self._start_worker(site_id)
        self._housekeeper.start()

    def _start_worker(self, site_id: str):
        w = self.workers.get(site_id)
        if w and w.is_alive():
            return
        w = SiteWorker(self, site_id)
        self.workers[site_id] = w
        w.start()

    def poke(self, site_id: str | None = None):
        for sid, w in self.workers.items():
            if site_id is None or sid == site_id:
                w.wake.set()

    def set_enabled(self, site_id: str, enabled: bool):
        db.conn().execute("UPDATE sites SET enabled=?, status=CASE WHEN ? THEN 'idle' ELSE 'paused' END "
                          "WHERE id=?", (int(enabled), int(enabled), site_id))
        self.poke(site_id)

    def retry(self, site_id: str):
        db.conn().execute("UPDATE sites SET status='idle', status_msg=NULL WHERE id=?", (site_id,))
        w = self.workers.get(site_id)
        if w:
            w.browser_error = None
        self.poke(site_id)

    def update_settings(self, site_id: str, values: dict):
        current = jload(db.conn().execute("SELECT settings FROM sites WHERE id=?", (site_id,)).fetchone()["settings"], {})
        current.update({k: v for k, v in values.items() if k in DEFAULTS})
        db.conn().execute("UPDATE sites SET settings=? WHERE id=?", (jdump(current), site_id))
        w = self.workers.get(site_id)
        if w and w.http and values.get("min_interval"):
            w.http.min_interval = float(values["min_interval"])
        if w and w.site:
            w.site.settings.update(current)

    def run_matching(self):
        if self.matching_now:
            return
        self.matching_now = True
        try:
            matching.find_duplicates()
            library.refresh_tag_counts()
            self.last_match = time.time()
        finally:
            self.matching_now = False

    def _housekeeping(self):
        last_counts = 0.0
        while not self.shutdown.wait(20):
            try:
                if self.dirty and time.time() - last_counts > 120:
                    sites, self.dirty = set(self.dirty), set()
                    for s in sites:
                        library.recompute_popularity(s)
                    library.refresh_tag_counts()
                    last_counts = time.time()
                if time.time() - self.last_match > 1800:
                    self.run_matching()
            except Exception as e:  # never let housekeeping die
                log.error("housekeeping: %s\n%s", e, traceback.format_exc())

    def stop(self):
        self.shutdown.set()
        for w in self.workers.values():
            w.stop.set()
            w.wake.set()

    def status(self) -> dict:
        return {sid: {"activity": w.activity, "alive": w.is_alive(), "browser_error": w.browser_error,
                      "requests": w.http.requests if w.http else 0}
                for sid, w in self.workers.items()}
