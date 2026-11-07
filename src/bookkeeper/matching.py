"""Finding the same book on different sites, and sharing tags and narration between the copies.

Copies are matched on exact normalized keys only (no fuzzy guessing), so merges are rare but safe:
  * title + an author name word (for original works), and
  * a distinctive non-Russian title on its own (English or original titles of translated novels,
    e.g. "Omniscient Reader's Viewpoint" or "전지적 독자 시점").
"""
import re

from . import db

_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]|【[^】]*】")
_NOISE_WORDS = re.compile(r"\b(light novel|web novel|novel|ln|wn|новелла|ранобэ|ранобе|роман|книга \d+|том \d+)\b")
_KEEP = re.compile(r"[^0-9a-zа-яіїєґ぀-ヿ一-鿿가-힯]+")
_CYR = re.compile(r"[а-яіїєґ]")


def norm_title(title: str) -> str:
    s = (title or "").lower().replace("ё", "е")
    s = _BRACKETS.sub(" ", s)
    s = _NOISE_WORDS.sub(" ", s)
    return _KEEP.sub("", s)


def author_words(name: str) -> set[str]:
    s = (name or "").lower().replace("ё", "е")
    return {w for w in re.findall(r"[a-zа-яіїєґ]{3,}", s)}


def keys_for(title: str, alt_titles: list[str], authors: list[str], is_translation: bool) -> set[str]:
    keys = set()
    words = set()
    for a in authors[:2]:
        words |= author_words(a)
    for t in [title, *alt_titles]:
        tk = norm_title(t)
        if len(tk) < 3:
            continue
        for w in words:
            keys.add(f"ta:{tk}:{w}")
        # Non-Russian titles are distinctive enough on their own (English / original names).
        if len(tk) >= 8 and (is_translation or not _CYR.search(tk)):
            keys.add(f"t:{tk}")
    return keys


def update_keys(c, book_id: int, site: str, title: str, alt_titles: list[str], authors: list[str],
                is_translation: bool):
    c.execute("DELETE FROM match_keys WHERE book_id=?", (book_id,))
    for k in keys_for(title, alt_titles, authors, is_translation):
        c.execute("INSERT OR IGNORE INTO match_keys(key, book_id, site) VALUES(?,?,?)", (k, book_id, site))


def find_duplicates(progress=None) -> int:
    """Group copies of the same book across sites; share tags and narration between them.
    Returns the number of groups."""
    c = db.conn()
    parent: dict[int, int] = {}

    def find(x):
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    rows = c.execute("SELECT key, GROUP_CONCAT(book_id) AS ids FROM match_keys GROUP BY key "
                     "HAVING COUNT(DISTINCT site) >= 2 AND COUNT(*) <= 6").fetchall()
    for r in rows:
        ids = [int(x) for x in r["ids"].split(",")]
        for i in ids:
            parent.setdefault(i, i)
        root = find(ids[0])
        for other in ids[1:]:
            ro = find(other)
            if ro != root:
                parent[ro] = root
    groups: dict[int, list[int]] = {}
    for x in list(parent):
        groups.setdefault(find(x), []).append(x)
    groups = {k: sorted(set(v)) for k, v in groups.items() if len(set(v)) > 1}

    with db.transaction() as tc:
        tc.execute("UPDATE books SET work_id=NULL, is_primary=1 WHERE work_id IS NOT NULL")
        tc.execute("DELETE FROM book_tags WHERE source='other-site'")
    from .library import _refresh_rules, _recompute_pov, _replace_tags  # local import: avoids a cycle
    for n, members in enumerate(groups.values()):
        work_id = members[0]
        with db.transaction() as tc:
            q = ",".join("?" * len(members))
            best = tc.execute(
                f"SELECT id FROM books WHERE id IN ({q}) ORDER BY (meta_at IS NOT NULL) DESC, "
                f"COALESCE(popularity,0) DESC, COALESCE(chapters,0) DESC LIMIT 1", members).fetchone()["id"]
            tc.execute(f"UPDATE books SET work_id=?, is_primary=(id=?) WHERE id IN ({q})", [work_id, best, *members])
            own = {m: {r[0] for r in tc.execute("SELECT DISTINCT tag FROM book_tags WHERE book_id=? AND "
                                                "source IN ('site','text','user')", (m,))} for m in members}
            for m in members:
                # Tags the other copies have and this one lacks. Narration from another copy only counts
                # when this copy has neither a site tag nor its own analysis (see library._recompute_pov).
                others = set().union(*(own[o] for o in members if o != m)) - own[m]
                _replace_tags(tc, m, "other-site", [(t, None) for t in others])
                _refresh_rules(tc, m)
                _recompute_pov(tc, m)
        if progress and n % 200 == 0:
            progress(n, len(groups))
    return len(groups)
