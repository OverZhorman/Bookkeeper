"""FanMTL pages (markup as the site writes it, made-up novels)."""
from bookkeeper.http import NotFound
from bookkeeper.sites.base import Chapter
from bookkeeper.sites.fanmtl import FanMtl

B = "https://www.fanmtl.com"


class FakeHttp:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url, params=None, **kw):
        self.calls.append(url)
        if url not in self.pages:
            raise NotFound(url)
        return type("P", (), {"text": self.pages[url]})()


def item(sid, title, chapters, status="Ongoing"):
    return (f'<li class="novel-item">\n<a href="/novel/{sid}.html" title="{title}">\n<div class="cover-wrap"><figure '
            f'class="novel-cover"><img class="lazy" src="/static/picture/placeholder-158.jpg" data-src="/d/file/c/'
            f'{sid}.jpg" alt="{title}" /></figure></div>\n<h4 class="novel-title text2row">{title}</h4>\n'
            f'<div class="novel-stats"><span><i class="material-icons">book</i> {chapters} Chapters</span></div>\n'
            f'<div class="novel-stats">Status: <span class="status cpl">{status}</span></div>\n</a>\n</li>\n')


def listing(sort, page, last, items):
    nav = "".join(f'<li><a href="/list/all/all-{sort}-{n}.html">{n + 1}</a></li>' for n in range(last + 1) if n != page)
    return (f'<nav class="paging"><ul class="pagination">{nav}</ul></nav><section>'
            f'<ul class="novel-list grid col col2">{"".join(items)}</ul></section><ul class="footer"></ul>')


NOVEL = """<article id="novel"><div class="novel-info"><div class="main-head">
<h1 itemprop="name" class="novel-title text2row">Konoha: The Tea Master&#039;s Path</h1>
<h2 class="alternative-title text1row notranslate">火影：茶道之路</h2>
<div class="author"><span>Author:</span><span itemprop="author">佚名</span></div><div class="rating"></div></div>
<nav class="links notranslate"><a id="readchapterbtn" href="/novel/kks77_901.html"><span>Read</span></a></nav>
<div class="header-stats"><span><strong><i class="fas fa-book"></i> 1020</strong><small>Chapters</small></span>
<span><strong class="">Completed</strong><small>Status</small></span></div>
<div class="categories"><strong>Categories</strong><ul>
<li><a href='/list/fan-fiction/all-newstime-0.html' title="Fan-Fiction" class="property-item">Fan-Fiction</a></li>
<li><a href='/list/naruto/all-newstime-0.html' title="Naruto" class="property-item">Naruto</a></li>
<li><a href='/list//all-newstime-0.html' title="Wuxia Xianxia" class="property-item">Wuxia Xianxia</a></li>
<li><a href='/list/faloo/all-newstime-0.html' title="Faloo" class="property-item">Faloo</a></li></ul>
<ul><li><a class="tag"  href='/tags/2-0.html'>WeaktoStrong</a></li></ul></div></div>
<section id="info" class="tab-pane"><div class="summary"><h4>Summary</h4><div class="content">
<p>He brews tea.<br>Then he brews more.</p> <p>Novel keywords: Konoha Tea txt Complete Works Download</p></div></div>
<div class="tags"><h4>Tags</h4><ul class="content"><li><a class="tag"  href='/tags/2-0.html'>WeaktoStrong</a></li>
<li><a class="tag"  href='/tags/580-0.html'></a></li>
<li><a class="tag"  href='/tags/906-0.html'>R-18</a></li></ul></div>
</section><section id="chapters"><div class="intro"><strong>Latest Release:</strong>
<a href="/novel/kks77_1020.html">Chapter 120</a> . <a href="/novel/kks77_1019.html">119</a></div></section>"""
WORDS = " ".join(["The kettle sang while the leaves unfolded in the hot water of the old pot."] * 20)
CHAPTER = ('<header class="chapter-header skiptranslate"><div class="titles"><h1><a href="/novel/kks77.html">Konoha'
           '</a></h1><h2>Chapter 1: The Master&amp;#039;s Kettle</h2></div></header><section><div class="chapter-'
           'content">\n<div align="center"><script>ads()</script></div>\n<p>Chapter 1 The Kettle</p><p>' + WORDS +
           '</p><p><script>more()</script>'
           '</p><p>"Again," said the master.</p><p>Read it first on fanmtl.com</p><p>(End of this chapter)</p></p>\n'
           '</div><div class="chapternav"><a class="nextchap" href="/novel/kks77_902.html">Next</a></div>')


def test_fanmtl_walks_the_list_by_popularity_then_by_date():
    site = FanMtl(FakeHttp({
        f"{B}/list/all/all-onclick-0.html": listing("onclick", 0, 1, [item("a1", "Tea &amp; Swords", 12)]),
        f"{B}/list/all/all-onclick-1.html": listing("onclick", 1, 1, [item("b2", "Second", 522475)]),
        f"{B}/list/all/all-newstime-0.html": listing("newstime", 0, 0, [item("c3", "Newest", 3), item("a1", "x", 12)]),
        f"{B}/list/all/all-lastdotime-0.html": listing("lastdotime", 0, 0, [item("a1", "x", 13)])}))
    state = {}
    batches = list(site.discover(state))  # several pages per batch
    assert [[b.sid for b in batch] for batch in batches] == [["a1", "b2"], ["c3", "a1"]]
    a1, b2 = batches[0]
    assert a1.title == "Tea & Swords" and a1.chapters == 12
    assert a1.pop_raw == 1_000_000 - 1 and b2.pop_raw == 1_000_000 - 31  # ranks: 30 novels a page
    assert a1.cover == f"{B}/d/file/c/a1.jpg" and a1.status == "ongoing" and a1.extra == {"last": 12}
    assert b2.chapters is None and b2.extra == {"last": 522475}  # a site-wide chapter number, not a count
    assert state["full_done"] and state["top"] == ["c3", "a1"] and batches[1][0].pop_raw is None
    # Later passes: new novels until one seen last time, then the latest updates.
    site.http.calls.clear()
    assert [[b.sid for b in batch] for batch in site.discover(state)] == [["c3", "a1"], ["a1"]]
    assert site.http.calls == [f"{B}/list/all/all-newstime-0.html", f"{B}/list/all/all-lastdotime-0.html"]


def test_fanmtl_novel_page_and_chapters():
    site = FanMtl(FakeHttp({f"{B}/novel/kks77.html": NOVEL, f"{B}/novel/kks77_901.html": CHAPTER}))
    d = site.details({"sid": "kks77"})
    assert d.title == "Konoha: The Tea Master's Path" and d.alt_titles == ["火影：茶道之路"] and d.authors == []
    assert d.origin == "cn" and d.is_translation and d.status == "completed" and d.adult
    assert d.tags == ["Fan-Fiction", "fandom:Naruto", "Wuxia", "Xianxia", "WeaktoStrong", "R-18", "Machine translation"]
    assert d.description == "He brews tea.\nThen he brews more." and d.extra["source"] == "Faloo"
    assert d.chapters == 120 and d.extra["first"] == 901 and d.extra["last"] == 1020
    chapters = site.chapters({"sid": "kks77"})  # not looked at yet: the novel page says where chapters start
    assert len(chapters) == 120 and (chapters[0].id, chapters[-1].id) == ("901", "1020")
    text = site.chapter_text({"sid": "kks77"}, chapters[0])
    assert chapters[0].title == "Chapter 1: The Master's Kettle"
    assert text.startswith("The kettle sang") and text.endswith('"Again," said the master.')
    assert "ads()" not in text and "fanmtl" not in text
    assert site.chapter_text({"sid": "kks77"}, Chapter(id="902", title="", index=1)) == ""  # a missing chapter
