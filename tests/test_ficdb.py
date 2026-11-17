"""Ficdb's limited search (markup as the site writes it, made-up stories)."""
from datetime import date

from bookkeeper.http import NotFound
from bookkeeper.sites.ficdb import Ficdb, _count, _date, parse_results

B = "https://ficdb.net"
TODAY = date(2026, 11, 17)


def card(sid, title, fandoms, tags, stats, sources=(("SB", "https://forums.spacebattles.com/threads/9"),)):
    def group(names):
        return ('<div class="field is-grouped is-grouped-multiline">' + "".join(
            f'<div class="control is-close">\n<div class="tags has-addons">\n<span class="tag is-primary">{n}</span>\n'
            f'</div>\n</div>' for n in names) + "\n</div>\n")
    src = "".join(f'<small><a target="_blank" href="{u}" class="tag">{c}</a></small>\n' for c, u in sources)
    return f"""<div class="card">
	<div class="card-content low-padding">
		<div class="media">
			<p class="title is-5">
				<a target="_blank" href="{sources[0][1]}">{title}</a>
			</p>
			{src}<small>
			<a href="/edit_story/{sid}">[edit]</a>
			<a id="follow-link{sid}" onclick="toggleFollowCookie({sid})">[follow]</a>
	</small>
		</div>
		<div class="content">
			<p class="subtitle is-6">by Quill
				</p>
			{group(fandoms)}{group(tags)}<div class="content wrap-text-boxes">
				<div class="truncated-content" id="truncated-content-{sid}">
				<p>I wake up in a game world.</p><p>The System &amp; I disagree.</p>
				</div>
			</div>
		</div>
	</div>
	<footer class="card-footer"><div class="card-footer-item"><div class="container is-pulled-right">
			<small>
	Word Count: {stats}
		·
<a class="is-small is-light" onclick="toggleFlagMenu({sid})">flag</a>
</small></div></div></footer>
</div>
"""


def page(n, last, cards):
    nav = "".join(f'<li><a class="pagination-link" href=/search?searchbox=x&safe_search=y&unverified=1&page={i}>{i}</a></li>'
                  for i in range(1, last + 1) if i != n)
    return f'<nav class="pagination" role="navigation"><ul class="pagination-list">{nav}</ul></nav>{"".join(cards)}'


STATS = ('74K\n\t\t· Chapters: 59\n\t\t· Rating: 1,245\n\t\t· Created: <time class="nowrap">Oct 11, 2025</time>\n'
         '\t\t· Updated: <time class"nowrap">Nov 16</time>')


def test_ficdb_card():
    (a,) = parse_results(page(1, 1, [card("876", "Hokage &amp; League", ["Naruto", "Original Work", "Unheard Of Show"],
                                          ["Isekai", "Smut"], STATS, (("SB", "https://forums.spacebattles.com/threads/9"),
                                                                      ("AO3", "https://archiveofourown.org/works/5")))]),
                         TODAY)
    assert (a.sid, a.url, a.title, a.authors) == ("876", "https://forums.spacebattles.com/threads/9", "Hokage & League",
                                                  ["Quill"])
    assert a.description == "I wake up in a game world.\nThe System & I disagree." and a.lang == "en"
    assert (a.words, a.chapters, a.likes, a.pop_raw) == (74000, 59, 1245, 1245)
    assert (a.created_at, a.updated_at) == ("2025-10-11", "2026-11-16") and a.adult and a.complete
    assert a.tags == ["fandom:Naruto", "Original Work", "fandom:Unheard Of Show", "Isekai", "Smut"]
    assert a.extra["sources"] == {"SpaceBattles": "https://forums.spacebattles.com/threads/9",
                                  "AO3": "https://archiveofourown.org/works/5"}


def test_ficdb_numbers_and_dates():
    assert (_count("4.9K"), _count("1.2M"), _count("59"), _count("")) == (4900, 1200000, 59, None)
    assert _date("Dec 30", TODAY) == "2025-12-30"  # a date "ahead" of today is last year's
    assert _date("Nov 17", TODAY) == "2026-11-17" and _date("nonsense", TODAY) is None


class FakeHttp:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url, params=None, **kw):
        self.calls.append(dict(params))
        key = (params["searchbox"], params.get("sortby"), params.get("page", 1))
        if key not in self.pages:
            raise NotFound(url)
        return type("P", (), {"text": self.pages[key]})()


def test_ficdb_reads_chosen_tags_through_the_limited_search():
    c = lambda sid: card(sid, f"Story {sid}", ["Worm"], ["Isekai"], STATS)  # noqa: E731
    http = FakeHttp({("Isekai", "rating", 1): page(1, 3, [c("1"), c("2")]), ("Isekai", "rating", 2): page(2, 3, [c("3")]),
                     ("Worm", "rating", 1): page(1, 1, [c("4")]),
                     ("Isekai", None, 1): page(1, 1, [c("5")]), ("Worm", None, 1): page(1, 1, [c("4")])})
    site = Ficdb(http, {"tags": "Isekai, Worm", "pages": "2"})
    state = {}
    assert [[b.sid for b in batch] for batch in site.discover(state)] == [["1", "2"], ["3"], ["4"]]
    assert state == {"full_done": True, "ti": 0, "page": 1}
    assert all(p["unverified"] == "1" and p["safe_search"] == "y" for p in http.calls)  # the search meant for programs
    assert [[b.sid for b in batch] for batch in site.discover(state)] == [["5"], ["4"]]  # later: latest updates
