"""The local web server behind the interface (only reachable from your own computer)."""
import threading
from pathlib import Path

import httpx
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .. import __version__, config, db, export, library, search
from .. import tags as T
from ..config import USER_AGENT
from ..crawler import DEFAULTS, Manager, site_settings
from ..db import jload, now
from ..sites import PLANNED, SITES

STATIC = Path(__file__).parent / "static"


def create_app(manager: Manager) -> FastAPI:
    app = FastAPI(title="Bookkeeper", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    cover_lock = threading.Semaphore(4)
    cover_client = httpx.Client(headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=20)

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    # ---------- library ----------
    @app.get("/api/books")
    def books(request: Request):
        return search.search(dict(request.query_params))

    @app.get("/api/books/{book_id}")
    def book(book_id: int):
        d = search.book_detail(book_id)
        if not d:
            raise HTTPException(404)
        return d

    @app.post("/api/books/{book_id}/user")
    def book_user(book_id: int, body: dict = Body(...)):
        fields = {}
        if "shelf" in body:
            fields["shelf"] = body["shelf"] or None
        if "favorite" in body:
            fields["favorite"] = int(bool(body["favorite"]))
        if "pov" in body:
            fields["pov"] = body["pov"] or None
        if "note" in body:
            fields["note"] = body["note"]
        library.set_user(book_id, **fields)
        return search.book_detail(book_id)

    @app.post("/api/books/{book_id}/tags")
    def book_tags(book_id: int, body: dict = Body(...)):
        library.set_user_tags(book_id, [str(t) for t in body.get("tags", [])])
        return search.book_detail(book_id)

    @app.post("/api/analyze")
    def analyze(body: dict = Body(...)):
        ids = [int(x) for x in body.get("ids", [])][:500]
        c = db.conn()
        for i in ids:
            c.execute("INSERT OR REPLACE INTO queue(book_id, priority, requested_at) VALUES(?,?,?)",
                      (i, int(body.get("priority", 10)), now()))
            if body.get("force"):
                c.execute("UPDATE books SET analyzed_at=NULL WHERE id=?", (i,))
        manager.poke()
        return {"queued": len(ids)}

    @app.get("/api/tags")
    def tag_list(q: str = "", limit: int = 20):
        return search.tag_suggestions(q, min(limit, 100))

    @app.get("/api/tags/{tag_id}")
    def tag_one(tag_id: str):
        row = db.conn().execute("SELECT * FROM tags WHERE id=?", (tag_id,)).fetchone()
        return dict(row) if row else {"id": tag_id, **T.info(tag_id), "books": 0}

    # ---------- sites ----------
    @app.get("/api/sites")
    def sites():
        c = db.conn()
        counts = {r["site"]: dict(r) for r in c.execute(
            "SELECT site, COUNT(*) AS books, SUM(meta_at IS NOT NULL) AS detailed, "
            "SUM(analyzed_at IS NOT NULL) AS analyzed, SUM(pov='first') AS first_person, "
            "SUM(pov IS NOT NULL AND pov != 'unsure') AS with_pov FROM books GROUP BY site")}
        live = manager.status()
        out = []
        for sid, cls in SITES.items():
            row = c.execute("SELECT * FROM sites WHERE id=?", (sid,)).fetchone()
            state = jload(row["state"], {}) if row else {}
            out.append({
                "id": sid, "name": cls.name, "home": cls.home, "note": cls.note, "implemented": True,
                "needs_browser": cls.needs_browser_for_text,
                "enabled": bool(row and row["enabled"]), "status": row["status"] if row else "idle",
                "status_msg": row["status_msg"] if row else None,
                "settings": site_settings(sid), "default_interval": cls.min_interval,
                "full_done": bool(state.get("full_done")), "passes": state.get("passes", 0),
                "counts": counts.get(sid, {"books": 0, "detailed": 0, "analyzed": 0, "first_person": 0,
                                           "with_pov": 0}),
                "live": live.get(sid, {}),
            })
        return {"sites": out, "planned": PLANNED}

    @app.post("/api/sites/{site_id}")
    def site_update(site_id: str, body: dict = Body(...)):
        if site_id not in SITES:
            raise HTTPException(404)
        if "enabled" in body:
            manager.set_enabled(site_id, bool(body["enabled"]))
        settings = {k: v for k, v in body.items() if k in DEFAULTS}
        if settings:
            manager.update_settings(site_id, settings)
        return {"ok": True}

    @app.post("/api/sites/{site_id}/retry")
    def site_retry(site_id: str):
        manager.retry(site_id)
        return {"ok": True}

    # ---------- downloads ----------
    @app.post("/api/downloads")
    def download_new(body: dict = Body(...)):
        job = export.queue_download(int(body["book_id"]), body.get("fmt", "epub"),
                                    {k: body[k] for k in ("from", "to", "rebuild") if body.get(k)})
        row = db.conn().execute("SELECT site FROM books WHERE id=?", (int(body["book_id"]),)).fetchone()
        if row:
            manager.poke(row["site"])
        return {"id": job}

    @app.get("/api/downloads")
    def download_list():
        rows = db.conn().execute(
            "SELECT d.*, b.title, b.site FROM downloads d JOIN books b ON b.id=d.book_id ORDER BY d.id DESC LIMIT 200")
        return [{**dict(r), "options": jload(r["options"], {})} for r in rows]

    @app.get("/api/downloads/{job_id}/file")
    def download_file(job_id: int):
        p = export.file_path(job_id)
        if not p:
            raise HTTPException(404)
        return FileResponse(p, filename=p.name)

    @app.delete("/api/downloads/{job_id}")
    def download_delete(job_id: int):
        p = export.file_path(job_id)
        db.conn().execute("DELETE FROM downloads WHERE id=?", (job_id,))
        if p and p.exists():
            p.unlink()
        return {"ok": True}

    # ---------- saved searches ----------
    @app.get("/api/searches")
    def searches():
        return [dict(r) for r in db.conn().execute("SELECT * FROM saved_searches ORDER BY name")]

    @app.post("/api/searches")
    def search_save(body: dict = Body(...)):
        cur = db.conn().execute("INSERT INTO saved_searches(name, query, created_at) VALUES(?,?,?)",
                                (body["name"][:100], body["query"], now()))
        return {"id": cur.lastrowid}

    @app.delete("/api/searches/{sid}")
    def search_delete(sid: int):
        db.conn().execute("DELETE FROM saved_searches WHERE id=?", (sid,))
        return {"ok": True}

    # ---------- covers (cached on disk, so they also work offline) ----------
    @app.get("/api/cover/{book_id}")
    def cover(book_id: int):
        row = db.conn().execute("SELECT cover, site FROM books WHERE id=?", (book_id,)).fetchone()
        if not row or not row["cover"]:
            raise HTTPException(404)
        path = export.cover_cache_path(row["cover"])
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            home = SITES[row["site"]].home if row["site"] in SITES else ""
            with cover_lock:
                try:
                    r = cover_client.get(row["cover"], headers={"Referer": home + "/"})
                except httpx.HTTPError:
                    raise HTTPException(404)
            if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
                raise HTTPException(404)
            path.write_bytes(r.content)
        data = path.read_bytes()
        return Response(data, media_type=export._image_mime(data), headers={"Cache-Control": "max-age=2592000"})

    # ---------- app ----------
    @app.get("/api/meta")
    def meta():
        c = db.conn()
        totals = dict(c.execute("SELECT COUNT(*) AS books, SUM(pov='first') AS first_person, "
                                "SUM(analyzed_at IS NOT NULL) AS analyzed FROM books").fetchone())
        return {
            "version": __version__, "data_dir": str(config.DATA_DIR), "downloads_dir": str(config.DOWNLOADS_DIR),
            "user_tags_file": str(config.USER_TAGS_FILE), "totals": totals,
            "sites": {sid: {"name": cls.name, "home": cls.home} for sid, cls in SITES.items()},
            "categories": T.CATEGORY_ORDER,
            "matching": manager.matching_now,
        }

    @app.post("/api/maintenance/{task}")
    def maintenance(task: str):
        if task == "match":
            threading.Thread(target=manager.run_matching, daemon=True).start()
        elif task == "retag":
            threading.Thread(target=library.reapply_all_tags, daemon=True).start()
        else:
            raise HTTPException(404)
        return {"started": task}

    @app.exception_handler(Exception)
    def on_error(_request, exc):  # pragma: no cover
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=500)

    return app
