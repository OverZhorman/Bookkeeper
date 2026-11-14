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
    found: dict[int, list[int]] = {}
    for x in list(parent):
        found.setdefault(find(x), []).append(x)
    groups = [sorted(set(v)) for v in found.values() if len(set(v)) > 1]
    return _save_groups(c, groups, progress)


def _save_groups(c, groups: list[list[int]], progress=None) -> int:
    """Write the groups, changing only what differs from the saved ones: groups that formed, grew, shrank or broke
    up, a different main copy, and copies whose shared tags are out of date. (Rewriting every group each time kept
    the collectors waiting and made the database's write-ahead log grow by hundreds of MB.)"""
    from .library import _recompute_pov, _refresh_rules  # local import: avoids a cycle
    ids = sorted({m for members in groups for m in members})
    rank: dict[int, tuple] = {}
    own: dict[int, set[str]] = {i: set() for i in ids}
    copied: dict[int, set[str]] = {i: set() for i in ids}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        q = ",".join("?" * len(chunk))
        for r in c.execute(f"SELECT id, meta_at IS NOT NULL, COALESCE(popularity, 0), COALESCE(chapters, 0) "
                           f"FROM books WHERE id IN ({q})", chunk):
            rank[r[0]] = (r[1], r[2], r[3])
        for r in c.execute(f"SELECT book_id, tag, source FROM book_tags WHERE book_id IN ({q}) "
                           f"AND source IN ('site', 'text', 'user', 'other-site')", chunk):
            (copied if r[2] == "other-site" else own)[r[0]].add(r[1])
    groups = [g for g in ([m for m in members if m in rank] for members in groups) if len(g) > 1]  # gone meanwhile
    grouped = {m for members in groups for m in members}
    current = {r[0]: (r[1], r[2]) for r in c.execute("SELECT id, work_id, is_primary FROM books "
                                                     "WHERE work_id IS NOT NULL")}
    saved: dict[int, set[int]] = {}
    for book_id, (work_id, _) in current.items():
        saved.setdefault(work_id, set()).add(book_id)

    # Copies that aren't part of any group any more stand alone again.
    shared = {r[0] for r in c.execute("SELECT DISTINCT book_id FROM book_tags WHERE source='other-site'")}
    alone = sorted((set(current) | shared) - grouped)
    for i in range(0, len(alone), 200):
        chunk = alone[i:i + 200]
        q = ",".join("?" * len(chunk))
        with db.transaction() as tc:
            tc.execute(f"UPDATE books SET work_id=NULL, is_primary=1 WHERE id IN ({q}) AND work_id IS NOT NULL",
                       chunk)
            tc.execute(f"DELETE FROM book_tags WHERE source='other-site' AND book_id IN ({q})", chunk)
            for m in chunk:
                _refresh_rules(tc, m)
                _recompute_pov(tc, m)

    def main_copy(members):
        # The copy with details, then the most popular, then the longest; on a tie the current main copy stays.
        return max(members, key=lambda m: (*rank[m], current[m][1] if m in current else 0, -m))

    def tags_from_others(members, m):
        return set().union(*(own[o] for o in members if o != m)) - own[m]

    main_only = []
    for n, members in enumerate(groups):
        work_id, best = members[0], main_copy(members)
        if saved.get(work_id) != set(members) or any(copied[m] != tags_from_others(members, m) for m in members):
            q = ",".join("?" * len(members))
            with db.transaction() as tc:
                tc.execute(f"UPDATE books SET work_id=?, is_primary=(id=?) WHERE id IN ({q})",
                           [work_id, best, *members])
                share_tags(tc, members)
        elif any(current[m][1] != (m == best) for m in members):
            main_only.append((best, members))
        if progress and n % 200 == 0:
            progress(n, len(groups))
    for i in range(0, len(main_only), 200):
        with db.transaction() as tc:
            for best, members in main_only[i:i + 200]:
                tc.execute(f"UPDATE books SET is_primary=(id=?) WHERE id IN ({','.join('?' * len(members))})",
                           [best, *members])
    return len(groups)


def share_tags(tc, members: list[int]) -> None:
    """Each copy of a work gets the tags the other copies have and it lacks (source 'other-site'). Narration from
    another copy only counts when this copy has neither a site tag nor its own analysis (see library._recompute_pov)."""
    from .library import _refresh_rules, _recompute_pov, _replace_tags  # local import: avoids a cycle
    own = {m: {r[0] for r in tc.execute("SELECT DISTINCT tag FROM book_tags WHERE book_id=? AND "
                                        "source IN ('site','text','user')", (m,))} for m in members}
    for m in members:
        others = set().union(*(own[o] for o in members if o != m)) - own[m]
        _replace_tags(tc, m, "other-site", [(t, None) for t in others])
        _refresh_rules(tc, m)
        _recompute_pov(tc, m)
