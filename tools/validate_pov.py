"""Re-run the narration test: 41 books whose narration is known (21 Russian web novels from RanobeLIB,
20 English classics from Project Gutenberg). Texts are fetched on demand, slowly, and cached in
data/cache/validation so a second run is instant.

    uv run python tools/validate_pov.py
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bookkeeper import config  # noqa: E402
from bookkeeper.analysis.pov import analyse  # noqa: E402
from bookkeeper.http import Http  # noqa: E402
from bookkeeper.sites.ranobelib import RanobeLib  # noqa: E402

RANOBELIB = [  # (slug, title, narration, narrator)
    ("26690--omniscient-readers-viewpoint-novel", "Omniscient Reader's Viewpoint", "first", "male"),
    ("6709--youkoso-jitsuryoku-shijou-shugi-no-kyoushitsu-e-novel", "Classroom of the Elite", "first", "male"),
    ("12021--kono-subarashii-sekai-ni-shukufuku-wo", "Konosuba", "first", "male"),
    ("14841--beginning-after-the-end-novel", "The Beginning After the End", "first", "male"),
    ("6689--ascendance-of-a-bookworm-novel", "Ascendance of a Bookworm", "first", "female"),
    ("9402--suzumiya-haruhi-series", "Haruhi Suzumiya", "first", "male"),
    ("45102--koten-bu-series", "Hyouka", "first", "male"),
    ("6641--yahari-ore-no-seishun-rabukome-wa-machigatte-iru-novel", "Oregairu", "first", "male"),
    ("6684--kumo-desu-ga-nani-ka-novel", "So I'm a Spider, So What?", "first", "female"),
    ("163198--hanamonogatari", "Hanamonogatari", "first", "female"),
    ("16509--overgeared", "Overgeared (1st person from ch. 2)", "first", "male"),
    ("20818--lord-of-the-mysteries", "Lord of the Mysteries", "third", None),
    ("19232--mother-of-learning", "Mother of Learning", "third", None),
    ("122448--shadow-slave", "Shadow Slave", "third", None),
    ("18610--reverend-insanity", "Reverend Insanity", "third", None),
    ("6809--panlong-novel", "Coiling Dragon", "third", None),
    ("7413--release-that-witch-novel", "Release That Witch", "third", None),
    ("6664--log-horizon-novel", "Log Horizon", "third", None),
    ("7230--86-novel", "86", "third", None),
    ("11521--goburin-sureiya", "Goblin Slayer", "third", None),
    ("28062--kino-no-tabi-the-beautiful-world-sigsawa-keiichi", "Kino's Journey", "third", None),
]
GUTENBERG = [
    (2701, "Moby Dick", "first"), (1260, "Jane Eyre", "first"), (1400, "Great Expectations", "first"),
    (120, "Treasure Island", "first"), (76, "Huckleberry Finn", "first"), (1661, "Sherlock Holmes", "first"),
    (768, "Wuthering Heights", "first"), (64317, "The Great Gatsby", "first"), (219, "Heart of Darkness", "first"),
    (84, "Frankenstein", "first"),
    (1342, "Pride and Prejudice", "third"), (11, "Alice in Wonderland", "third"), (158, "Emma", "third"),
    (174, "The Picture of Dorian Gray", "third"), (74, "Tom Sawyer", "third"), (46, "A Christmas Carol", "third"),
    (2554, "Crime and Punishment", "third"), (215, "The Call of the Wild", "third"), (16, "Peter Pan", "third"),
    (55, "The Wizard of Oz", "third"),
]
HEADING = re.compile(r"^\s*((CHAPTER|Chapter|STAVE|Stave|LETTER|Letter|BOOK|PART)\b.*|[IVXLC]+\.?(\s+[A-Z].*)?)\s*$",
                     re.M)
CACHE = config.CACHE_DIR / "validation"


def cached(name, fetch):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    value = fetch()
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return value


def gutenberg_opening(book_id, words=6000):
    url = f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt"
    raw = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT}),
                                 timeout=60).read().decode("utf-8", "replace")
    time.sleep(1)
    m1, m2 = re.search(r"\*\*\* ?START OF.*?\*\*\*", raw), re.search(r"\*\*\* ?END OF", raw)
    body = raw[m1.end() if m1 else 0: m2.start() if m2 else len(raw)]
    heads = [m.start() for m in HEADING.finditer(body)]
    start = next((h for h, nxt in zip(heads, heads[1:] + [len(body)]) if nxt - h > 3000), int(len(body) * 0.02))
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", body[start:])]
    out, n = [], 0
    for p in paras:
        out.append(p)
        n += len(p.split())
        if n >= words:
            break
    return ["\n".join(out)]


def main():
    site = RanobeLib(Http("ranobelib", min_interval=1.0))
    rows = []
    for slug, title, truth, narrator in RANOBELIB:
        texts = cached(f"rl_{slug.split('--')[0]}", lambda: site.opening_text({"sid": slug}))
        rows.append(("RU", title, truth, narrator, analyse(texts)))
    for gid, title, truth in GUTENBERG:
        texts = cached(f"gb_{gid}", lambda: gutenberg_opening(gid))
        rows.append(("EN", title, truth, None, analyse(texts)))
    right = unsure = wrong = gender_right = gender_total = 0
    for lang, title, truth, narrator, r in rows:
        verdict = r["pov"]
        mark = "OK " if verdict == truth else "?? " if verdict == "unsure" else "XX "
        right += verdict == truth
        unsure += verdict == "unsure"
        wrong += verdict not in (truth, "unsure")
        g = ""
        if narrator:
            gender_total += 1
            gender_right += r.get("narrator") == narrator
            g = f"  narrator {r.get('narrator')} (known {narrator})"
        print(f"{mark}{lang} {title[:36]:36} known={truth:5} got={verdict:6} sure={r.get('confidence', 0):.2f}{g}")
    print(f"\n{right} right, {unsure} unsure, {wrong} wrong out of {len(rows)}; "
          f"narrator gender {gender_right}/{gender_total}")


if __name__ == "__main__":
    main()
