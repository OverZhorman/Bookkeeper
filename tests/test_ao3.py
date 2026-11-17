"""Archive of Our Own pages (markup as the site writes it, made-up works)."""
from bookkeeper.http import NotFound
from bookkeeper.sites.ao3 import Ao3, parse_listing
from bookkeeper.sites.base import Chapter

B = "https://archiveofourown.org"


class FakeHttp:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url, params=None, **kw):
        self.calls.append((url, params))
        key = url + ("?page=%d" % params["page"] if params and "page" in params else "")
        if key not in self.pages:
            raise NotFound(url)
        return type("P", (), {"text": self.pages[key], "url": url})()


def blurb(wid, title, fandoms, rating="Teen And Up Audiences", rclass="teen", lang="en", complete=True,
          chapters="3/3", tags=("First Person",), author='<a rel="author" href="/users/ann/pseuds/ann">ann</a>'):
    fl = ", ".join(f'<a class="tag" href="/tags/x/works">{f}</a>' for f in fandoms)
    ff = " ".join(f"<li class='freeforms'><a class=\"tag\" href=\"/tags/x/works\">{t}</a></li>" for t in tags)
    yes = "yes" if complete else "no"
    return f"""<li id="work_{wid}" class="work blurb group work-{wid} user-1" role="article">
  <div class="header module">
    <h4 class="heading">
      <a href="/works/{wid}">{title}</a>
      by
      {author}
    </h4>
    <h5 class="fandoms heading">
      <span class="landmark">Fandoms:</span>
      {fl}
      &nbsp;
    </h5>
    <ul class="required-tags">
<li><a class="help symbol question modal" title="Symbols key" href="/help/symbols_key"><span class="rating-{rclass} rating" title="{rating}"><span class="text">{rating}</span></span></a></li>
<li><a class="help symbol question modal" title="Symbols key" href="/help/symbols_key"><span class="warning-no warnings" title="No Archive Warnings Apply"><span class="text">No Archive Warnings Apply</span></span></a></li>
<li><a class="help symbol question modal" title="Symbols key" href="/help/symbols_key"><span class="category-multi category" title="F/M, Gen"><span class="text">F/M, Gen</span></span></a></li>
<li><a class="help symbol question modal" title="Symbols key" href="/help/symbols_key"><span class="complete-{yes} iswip" title="x"><span class="text">x</span></span></a></li>
</ul>
    <p class="datetime">05 Nov 2026</p>
  </div>
  <h6 class="landmark heading">Tags</h6>
  <ul class="tags commas">
    <li class='warnings'><strong><a class="tag" href="/tags/x/works">No Archive Warnings Apply</a></strong></li><li class='relationships'><a class="tag" href="/tags/x/works">Mira &amp; Tobin</a></li><li class='characters'><a class="tag" href="/tags/x/works">Mira</a></li> {ff}
  </ul>
    <h6 class="landmark heading">Summary</h6>
    <blockquote class="userstuff summary">
      <p>She wakes up inside the game.</p>
<p>Again.</p>
    </blockquote>
  <dl class="stats">
      <dt class="language">Language:</dt>
      <dd class="language" lang="{lang}">x</dd>
    <dt class="words">Words:</dt>
    <dd class="words">12,345</dd>
    <dt class="chapters">Chapters:</dt>
    <dd class="chapters"><a href="/works/{wid}/chapters/2">{chapters.split('/')[0]}</a>/{chapters.split('/')[1]}</dd>
    <dt class="kudos">Kudos:</dt>
    <dd class="kudos"><a href="/works/{wid}?view_full_work=true#kudos">1,204</a></dd>
    <dt class="bookmarks">Bookmarks:</dt>
    <dd class="bookmarks"><a href="/works/{wid}/bookmarks">77</a></dd>
  <dt class="hits">Hits:</dt>
  <dd class="hits">23,456</dd>
  </dl>
</li>
"""


def listing(page, last, items):
    nav = " ".join(f'<li><a href="/tags/LitRPG/works?page={n}">{n}</a></li>' for n in range(1, last + 1) if n != page)
    return (f'<h2 class="heading">1 - 20 of 99 Works in LitRPG</h2><ol class="work index group">\n'
            f'{"        ".join(items)}</ol>\n<ol class="pagination actions" title="pagination">{nav}</ol>')


def test_ao3_listing_card_has_everything():
    a, b, c = parse_listing(listing(1, 1, [
        blurb("101", "Respawn &amp; Repeat", ["Original Work"]),
        blurb("102", "Second", ["Naruto", "Boruto"], "Explicit", "explicit", complete=False, chapters="2/?",
              author="", tags=("Alternate Universe",)).replace("by\n", "by\n Anonymous"),
        blurb("103", "Другая", ["Original Work"], lang="ru")]))
    assert a.sid == "101" and a.url == f"{B}/works/101" and a.title == "Respawn & Repeat" and a.authors == ["ann"]
    assert a.description == "She wakes up inside the game.\nAgain." and a.lang == "en" and a.updated_at == "2026-11-05"
    assert a.status == "completed" and a.chapters == 3 and a.words == 12345 and a.likes == a.pop_raw == 1204
    assert a.views == 23456 and a.age_rating == "PG-13" and not a.adult and a.complete and a.access == "free"
    assert a.tags == ["F/M", "Gen", "Original", "Mira & Tobin", "Mira", "First Person"]
    assert a.extra == {"rating": "Teen And Up Audiences", "fandoms": [], "planned_chapters": 3, "bookmarks": 77,
                       "comments": None}
    assert b.adult and b.age_rating == "NC-17" and b.status == "ongoing" and b.authors == ["Anonymous"]
    assert b.tags[:5] == ["18+", "F/M", "Gen", "fandom:Naruto", "fandom:Boruto"]
    assert b.extra["planned_chapters"] is None and b.extra["fandoms"] == ["Naruto", "Boruto"]
    assert c.lang == "ru"


def test_ao3_reads_each_tag_list_then_only_the_newest_pages():
    page = lambda n, wids, lang="en": listing(n, 3, [blurb(w, f"Work {w}", ["Original Work"], lang=lang) for w in wids])
    http = FakeHttp({
        f"{B}/tags/LitRPG/works": page(1, ["1", "2"]),
        f"{B}/tags/LitRPG/works?page=2": page(2, ["3"], lang="de"),  # kept languages only
        f"{B}/tags/LitRPG/works?page=3": page(3, ["4"]),
        f"{B}/tags/Harry%20Potter%20-%20J*d*%20K*d*%20Rowling/works": page(1, ["5"]),
    })
    site = Ao3(http, {"tags": "LitRPG, Harry Potter - J. K. Rowling, Nothing Here", "pages": "2"})
    state = {}
    assert [[b.sid for b in batch] for batch in site.discover(state)] == [["1", "2"], ["5"]]  # 2 pages per tag
    assert state == {"full_done": True, "ti": 0, "page": 1}
    http.calls.clear()
    assert [[b.sid for b in batch] for batch in site.discover(state)] == [["1", "2"], ["4"], ["5"]]
    assert all("/works?" not in url and "/search" not in url for url, _ in http.calls)  # robots.txt


def test_ao3_tag_urls_use_its_own_escapes():
    assert Ao3.tag_url("Human/AI Relationship") == f"{B}/tags/Human*s*AI%20Relationship/works"
    assert Ao3.tag_url("Mira & Tobin") == f"{B}/tags/Mira%20*a*%20Tobin/works"


META = """<dl class="work meta group">
  <dt class="rating tags">Rating:</dt>
  <dd class="rating tags"><ul class="commas"><li><a class="tag" href="/tags/Mature/works">Mature</a></li></ul></dd>
  <dt class="fandom tags">Fandoms:</dt>
  <dd class="fandom tags"><ul class="commas"><li><a class="tag" href="/tags/x/works">Original Work</a></li></ul></dd>
  <dt class="freeform tags">Additional Tags:</dt>
  <dd class="freeform tags"><ul class="commas"><li><a class="tag" href="/tags/x/works">LitRPG</a></li></ul></dd>
  <dt class="language">Language:</dt><dd class="language" lang="en">English</dd>
  <dt class="stats">Stats:</dt><dd class="stats">
  <dl class="stats"><dt class="published">Published:</dt><dd class="published">2026-01-02</dd><dt class="status">Updated:</dt><dd class="status">2026-11-01</dd><dt class="words">Words:</dt><dd class="words">9,000</dd><dt class="chapters">Chapters:</dt><dd class="chapters">2/5</dd><dt class="kudos">Kudos:</dt><dd class="kudos">40</dd><dt class="hits">Hits:</dt><dd class="hits">900</dd></dl>
  </dd>
</dl>
</div>
<div id="workskin"><div class="preface group"><h2 class="title heading">
    Level One
  </h2><h3 class="byline heading"><a rel="author" href="/users/bo/pseuds/bo">bo</a></h3>
<div class="summary module"><h3 class="heading">Summary:</h3><blockquote class="userstuff"><p>Grinding.</p></blockquote></div></div>"""
CHAPTER = """<div class="chapter" id="chapter-{n}"><div class="chapter preface group"><h3 class="title">Ch</h3></div>
  <!--main content-->
  <div class="userstuff module" role="article">
    <h3 class="landmark heading" id="work">Chapter Text</h3>
    <p>I opened my eyes. Chapter {n}.</p><div class="skin">I checked my stats.</div>
  </div>
  <!--/main-->
</div>"""
MENU = """<select name="selected_id" id="selected_id"><option value="11">1. Arrival</option>
<option selected="selected" value="12">2. Stats</option></select>"""


def test_ao3_work_page_and_text():
    single = ('<div id="chapters" role="article">\n<h3 class="landmark heading" id="work">Work Text:</h3>\n'
              '<div class="userstuff"><p>Just me.</p><div>And my sword.</div></div>\n</div>\n<!-- end of cache -->')
    http = FakeHttp({
        f"{B}/works/7": MENU + META + '<div id="chapters">' + CHAPTER.format(n=1) + "</div>",
        f"{B}/works/7/navigate": '<ol class="chapter index group" role="navigation">\n'
                                 '  <li><a href="/works/7/chapters/11">1. Arrival</a> <span class="datetime">(x)</span></li>'
                                 '\n  <li><a href="/works/7/chapters/12">2. Stats</a></li>\n</ol>',
        f"{B}/works/7/chapters/12": META + CHAPTER.format(n=2) + '<div class="afterword preface group">Thanks!</div>',
        f"{B}/works/8": single,
    })
    site = Ao3(http, {})
    info = site.details({"sid": "7"})
    assert (info.title, info.authors, info.description, info.status) == ("Level One", ["bo"], "Grinding.", "ongoing")
    assert info.age_rating == "R" and not info.adult and info.chapters == 2 and info.words == 9000
    assert info.created_at == "2026-01-02" and info.updated_at == "2026-11-01" and info.tags == ["Original", "LitRPG"]
    assert info.extra["toc"] == [["11", "Arrival"], ["12", "Stats"]] and info.extra["planned_chapters"] == 5
    assert http.calls[0] == (f"{B}/works/7", {"view_adult": "true"})
    assert [(c.id, c.title) for c in site.chapters({"sid": "7"})] == [("11", "Arrival"), ("12", "Stats")]
    text = site.chapter_text({"sid": "7"}, Chapter("12", "Stats", 1))
    assert text.split("\n") == ["I opened my eyes. Chapter 2.", "I checked my stats."]  # no heading, no end notes
    assert site.opening_text({"sid": "7"}) == ["I opened my eyes. Chapter 1.\nI checked my stats."]
    assert http.calls[-1] == (f"{B}/works/7", {"view_adult": "true", "view_full_work": "true"})
    assert site.chapter_text({"sid": "8"}, Chapter("", "Text", 0)) == "Just me.\nAnd my sword."


def test_ao3_overloaded_page_is_not_a_bot_check():
    import httpx

    from bookkeeper.http import looks_like_bot_check
    beacon = ("<script>var u='/cdn-cgi/challenge-platform/scripts/jsd/main.js?ray=a5b6';</script>")
    overloaded = f"<title>Page Responding Too Slowly | Archive of Our Own</title><h2>Error 503</h2>{beacon}".encode()
    assert looks_like_bot_check(503, httpx.Headers({"server": "cloudflare"}), overloaded) is None
    challenge = (b"<title>Just a moment...</title><script src='/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/"
                 b"v1'></script>")
    assert looks_like_bot_check(403, httpx.Headers({}), challenge) == "bot check"
    assert looks_like_bot_check(403, httpx.Headers({}), b"<script src='/cdn-cgi/challenge-platform/h/g/x'>") == "bot check"
    assert looks_like_bot_check(200, httpx.Headers({"cf-mitigated": "challenge"}), b"") == "Cloudflare bot check"


def test_anubis_check_page_is_a_bot_check():
    import httpx

    from bookkeeper.http import looks_like_bot_check
    page = ('<title>Проверяем, что вы не бот!</title><link rel="stylesheet" href="/.within.website/x/xess/xess.min.css'
            '?cachebuster=1.22.0"><p>Защищено Anubis От Techaro.</p>').encode()
    assert looks_like_bot_check(200, httpx.Headers({}), page) == "Anubis bot check"
    assert looks_like_bot_check(200, httpx.Headers({}), b"<title>SquidgeWorld</title><p>Anubis the god</p>") is None


def test_squidgeworld_is_ao3_at_its_own_address_and_names_itself():
    from bookkeeper.sites.squidgeworld import SquidgeWorld
    sq = "https://squidgeworld.org"
    http = FakeHttp({f"{sq}/tags/Original%20Works%20-%20Novel/works": listing(1, 1, [
        blurb("9", "A Novel", ["Original Works - Novel", "No Fandom"]),
        blurb("10", "Fic", ["Star Wars - All Media Types", "Ironden [Original Work]"])])})
    site = SquidgeWorld(http, {"tags": "Original Works - Novel", "pages": "1"})
    (batch,) = list(site.discover({}))
    novel, fic = batch
    assert novel.url == f"{sq}/works/9" and novel.extra["fandoms"] == []
    assert "Original" in novel.tags and not any(t.startswith("fandom:") for t in novel.tags)
    assert "fandom:Star Wars - All Media Types" in fic.tags and fic.extra["fandoms"] == ["Star Wars - All Media Types"]
    assert SquidgeWorld.tag_url("A/B") == f"{sq}/tags/A*s*B/works" and Ao3.tag_url("A").startswith(B)
    assert SquidgeWorld.user_agent.startswith("Bookkeeper/") and "Mozilla" not in SquidgeWorld.user_agent
    assert Ao3.user_agent is None  # AO3 itself keeps the usual one
