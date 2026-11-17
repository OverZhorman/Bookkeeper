"""Scryer pages (markup as the site writes it, made-up stories)."""
from bookkeeper.sites.scryer import Scryer, fandom_ids, parse_results

B = "https://scryer.darklordpotter.net"


class FakeHttp:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url, params=None, ok_status=(), **kw):
        self.calls.append((url, dict(params or {})))
        key = url
        if params:
            key += "|" + ",".join(f"{params.get(k)}" for k in ("search[fandoms][]", "search[sort_by]", "page"))
        text = self.pages.get(key)
        if text is None:  # past the pages Scryer shows logged out
            return type("P", (), {"status": 401, "text": "You must be logged in to view more results."})()
        return type("P", (), {"status": 200, "text": text, "url": url})()


def card(sid, title, foot, labels=("time travel", "self insert"), xover=None):
    lab = " ".join(f'<span class="label label-default">{x}</span>' for x in labels)
    partner = f'<i class="fa fa-random"></i>\n        {xover}\n        -\n' if xover else ""
    return f"""<div class="panel panel-default">
  <div class="panel-heading">
    <h3 class="panel-title">
      <a
              class="story-link"
              data-story="{title}"
              data-story-origin="search"
              data-story-id="{sid}"
              rel="nofollow noopener"
              target="_blank"
              href="https://www.fanfiction.net/s/{sid}/1/Some-Title">{title}</a>
      by
      <a
              class="author-link"
              data-author="77"
              rel="nofollow noopener"
              target="_blank"
              href="https://www.fanfiction.net/u/77/Quill">Quill</a>
    </h3>
  </div>
  <div class="story-summary panel-body">
    I woke up as a first-year again. This time I&#39;m ready.
    <div>
      <hr />
      {lab}
        <i class="text-muted fa fa-question-circle xsmall"
           title="Content tags are derived from story attributes such as the summary and characters."></i>
    </div>
  </div>
  <div class="panel-footer small">
    {partner}<span class="pull-right text-muted"
          title="Updated: 2026-11-10 13:29:01 UTC"
          am-time-ago="item.updated"><time datetime="2026-11-10T13:29:01Z" title="x" data-time-ago="2026-11-10T13:29:01Z">2026-11-10</time></span>
    <strong title="Published: 2025-01-02 19:57:06 UTC">
      {foot[0]}
    </strong>
    {foot[1]}
    <span class="text-muted">
      - 1,267 favorites
      - 115 follows
    </span>
  </div>
</div>
"""


def results(page, last, cards):
    nav = "".join(f'<li><a href="/search?page={n}&amp;q=x">{n}</a></li>' for n in range(1, last + 1) if n != page)
    return (f'<h4 class="page-header">Search in Harry Potter</h4><div id="search" data-search="{{}}">{"".join(cards)}'
            f'<div class="text-right"><ul class="pagination pagination-sm">{nav}</ul></div>')


SHIP = ('<span class="text-success"><i class="fa fa-margin fa-angle-left"></i>Harry P., Daphne G.<i class="fa fa-margin '
        'fa-angle-right"></i></span>, Luna L.')


def test_scryer_card_has_the_whole_ffn_entry():
    a, b = parse_results(results(1, 1, [
        card("101", "Again &amp; Again", ("In-Progress", f"- T\n    - Adventure/Hurt/Comfort\n    - {SHIP}\n"
                                                         "    - 120,578 words\n    - 31 chapters\n    - 402 reviews")),
        card("102", "Short", ("Complete", "- M\n    - General\n    -\n    - 2,000 words\n    - 1 chapter\n"
                                          "    - 1 review"), labels=("smut",), xover="Naruto"),
    ]), "Harry Potter", "en")
    assert (a.sid, a.url, a.title, a.authors) == ("101", "https://www.fanfiction.net/s/101/1/", "Again & Again", ["Quill"])
    assert a.description == "I woke up as a first-year again. This time I'm ready." and a.lang == "en"
    assert a.status == "ongoing" and a.age_rating == "PG-13" and not a.adult and a.complete and a.access == "free"
    assert (a.words, a.chapters, a.likes, a.pop_raw) == (120578, 31, 1267, 1267)
    assert (a.created_at, a.updated_at) == ("2025-01-02", "2026-11-10")
    assert a.tags == ["Adventure", "Hurt/Comfort", "fandom:Harry Potter", "time travel", "self insert",
                      "Harry P./Daphne G.", "Harry P.", "Daphne G.", "Luna L."]
    assert a.extra["rating"] == "T" and a.extra["reviews"] == 402 and a.extra["follows"] == 115
    assert b.status == "completed" and b.age_rating == "R" and b.adult and b.chapters == 1 and b.words == 2000
    assert b.tags == ["General", "fandom:Harry Potter", "fandom:Naruto", "smut"]
    assert b.extra["fandoms"] == ["Harry Potter", "Naruto"]
    (w,) = parse_results(results(1, 1, [card("103", "W", ("Complete", "- T - General - 10 words - 1 chapter"),
                                             labels=("powerful harry", "time travel"))]), "Worm", "en")
    assert w.tags == ["General", "fandom:Worm", "time travel"]  # Harry Potter-only tags left out elsewhere


HOME = """<select multiple class="form-control" name="search[fandoms][]" id="search[fandoms][]">
<option value="224">Harry Potter</option><option value="80">Pokémon</option></select>
<select multiple class="form-control" name="search[crossovers][]" id="search[crossovers][]">
<option value="-1">All Crossovers (63049)</option><option value="1402">Naruto (3323)</option></select>"""


def test_scryer_fandom_names_and_lists():
    assert fandom_ids(HOME) == {"naruto": "1402", "harry potter": "224", "pokémon": "80"}  # not "All Crossovers"
    foot = ("Complete", "- K\n - General\n - 10 words\n - 1 chapter")
    http = FakeHttp({
        f"{B}/": HOME,
        f"{B}/search|224,meta.favs,None": results(1, 3, [card("1", "A", foot), card("2", "B", foot)]),
        f"{B}/search|224,meta.favs,2": results(2, 3, [card("3", "C", foot)]),
        # page 3: "You must be logged in to view more results" (HTTP 401) -> the next fandom
        f"{B}/search|1402,meta.favs,None": results(1, 1, [card("4", "D", foot)]),
        f"{B}/search|224,updated,None": results(1, 1, [card("5", "E", foot)]),
        f"{B}/search|1402,updated,None": results(1, 1, [card("4", "D", foot)]),
    })
    site = Scryer(http, {"fandoms": "Harry Potter, Nobody Knows, Naruto"})
    state = {}
    assert [[b.sid for b in batch] for batch in site.discover(state)] == [["1", "2"], ["3"], ["4"]]
    assert state == {"full_done": True, "li": 0, "page": 1}
    assert http.calls[1] == (f"{B}/search", {"search[fandoms][]": "224", "search[language]": "english",
                                            "search[sort_by]": "meta.favs", "search[order_by]": "desc"})
    assert [[b.sid for b in batch] for batch in site.discover(state)] == [["5"], ["4"]]  # later: the latest updates
    assert Scryer.has_text is False  # catalog only: the stories are on FanFiction.net
