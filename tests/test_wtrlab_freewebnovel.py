"""WTR-LAB and FreeWebNovel pages (markup as the sites write it, made-up novels)."""
import base64
import json

from bookkeeper.http import NotFound
from bookkeeper.sites.freewebnovel import FreeWebNovel
from bookkeeper.sites.wtrlab import WtrLab


class FakeHttp:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url, params=None, **kw):
        self.calls.append(url)
        if url not in self.pages:
            raise NotFound(url)
        return type("P", (), {"text": self.pages[url]})()


INDEX = ("<sitemapindex><sitemap><loc>https://wtr-lab.com/sitemap.xml</loc></sitemap>"
         "<sitemap><loc>https://wtr-lab.com/novels/sitemap/0.xml</loc></sitemap>"
         "<sitemap><loc>https://wtr-lab.com/novels/sitemap/1.xml</loc></sitemap></sitemapindex>")
MAP0 = ("<urlset><url><loc>https://wtr-lab.com/en/novel/7/the-slime-king</loc><lastmod>2024-01-01</lastmod></url>"
        "<url><loc>https://wtr-lab.com/en/novel/9/tea-&amp;-swords</loc></url></urlset>")
MAP1 = "<urlset><url><loc>https://wtr-lab.com/en/novel/11/last-one</loc></url></urlset>"
NEXT = {"props": {"pageProps": {
    "serie": {"serie_data": {"id": 7, "slug": "the-slime-king", "chapter_count": 120, "view": 5000, "in_library": 40,
                             "rating": 4.5, "total_rate": 12, "created_at": "2025-03-04 10:00:00+00",
                             "data": {"title": "The Slime King", "author": "Da Mo", "description": "A slime rises.",
                                      "image": "https://img.wtr-lab.com/x.jpg", "raw": {"title": "", "author": "大魔"},
                                      "raw_title_b64": base64.b64encode("史莱姆之王".encode()).decode()}},
              "names": [{"title": "The Slime King"}, {"title": "Slime Monarch"}], "ranks": {"all": 99}},
    "tags": [{"id": 1, "title": "Weak to Strong"}, {"id": 2, "title": "Non-human Protagonist"},
             {"id": 3, "title": "The Slime King"}]}}}
NOVEL = ('<div><span>Genre</span><a href="/en/novel-list?genre=9"><span class="x">fantasy</span></a>'
         '<a href="/en/novel-list?genre=33"><span class="x">xuanhuan</span></a></div><div>Status<span>Completed</span></div>'
         '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(NEXT) + "</script>")


def test_wtrlab_sitemaps_and_novel_page():
    site = WtrLab(FakeHttp({"https://wtr-lab.com/novels/index.xml": INDEX,
                            "https://wtr-lab.com/novels/sitemap/0.xml": MAP0,
                            "https://wtr-lab.com/novels/sitemap/1.xml": MAP1,
                            "https://wtr-lab.com/en/novel/7/the-slime-king": NOVEL}))
    state = {}
    batches = list(site.discover(state))
    assert [[b.sid for b in batch] for batch in batches] == [["7", "9"], ["11"]] and state["full_done"]
    assert batches[0][1].title == "Tea & Swords" and batches[0][1].url == "https://wtr-lab.com/en/novel/9/tea-&-swords"
    book = batches[0][0]
    d = site.details({"sid": book.sid, "url": book.url, "extra": book.extra})
    assert d.title == "The Slime King" and d.authors == ["Da Mo"] and d.alt_titles == ["Slime Monarch", "史莱姆之王"]
    assert d.origin == "cn" and d.status == "completed" and d.chapters == 120 and d.rating == 9.0 and d.votes == 12
    assert d.tags == ["fantasy", "xuanhuan", "Weak to Strong", "Non-human Protagonist", "Machine translation"]
    assert d.created_at == "2025-03-04" and d.extra["raw_author"] == "大魔"
    assert site.opening_text({"sid": "7"}) == [] and not site.has_text  # robots.txt rules out chapter pages
    site.http.calls.clear()
    assert [len(b) for b in site.discover(state)] == [2, 1]  # later passes: the last two sitemaps


CARD = """<div class="li-row"><div class="li"><div class="con"><div class="pic"><a href="/novel/sword-saint">
<img src="/files/article/image/1/123/123s.jpg" width="100"></a></div><div class="txt">
<h3 class="tit"><a href="/novel/sword-saint" title="Sword Saint &amp; Me">Sword Saint &amp; Me</a></h3>
<div class="core"><span>4.6</span><i></i></div><div class="desc"><div class="item"><div class="right">
<em class="e1"><a href="/sort/latest-release/chinese-novel" class="novel" title="Chinese Novel">Chinese Novel</a></em></div></div>
<div class="item"><div class="right"><a href="/genre/Xianxia" class="novel" title="Xianxia Novels">Xianxia</a>, <a href="/genre/Adult" class="novel" title="Adult Novels">Adult</a></div></div>
<div class="item"><div class="right"><a href="/novel/sword-saint/chapter-310" class="chapter" title="Chapter 310"><span class="s1">310 Chapters</span></a></div></div>
</div></div></div></div></div>"""
LISTING = ('<div class="pages"><a href="/genre/Xianxia/2">2</a><a href="/genre/Xianxia/7">7</a></div>' + CARD)
PAGE = """<meta property="og:novel:category" content="Chinese Novel"><meta property="og:novel:genre" content="Xianxia, Action">
<meta property="og:novel:author" content="Moon Blade, 月刃"><meta property="og:novel:status" content="Completed">
<meta property="og:novel:novel_name" content="Sword Saint &amp; Me"><meta property="og:novel:update_time" content="2026-10-01 04:42:25">
<meta property="og:novel:lastest_chapter_url" content="https://freewebnovel.com/novel/sword-saint/chapter-312">
<div class="item"><span class="glyphicon glyphicon-copy" title="Source"></span> <div class="right"> <span class="s1"><a href="https://x" class="a1" title="Qidian">Qidian</a></span></div></div>
<h1 class="tit">Sword Saint &amp; Me</h1><p class="vote">4.5 / 5 ( 264 votes )</p>
<div class="txt"><div class="inner"><p>He picks up a sword.</p><p>Then another.</p> </div></div>"""
WORDS = " ".join(["He swung the old sword again and the mountain answered with a low rumble."] * 30)
CHAPTER = ('<div id="readerPageTitle"><span class="chapter">Chapter 1 The Sword</span></div><div class="txt">'
           '<div id="article"><p> ' + WORDS + ' </p><!--fnw-reader-ad--><div class="ad"><iframe></iframe></div>'
           '<!--fnw-reader-ad-end--><p>This chapter is updated by f r e e w e b n o v e l . c o m</p>'
           '<p> "Again," said the master.</p></div> <!--bg--> <p>Comments</p>')


def test_freewebnovel_listing_details_and_chapters():
    site = FreeWebNovel(FakeHttp({"https://freewebnovel.com/genre/Xianxia": LISTING,
                                  "https://freewebnovel.com/novel/sword-saint": PAGE,
                                  "https://freewebnovel.com/novel/sword-saint/chapter-1": CHAPTER}))
    books, last = site._listing("genre/Xianxia", 1)
    assert last == 7 and len(books) == 1
    b = books[0]
    assert b.sid == "sword-saint" and b.title == "Sword Saint & Me" and b.origin == "cn" and b.is_translation
    assert b.tags == ["Xianxia", "Adult"] and b.adult and b.chapters == 310 and b.rating == 9.2 and b.extra["last"] == 310
    d = site.details({"sid": "sword-saint"})
    assert d.title == "Sword Saint & Me" and d.authors == ["Moon Blade"] and d.extra["author_names"] == ["Moon Blade", "月刃"]
    assert d.status == "completed" and d.chapters == 312 and d.votes == 264 and d.rating == 9.0
    assert d.tags == ["Xianxia", "Action"] and d.updated_at == "2026-10-01" and d.extra["source"] == "Qidian"
    assert d.description == "He picks up a sword.\nThen another."
    chapters = site.chapters({"sid": "sword-saint", "extra": d.extra})
    assert len(chapters) == 312 and chapters[0].id == "1"
    text = site.chapter_text({"sid": "sword-saint"}, chapters[0])
    assert chapters[0].title == "Chapter 1 The Sword"
    assert text.startswith("He swung") and text.endswith('"Again," said the master.') and "novel" not in text
    assert site.chapter_text({"sid": "sword-saint"}, chapters[1]) == ""  # a missing chapter


def test_freewebnovel_walks_every_listing_up_to_fifty_pages():
    site = FreeWebNovel(FakeHttp({}))
    seen = []

    def listing(path, page):
        seen.append((path, page))
        return ([object()], 80) if path == "sort/latest-novel" else ([], 0)
    site._listing = listing
    state = {}
    n = sum(1 for _ in site.discover(state))
    assert n == 50 and seen[49] == ("sort/latest-novel", 50) and seen[50] == ("sort/latest-release", 1)
    assert state["full_done"] and ("genre/Yaoi/completed", 1) in seen
