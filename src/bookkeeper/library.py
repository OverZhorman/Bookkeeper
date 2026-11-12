"""Saving books, tags and analysis results, and deciding each book's narration."""
from . import db, matching
from . import tags as T
from .db import jdump, jload, now
from .sites.base import BookInfo

POV_TAG_IDS = tuple(T.POV_TAGS)
_existing_tags: set[str] = set()


def _dedupe(items, exclude=None):
    seen, out = {(exclude or "").strip().lower()}, []
    for x in items or []:
        x = (x or "").strip()
        if x and x.lower() not in seen:
            seen.add(x.lower())
            out.append(x)
    return out


def upsert_book(site: str, info: BookInfo, details: bool = False) -> int:
    """Insert or update a book. details=True records that the full-details step is done."""
    authors = _dedupe(info.authors)
    vals = {
        "url": info.url, "title": (info.title or "").strip() or "(untitled)",
        "alt_titles": jdump(_dedupe(info.alt_titles, exclude=info.title)),
        "authors": jdump(authors), "author_sort": authors[0] if authors else None,
        "description": info.description, "cover": info.cover, "lang": info.lang, "status": info.status,
        "is_translation": None if info.is_translation is None else int(info.is_translation),
        "origin": info.origin, "chapters": info.chapters, "words": info.words, "rating": info.rating,
        "votes": info.votes, "views": info.views, "likes": info.likes, "pop_raw": info.pop_raw,
        "adult": int(bool(info.adult)), "access": info.access, "created_at": info.created_at,
        "updated_at": info.updated_at, "age_rating": normalize_age(info.age_rating),
    }
    if info.add_tags:
        return _add_labels(site, info)
    with db.transaction() as c:
        row = c.execute("SELECT id, extra, meta_at FROM books WHERE site=? AND sid=?", (site, info.sid)).fetchone()
        replace_tags = info.tags is not None and not (info.partial_tags and row and row["meta_at"])
        if row:
            book_id = row["id"]
            # A listing page knows less than a details page: don't overwrite known values with blanks.
            sets = {k: v for k, v in vals.items() if v is not None and v != "[]"}
            if not info.adult:
                sets.pop("adult", None)
            if info.extra:
                sets["extra"] = jdump({**jload(row["extra"], {}), **info.extra})
            if details or info.complete:
                sets["meta_at"] = now()
            if sets:
                c.execute(f"UPDATE books SET {', '.join(f'{k}=?' for k in sets)} WHERE id=?",
                          [*sets.values(), book_id])
        else:
            vals.update(site=site, sid=info.sid, added_at=now(), extra=jdump(info.extra or {}), labels="[]",
                        meta_at=now() if (details or info.complete) else None)
            cols = list(vals)
            cur = c.execute(f"INSERT INTO books({', '.join(cols)}) VALUES({', '.join('?' for _ in cols)})",
                            list(vals.values()))
            book_id = cur.lastrowid
        if replace_tags:
            _set_site_labels(c, book_id, info.tags)
        _refresh_rules(c, book_id)
        _drop_confirmed_maybes(c, book_id)
        _recompute_pov(c, book_id)
        b = c.execute("SELECT title, alt_titles, authors, is_translation FROM books WHERE id=?", (book_id,)).fetchone()
        matching.update_keys(c, book_id, site, b["title"], jload(b["alt_titles"], []), jload(b["authors"], []),
                             bool(b["is_translation"]))
    return book_id


AGE_RATINGS = ("G", "PG-13", "R", "NC-17", "NC-21")
_AGE_ALIASES = {"0+": "G", "6+": "G", "G": "G", "PG": "PG-13", "12+": "PG-13", "13+": "PG-13", "PG-13": "PG-13",
                "16+": "R", "R": "R", "R-15": "R", "17+": "NC-17", "18+": "NC-17", "R18": "NC-17", "R-18": "NC-17",
                "NC-17": "NC-17", "21+": "NC-21", "NC-21": "NC-21"}


def normalize_age(value) -> str | None:
    """A site's age label ("16+", "NC-17", "R18"…) as one of G / PG-13 / R / NC-17 / NC-21."""
    if value in (None, ""):
        return None
    return _AGE_ALIASES.get(str(value).strip().upper().replace(" ", ""))


def _ensure_tag(c, tag: str, raw: str | None):
    if tag in _existing_tags:
        return
    known = T.is_known(tag)
    i = T.info(tag)
    label = i["label"] if known else (raw or tag).strip()
    if tag.startswith(T.FANDOM_PREFIX) and label.lower().startswith(T.FANDOM_PREFIX):
        label = label[len(T.FANDOM_PREFIX):].strip()
    c.execute("INSERT OR IGNORE INTO tags(id, label, label_ru, label_uk, category, known) VALUES(?,?,?,?,?,?)",
              (tag, label, i.get("label_ru"), i.get("label_uk"), i.get("category") or "other", int(known)))
    _existing_tags.add(tag)


def _replace_tags(c, book_id: int, source: str, pairs):
    c.execute("DELETE FROM book_tags WHERE book_id=? AND source=?", (book_id, source))
    seen = set()
    for tag, raw in pairs:
        if not tag or tag in seen:
            continue
        seen.add(tag)
        _ensure_tag(c, tag, raw)
        c.execute("INSERT OR IGNORE INTO book_tags(book_id, tag, source, raw) VALUES(?,?,?,?)",
                  (book_id, tag, source, raw))


def _add_labels(site: str, info: BookInfo) -> int | None:
    """More site labels for a book that's listed already (Flibusta's genre pages); others are left alone."""
    with db.transaction() as c:
        row = c.execute("SELECT id FROM books WHERE site=? AND sid=?", (site, info.sid)).fetchone()
        if not row:
            return None
        book_id = row["id"]
        have = _site_labels(c, book_id)
        new = [t for t in info.tags or [] if t and t.strip() and t.strip() not in have]
        if new:
            _set_site_labels(c, book_id, have + new)
            _refresh_rules(c, book_id)
            _drop_confirmed_maybes(c, book_id)
            _recompute_pov(c, book_id)
    return book_id


def _site_labels(c, book_id: int) -> list[str]:
    """The labels the site gave a book, exactly as written (also ones you hid, which map to no tag)."""
    row = c.execute("SELECT labels FROM books WHERE id=?", (book_id,)).fetchone()
    labels = jload(row[0]) if row else None
    if labels is None:  # saved before 0.4.1 and not filled in yet
        labels = [r[0] for r in c.execute("SELECT DISTINCT raw FROM book_tags WHERE book_id=? AND source='site' "
                                          "AND raw IS NOT NULL", (book_id,))]
    return labels


def _set_site_labels(c, book_id: int, raws) -> None:
    """Keep a book's site labels as written and map them onto tags. Keeping them means a label fix can always be
    undone, even for a label that was hidden or that shares a tag with another label of the book."""
    raws = list(dict.fromkeys(r.strip() for r in raws or [] if r and r.strip()))
    c.execute("UPDATE books SET labels=? WHERE id=?", (jdump(raws), book_id))
    _replace_tags(c, book_id, "site", [(t, raw) for raw in raws for t in T.canonical(raw)])


def retag_books(book_ids, labels: bool = True) -> set[str]:
    """Map these books' site labels again (after a label fix), with their copies on other sites, and update the tag
    counts. labels=False only works out the rules again (after a parent or child link changed). Returns the tags
    that changed."""
    ids, touched = sorted(set(book_ids)), set()

    def tags_of(c, chunk):
        q = ",".join("?" * len(chunk))
        return {r[0] for r in c.execute(f"SELECT DISTINCT tag FROM book_tags WHERE book_id IN ({q})", chunk)}
    for i in range(0, len(ids), 200):  # small transactions, so the collectors aren't kept waiting
        chunk = ids[i:i + 200]
        with db.transaction() as c:
            touched |= tags_of(c, chunk)
            for book_id in chunk:
                if labels:
                    _set_site_labels(c, book_id, _site_labels(c, book_id))
                _refresh_rules(c, book_id)
                _drop_confirmed_maybes(c, book_id)
                _recompute_pov(c, book_id)
            touched |= tags_of(c, chunk)
    works = set()
    for i in range(0, len(ids) if labels else 0, 500):
        chunk = ids[i:i + 500]
        works |= {r[0] for r in db.conn().execute(
            f"SELECT DISTINCT work_id FROM books WHERE work_id IS NOT NULL AND id IN ({','.join('?' * len(chunk))})",
            chunk)}
    for work_id in works:
        with db.transaction() as c:
            members = [r[0] for r in c.execute("SELECT id FROM books WHERE work_id=?", (work_id,))]
            touched |= tags_of(c, members)
            matching.share_tags(c, members)
            touched |= tags_of(c, members)
    touched_list = sorted(touched)
    with db.transaction() as c:
        for i in range(0, len(touched_list), 500):
            chunk = touched_list[i:i + 500]
            q = ",".join("?" * len(chunk))
            c.execute(f"UPDATE tags SET books = (SELECT COUNT(DISTINCT book_id) FROM book_tags WHERE tag = tags.id "
                      f"AND source != 'maybe') WHERE id IN ({q})", chunk)
            # one-off site labels no book has any more
            c.execute(f"DELETE FROM tags WHERE id IN ({q}) AND known = 0 AND category = 'other' "
                      f"AND NOT EXISTS (SELECT 1 FROM book_tags WHERE tag = tags.id)", chunk)
    _existing_tags.clear()
    return touched


def refresh_rules_for(tag_ids) -> None:
    """After a parent or child link changed: work out the implied tags again for every book with these tags."""
    c = db.conn()
    books = set()
    for tag in set(tag_ids):
        books |= {r[0] for r in c.execute("SELECT DISTINCT book_id FROM book_tags WHERE tag=?", (tag,))}
    if books:
        retag_books(books, labels=False)


def sync_tag_rows(tag_ids) -> None:
    """Bring the tags table in line with the tag list (names, category, shared or not) after an edit."""
    with db.transaction() as c:
        for tid in set(tag_ids):
            i, known = T.info(tid), T.is_known(tid)
            cat = i.get("category") or ("fandom" if tid.startswith(T.FANDOM_PREFIX) else "other")
            if known:
                c.execute("INSERT INTO tags(id, label, label_ru, label_uk, category, known) VALUES(?,?,?,?,?,1) "
                          "ON CONFLICT(id) DO UPDATE SET label=excluded.label, label_ru=excluded.label_ru, "
                          "label_uk=excluded.label_uk, category=excluded.category, known=1",
                          (tid, i["label"], i.get("label_ru"), i.get("label_uk"), cat))
            else:  # no longer a shared tag: back to the label as the site wrote it
                raw = c.execute("SELECT raw FROM book_tags WHERE tag=? AND raw IS NOT NULL LIMIT 1", (tid,)).fetchone()
                c.execute("UPDATE tags SET label=?, label_ru=NULL, label_uk=NULL, category=?, known=0 WHERE id=?",
                          (raw[0] if raw else i["label"], cat, tid))
    _existing_tags.clear()


def _replace_maybe_tags(c, book_id: int, found: list[dict]):
    """Possible tags from the opening chapters, except ones the book already has for certain."""
    c.execute("DELETE FROM book_tags WHERE book_id=? AND source='maybe'", (book_id,))
    have = {r[0] for r in c.execute("SELECT DISTINCT tag FROM book_tags WHERE book_id=?", (book_id,))}
    for item in found:
        if item["tag"] in have:
            continue
        _ensure_tag(c, item["tag"], None)
        c.execute("INSERT OR IGNORE INTO book_tags(book_id, tag, source, raw, score) VALUES(?,?,?,?,?)",
                  (book_id, item["tag"], "maybe", f"{item['per_10k']} per 10,000 words", item["score"]))


def _drop_confirmed_maybes(c, book_id: int | None = None):
    """A possible tag that the book now has for certain isn't 'possible' any more."""
    c.execute("DELETE FROM book_tags WHERE source='maybe' " + ("AND book_id=? " if book_id else "") +
              "AND EXISTS(SELECT 1 FROM book_tags x WHERE x.book_id=book_tags.book_id AND x.tag=book_tags.tag "
              "AND x.source!='maybe')", (book_id,) if book_id else ())


def _refresh_rules(c, book_id: int):
    have = {r[0] for r in c.execute("SELECT DISTINCT tag FROM book_tags WHERE book_id=? AND "
                                    "source NOT IN ('rule','maybe')", (book_id,))}
    _replace_tags(c, book_id, "rule", [(t, None) for t in T.implied(have)])


def _recompute_pov(c, book_id: int):
    """Your correction > the site's own tag > text analysis > a copy on another site."""
    pov = src = None
    user = c.execute("SELECT pov FROM user_books WHERE book_id=?", (book_id,)).fetchone()
    analysis = c.execute("SELECT pov, narrator FROM analysis WHERE book_id=?", (book_id,)).fetchone()
    if user and user["pov"]:
        pov, src = user["pov"], "user"
    else:
        q = f"SELECT DISTINCT tag FROM book_tags WHERE book_id=? AND source=? AND tag IN ({','.join('?' * len(POV_TAG_IDS))})"
        site_povs = {T.POV_TAGS[r[0]] for r in c.execute(q, (book_id, "site", *POV_TAG_IDS))}
        if site_povs:
            pov, src = (site_povs.pop() if len(site_povs) == 1 else "mixed"), "site"
        elif analysis and analysis["pov"] in ("first", "third", "second", "mixed"):
            pov, src = analysis["pov"], "text"
        else:
            other = {T.POV_TAGS[r[0]] for r in c.execute(q, (book_id, "other-site", *POV_TAG_IDS))}
            if other:
                pov, src = (other.pop() if len(other) == 1 else "mixed"), "other-site"
            elif analysis and analysis["pov"] == "unsure":
                pov, src = "unsure", "text"
    narrator = analysis["narrator"] if analysis and pov in ("first", "mixed") else None
    c.execute("UPDATE books SET pov=?, pov_source=?, narrator=? WHERE id=?", (pov, src, narrator, book_id))


def save_analysis(book_id: int, result: dict | None, error: str | None = None):
    from .analysis.pov import VERSION
    from .analysis.themes import VERSION as THEMES_VERSION
    with db.transaction() as c:
        if result is None:
            c.execute(
                "INSERT INTO analysis(book_id, error, version, at, attempts) VALUES(?,?,?,?,1) "
                "ON CONFLICT(book_id) DO UPDATE SET error=excluded.error, version=excluded.version, at=excluded.at, "
                "attempts=analysis.attempts+1",
                (book_id, error, VERSION, now()))
        else:
            c.execute(
                "INSERT OR REPLACE INTO analysis(book_id, pov, confidence, narrator, tense, game_system, chapters, "
                "words, details, version, error, at) VALUES(?,?,?,?,?,?,?,?,?,?,NULL,?)",
                (book_id, result["pov"], result.get("confidence"), result.get("narrator"), result.get("tense"),
                 int(bool(result.get("game_system"))), result.get("chapters"), result.get("words"),
                 jdump({"note": result.get("note"), "lang": result.get("lang"), **result.get("details", {}),
                        **({"themes_version": THEMES_VERSION} if "themes" in result else {})}),
                 VERSION, now()))
            text_tags = []
            if result["pov"] in ("first", "third", "second"):
                text_tags.append((f"pov-{result['pov']}", None))
            if result["pov"] == "first" and result.get("narrator") == "male":
                text_tags.append(("male-lead", None))
            if result["pov"] == "first" and result.get("narrator") == "female":
                text_tags.append(("female-lead", None))
            if result.get("tense") == "present":
                text_tags.append(("present-tense", None))
            if result.get("game_system"):
                text_tags.append(("game-messages", None))
            _replace_tags(c, book_id, "text", text_tags)
            _refresh_rules(c, book_id)
            if "themes" in result:
                _replace_maybe_tags(c, book_id, result["themes"])
        c.execute("UPDATE books SET analyzed_at=? WHERE id=?", (now(), book_id))
        _recompute_pov(c, book_id)


def set_user(book_id: int, **fields):
    """Your own marks on a book: shelf, favorite, pov (narration correction), note."""
    allowed = {k: v for k, v in fields.items() if k in ("shelf", "favorite", "pov", "note")}
    if not allowed:
        return
    with db.transaction() as c:
        c.execute("INSERT OR IGNORE INTO user_books(book_id, updated_at) VALUES(?,?)", (book_id, now()))
        c.execute(f"UPDATE user_books SET {', '.join(f'{k}=?' for k in allowed)}, updated_at=? WHERE book_id=?",
                  [*allowed.values(), now(), book_id])
        if "pov" in allowed:
            _recompute_pov(c, book_id)


def set_user_tags(book_id: int, tag_ids: list[str]):
    with db.transaction() as c:
        _replace_tags(c, book_id, "user", [(t, None) for t in tag_ids])
        _refresh_rules(c, book_id)
        _recompute_pov(c, book_id)


def recompute_popularity(site: str | None = None):
    sites = [site] if site else [r[0] for r in db.conn().execute("SELECT DISTINCT site FROM books")]
    for s in sites:
        with db.transaction() as c:
            c.execute(
                "UPDATE books SET popularity = r.pr FROM (SELECT id, PERCENT_RANK() OVER (ORDER BY pop_raw) AS pr "
                "FROM books WHERE site=? AND pop_raw IS NOT NULL) AS r WHERE books.id = r.id", (s,))


def refresh_tag_counts():
    with db.transaction() as c:
        c.execute("UPDATE tags SET books = 0")
        c.execute("UPDATE tags SET books = x.n FROM (SELECT tag, COUNT(DISTINCT book_id) AS n FROM book_tags "
                  "WHERE source != 'maybe' GROUP BY tag) AS x WHERE tags.id = x.tag")


def reapply_all_tags(progress=None):
    """After editing my_tags.toml: re-map every site label and re-run the rules for every book."""
    T.reload()
    _existing_tags.clear()
    c = db.conn()
    ids = [r[0] for r in c.execute("SELECT DISTINCT book_id FROM book_tags UNION "
                                   "SELECT id FROM books WHERE labels IS NOT NULL AND labels != '[]'")]
    for n, book_id in enumerate(ids):
        with db.transaction() as tc:
            _set_site_labels(tc, book_id, _site_labels(tc, book_id))
            _refresh_rules(tc, book_id)
            _recompute_pov(tc, book_id)
        if progress and n % 500 == 0:
            progress(n, len(ids))
    with db.transaction() as tc:  # labels for tags that became known
        for tid in T.all_ids():
            i = T.info(tid)
            tc.execute("UPDATE tags SET label=?, label_ru=?, label_uk=?, category=?, known=1 WHERE id=?",
                       (i["label"], i.get("label_ru"), i.get("label_uk"), i.get("category"), tid))
        tc.execute("UPDATE tags SET category='fandom' WHERE id LIKE 'fandom:%'")
        _drop_confirmed_maybes(tc)
        # labels that now map to a shared tag leave their old one-off tags behind
        tc.execute("DELETE FROM tags WHERE known=0 AND id NOT IN (SELECT DISTINCT tag FROM book_tags)")
    refresh_tag_counts()
    db.set_setting("tags_version", T.TAGS_VERSION)


def retag_if_needed() -> bool:
    """After an update that changed the built-in tag list: map every book's site labels again (in the background)."""
    if db.get_setting("tags_version", 1) == T.TAGS_VERSION:
        return False
    reapply_all_tags()
    return True
