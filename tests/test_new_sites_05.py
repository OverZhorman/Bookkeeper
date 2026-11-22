"""Connectors added in 0.5 (markup as the sites write it, made-up books)."""
import json
from datetime import date
from urllib.parse import urlencode

import pytest

from bookkeeper.http import NotFound
from bookkeeper.sites import PLANNED, SITES
from bookkeeper.sites.base import SiteError


class Page:
    def __init__(self, url, text):
        self.url, self.text = url, text

    def json(self):
        return json.loads(self.text)


class FakeHttp:
    def __init__(self, pages=None, posts=None):
        self.pages, self.posts, self.calls = pages or {}, list(posts or []), []

    @staticmethod
    def key(url, params=None):
        return url + ("?" + urlencode(sorted(params.items())) if params else "")

    def get(self, url, params=None, **kw):
        k = self.key(url, params)
        self.calls.append(k)
        if k not in self.pages:
            raise NotFound(k)
        return Page(k, self.pages[k])

    def get_json(self, url, **kw):
        return self.get(url, **kw).json()

    def post(self, url, data=None, **kw):
        self.calls.append(("POST", url, dict(data or {})))
        return Page(url, self.posts.pop(0) if self.posts else "")


def test_registry_and_planned_lists():
    for sid in ("booknet", "litmarket", "prodaman", "litgorod", "bookriver", "fanficsme", "ranobeme", "novelklo",
                "fantlab", "novelfire", "goodnovel", "sunset", "sufficientvelocity"):
        assert SITES[sid].id == sid and SITES[sid].note
    planned = {p["id"] for p in PLANNED}
    assert {"spacebattles", "litsovet", "livelib", "mangalib", "anilist", "mangadex"} <= planned
    assert not planned & set(SITES)


# ----- Booknet
BN_CARD = """<div class="bn_book-genre">
<div class="bn_book-genre__image"><a href="/book/zorya-b123" class="bn_book-genre__image-link"></a>
<img src="https://st.booknet.ua/uploads/covers/120/1.jpg" alt="x" /></div>
<div class="bn_book-genre__price">Передплата<br /><span class="new-price-discount">79 грн</span></div></div>
<div class="bn_book-genre__title bn_text-heading-h4"><a href="/book/zorya-b123" class="bn_book-genre__title-link">
Зоря над морем</a></div>
<div class="bn_book-genre__author bn_text-paragraph-m"><a href="/olena-u1">Олена Морська</a></div>
<div class="bn_book-genre__annotation bn_text-paragraph-m">Вона прокинулась у чужому світі...</div>
<div class="bn_book-genre__tags bn_text-label-l"><span class="bn_book-genre__tags-prefix">В тексті є:</span>
<span><a href="/tag/магія-t1">магія</a>, <a href="/tag/попаданка-t2">попаданка</a></span></div>
<div class="bn_book-genre__statistics-item"><svg><use href="/s.svg#star"></use></svg><span class="x">1 374</span></div>
<div class="bn_book-genre__statistics-item"><svg><use href="/s.svg#eye"></use></svg><span class="x">173 152</span></div>
<div class="bn_book-genre__status-content">В процесі: 22 Листоп</div>
<div class="bn_book-genre__status-pages">68 стор.</div></div>"""
BN_TOP = ('<a href="/top/all?alias=all&amp;page=2">2</a><a href="/top/all?alias=all&amp;page=3">3</a>'
          + BN_CARD)
BN_BOOK = """<h1 class="bn_book__header-title bn_text-heading-h1">Зоря над морем
<span class="bn_book__header-adult-only bn_text-label-m">18+</span></h1>
<a class="bn_book__header-genre bn_text-paragraph-l" href="/top/fentezi">Фентезі</a>
<h2 class="bn_book__header-author-item-name bn_text-paragraph-l"><a href="/olena-u1">Олена Морська</a></h2>
<span class="bn_book__header-status-value">Повний текст · </span><span class="bn_book__header-status-count">127 стор.</span>
<div class="bn_book__header-button bn_book__header-button-like" onclick="x();"><svg/><span class="y">1 380</span></div>
<img class="bn_book__header-image-src" src="https://st.booknet.ua/uploads/covers/220/1.jpg" />
<a class="bn_btn bn_btn-bordered bn_buy-button" href="#">Передплата</a>
<div class="bn_book__about-content bn_text-paragraph-l">Вона прокинулась у чужому світі.<br>І пішла.</div>
<h4 class="bn_book__tags bn_text-paragraph-l"><a href="/tag/магія-t1">магія</a><a href="/tag/море-t3">море</a></h4>
<div class="bn_book__chapters-title">Зміст книги: 2 глави</div>
<div class="bn_book__chapters-item "> <div class="bn_book__chapters-item-heading">
<a href="/reader/zorya-b123?c=11" class="bn_book__chapters-item-link"></a> <svg/>
<span class="bn_book__chapters-item-title bn_text-paragraph-l"> Розділ 1 </span></div></div>
<div class="bn_book__chapters-item lock"> <div class="bn_book__chapters-item-heading">
<a href="/reader/zorya-b123?c=12" class="bn_book__chapters-item-link"></a> <svg/>
<span class="bn_book__chapters-item-title bn_text-paragraph-l"> Розділ 2 </span></div></div>"""
BN_READER = ('<meta name="csrf-token" content="tok"><div class="reader-text font-size-medium" data-chapter="11">'
             '<h2>Розділ 1</h2><p>Я відкрила очі.</p></div> <div id="event-params"></div>')


def test_booknet_catalog_book_and_reader():
    from bookkeeper.sites.booknet import Booknet, parse_card
    b = parse_card(BN_CARD)
    assert b.sid == "123" and b.title == "Зоря над морем" and b.authors == ["Олена Морська"]
    assert b.tags == ["магія", "попаданка"] and b.partial_tags and b.likes == 1374 and b.views == 173152
    assert b.status == "ongoing" and b.access == "partial" and b.lang == "uk" and b.extra["pages"] == 68
    http = FakeHttp({"https://booknet.ua/top/all?alias=all&page=1": BN_TOP,
                     "https://booknet.ua/book/zorya-b123": BN_BOOK,
                     "https://booknet.ua/reader/zorya-b123?c=11": BN_READER},
                    posts=['{"status":1,"data":"<p>Я відкрила очі.</p>"}', '{"status":1,"data":"<p>Я відкрила очі.</p>"}'])
    site = Booknet(http)
    state = {}
    first = next(site.discover(state))
    assert [x.sid for x in first] == ["123"] and state.get("page", 1) == 1  # moves on when the next page is asked
    ref = {"sid": "123", "extra": {"alias": "zorya-b123"}}
    d = site.details(ref)
    assert d.adult and d.age_rating == "18+" and d.status == "completed" and d.chapters == 2
    assert d.tags == ["Фентезі", "магія", "море"] and d.access == "partial" and d.title == "Зоря над морем"
    chs = site.chapters(ref)
    assert [(c.id, c.title, c.free) for c in chs] == [("11", "Розділ 1", True), ("12", "Розділ 2", False)]
    assert site.chapter_text(ref, chs[0]) == "Я відкрила очі."  # page 2 repeats page 1: the end
    assert [c for c in http.calls if isinstance(c, tuple)][0][2] == {"chapterId": "11", "page": "1", "_csrf": "tok"}


def test_booknet_adult_reader_says_so():
    from bookkeeper.sites.booknet import Booknet
    from bookkeeper.sites.base import Chapter
    site = Booknet(FakeHttp({"https://booknet.ua/reader/x-b1?c=5": "<title>Доступ обмежено</title>"}))
    with pytest.raises(SiteError):
        site.chapter_text({"sid": "1", "extra": {"alias": "x-b1"}}, Chapter(id="5", title="", index=0))


def test_sunset_is_ao3_on_its_own_address():
    from bookkeeper.sites.sunset import Sunset
    site = Sunset(FakeHttp())
    assert site._tags() == ["F/F"] and Sunset.tag_url("F/F") == "https://sunset.femslash.club/tags/F*s*F/works"


# ----- Fantlab
def fl_search(total, rows):
    out = f"<form name=genrevoteform></form><b>Найденные произведения ({total} шт.)</b>"
    for i, (wid, author, title, kind, year, score, votes) in enumerate(rows, 1):
        out += (f"<tr ><td><span class=\"hidden-numbers\">{i}. </span>{author} <a href=/work{wid} title='7.1'>"
                f"«{title}»</a><font color=gray> ({kind}, {year} г.)</font></td><td><nobr>{score} ({votes})</nobr>"
                "</td></tr>")
    return out


def test_fantlab_search_splits_by_year_then_language():
    from bookkeeper.sites.fantlab import Fantlab, parse_search
    books, total = parse_search(fl_search(1351, [(571633, "Дем Михайлов", "Гром небесный / Heaven's Thunder",
                                                  "Роман", 2015, "7.70", 1351)]))
    assert total == 1351 and books[0].sid == "571633" and books[0].title == "Гром небесный"
    assert books[0].alt_titles == ["Heaven's Thunder"] and books[0].votes == 1351 and books[0].extra["year"] == 2015
    y = date.today().year
    base = {"sort": "marks", "form": "nov", "wg280": "on"}
    url = "https://fantlab.ru/bygenre"
    pages = {
        FakeHttp.key(url, base): fl_search(120, [(1, "А", "Первая", "Роман", 2015, "7.0", 90)]),
        FakeHttp.key(url, {**base, "byyear": "on", "yearfrom": "1", "yearto": str(y)}):
            fl_search(30, [(2, "Б", "Вторая", "Роман", 2016, "7.0", 80)]),
    }
    site = Fantlab(FakeHttp(pages), settings={"genres": "ЛитРПГ"})
    state = {}
    assert [[b.sid for b in batch] for batch in site.discover(state)] == [["1"], ["2"]] and state["full_done"]
    # a single year with more than 50 is split into Russian-language and translated works
    pages2 = {FakeHttp.key(url, {**base, "byyear": "on", "yearfrom": "2015", "yearto": "2015"}):
              fl_search(80, [(3, "В", "Третья", "Роман", 2015, "7.0", 70)])}
    http = FakeHttp(pages2)
    state = {"todo": [[280, 2015, 2015, ""]]}
    list(Fantlab(http, settings={"genres": "ЛитРПГ"}).discover(state))
    assert any("lang_id=1" in c for c in http.calls) and any("lang_id=-1" in c for c in http.calls)


def test_fantlab_work_classifier():
    from bookkeeper.sites.fantlab import work_info
    d = {"work_id": 7, "work_name": "Мир  Полудня", "work_name_orig": "Noon", "work_name_alts": ["Полдень"],
         "authors": [{"type": "autor", "name": "Автор", "name_orig": "Author"}], "lang_code": "en",
         "work_description": "[b]Текст[/b] о [autor=1]ком-то[/autor].", "rating": {"rating": "8.5", "voters": 900},
         "work_notfinished": 0, "work_type": "Роман", "work_year": 1990,
         "editions_blocks": {"10": {"list": [{"edition_id": 55, "pic_num": 1}]}},
         "classificatory": {"genre_group": [
             {"genre_group_id": 1, "genre": [{"label": "Фантастика", "percent": 1, "genre": [
                 {"label": "Космоопера", "percent": 0.8}]}]},
             {"genre_group_id": 4, "genre": [{"label": "Далёкое будущее", "percent": 0.9}]},
             {"genre_group_id": 5, "genre": [{"label": "Для взрослых", "percent": 0.6},
                                             {"label": "Только для взрослых", "percent": 0.8}]},
             {"genre_group_id": 7, "genre": [{"label": "Линейный", "percent": 1}]}]}}
    b = work_info(d)
    assert b.title == "Мир  Полудня".strip() and b.alt_titles == ["Noon", "Полдень"] and b.authors == ["Автор"]
    assert b.tags == ["Фантастика", "Космоопера", "Далёкое будущее", "Возраст читателя: Для взрослых",
                      "Возраст читателя: Только для взрослых", "Линейность сюжета: Линейный"]
    assert b.adult and b.age_rating == "NC-17" and b.is_translation and b.origin == "en"
    assert b.description == "Текст о ком-то." and b.cover == "https://fantlab.ru/images/editions/small/55"


# ----- NovelFire
NF_LIST = """<li class="novel-item"><a title="Sword &amp; Moon" href="/book/sword-moon"><figure class="novel-cover">
<img class="lazy" src="data:x" data-src="/server-1/sword-moon.jpg"><span class="badge _bl"><i class="icon-award"></i>R 2</span>
<span class="badge _br"><i class="icon-star"></i>4.5</span></figure></a><div class="novel-stats"><i class="icon-book-open"></i>
 1,432 Chapters</span></div></li><a href="?page=2">2</a><a href="?page=9">9</a>"""
NF_NOVEL = """<h1 itemprop="name" class="novel-title text2row">Sword &amp; Moon</h1><div class="author"><span>Author:</span>
<a href="/author/x" class="property-item"><span itemprop="author">Moon Blade</span></a>, <a href="/author/y"
class="property-item"><span itemprop="author"> 月刃</span></a> </div><strong class="nub">4.5</strong>
<div class="header-stats"><span><strong><i class="icon-book-open"></i> 1432</strong><small>Chapters</small></span>
<span><strong><i class="icon-eye"></i> 17.3M</strong><small>Views</small></span>
<span><strong><i class="icon-bookmark"></i> 19K</strong><small>Bookmarked</small></span>
<span> <strong class="completed">Completed</strong> <small>Status</small></span></div>
<a href="/genre-xianxia/sort-new/status-all/all-novel" title="Xianxia" class="property-item">Xianxia</a>
<p class="latest">Reviews from 533 readers</p>
<div class="summary"><h4>Summary</h4><div class="content expand-wrapper"><p>He picks up a sword.</p><div class="expand">
<a class="tag" href="/tags/weak-to-strong/order-popular" rel="tag">Weak to Strong</a>"""


def test_novelfire_list_and_novel():
    from bookkeeper.sites.novelfire import parse_list, parse_novel
    books, last = parse_list(NF_LIST)
    assert last == 9 and books[0].sid == "sword-moon" and books[0].title == "Sword & Moon"
    assert books[0].rating == 9.0 and books[0].chapters == 1432 and books[0].cover.endswith("/server-1/sword-moon.jpg")
    n = parse_novel("sword-moon", NF_NOVEL)
    assert n.authors == ["Moon Blade"] and n.origin == "cn" and n.is_translation and n.status == "completed"
    assert (n.views, n.likes, n.votes, n.chapters) == (17_300_000, 19_000, 533, 1432)
    assert n.tags == ["Xianxia", "Weak to Strong"] and n.description == "He picks up a sword."


# ----- GoodNovel
def gn_page(state):
    return f"<script>window.__INITIAL_STATE__={json.dumps(state)};(function(){{}})()</script>"


GN_BOOK = {"bookId": "31", "bookName": "The Survival Manual", "pseudonym": "Ada", "bookResourceUrl": "The-Survival-Manual_31",
           "ratings": 9.9, "chapterCount": 990, "totalWords": 726209, "viewCountDisplay": "210.1K",
           "writeStatus": "ONGOING", "genreNames": ["Apocalypse"], "newTagsNames": ["System", "First Person POV"],
           "novelType": "TRANSLATION", "language": "ENGLISH", "freeBook": 0, "pornographic": 0, "mature": 0,
           "ctime": "2026-01-27 20:10:05", "lastChapterTime": "2026-11-22 19:00:26", "chargeChapterNum": 7,
           "introduction": "Disaster strikes."}


def test_goodnovel_list_chapters_and_text():
    from bookkeeper.sites.goodnovel import GoodNovel
    pages = {
        "https://www.goodnovel.com/stories/Romance-novels": gn_page({"Browse": {"bookList": [GN_BOOK], "totalPage": 1}}),
        "https://www.goodnovel.com/book/The-Survival-Manual_31": gn_page({"Catalog": {"catalogs": [
            {"id": 5, "chapterName": "Chapter 1", "unlock": True, "chapterResourceUrl": "Chapter-1_5"},
            {"id": 6, "chapterName": "Chapter 2", "unlock": False, "chapterResourceUrl": "Chapter-2_6"}]}}),
        "https://www.goodnovel.com/book/The-Survival-Manual_31/Chapter-1_5": gn_page(
            {"bookCapter": {"chapterData": {"price": 0, "charge": 0, "content": "\"Ah!\"\n\nShe woke up."}}}),
    }
    site = GoodNovel(FakeHttp(pages))
    state = {"gi": 0}
    b = next(site.discover(state))[0]
    assert b.sid == "31" and b.authors == ["Ada"] and b.words == 726209 and b.views == 210_100 and b.complete
    assert b.tags == ["Apocalypse", "System", "First Person POV"] and b.is_translation and b.access == "partial"
    assert b.status == "ongoing" and b.created_at == "2026-01-27" and b.updated_at == "2026-11-22"
    ref = {"sid": "31", "extra": b.extra}
    chs = site.chapters(ref)
    assert [(c.id, c.free) for c in chs] == [("5", True), ("6", False)]
    assert site.chapter_text(ref, chs[0]) == "\"Ah!\"\nShe woke up."


# ----- Litmarket
LM_LIST = """<div class="swiper-pagination"></div><div class="item" data-book-id="77">
<div class="price-stickers"><div class="sticker read-price _discount "><i class="lmfont-book"></i> 109 &#8381; </div></div>
<img class="img bookCardSkeleton" width="152" src="/storage/books/77.jpg" />
<div class="book-ebook-status"><span><i class="lmfont-book menu-icon"> </i>Закончена </span></div>
<div class="card-title"><a
   href="https://litmarket.ru/books/nevernyy">Неверный</a></div>
<div class="author"> <a itemprop="author" itemscope href="/ayrin-p1">Айрин Лакс</a> </div>
<div class="card-cycle"><div><span>Цикл:</span><a href="/c">Генералы #3</a></div></div>
<span class="rating-total-wrap">(<span class="rating-total">666</span>)</span><span class="libraries-count">(3622)</span>
<div class="tags"> <a href="https://litmarket.ru/books/tag/%D0%B1" class="label">#бывшие</a> </div>
<div itemprop="about" class="card-description"> — Убирайся!<br /> Час назад. </div>
<a href="https://litmarket.ru/books/genres/modern_love_novel" onclick='x'> Современный любовный роман </a>
<span>Создана:</span> <time>
   19.11.2026 </time>
<i class="lmfont-pages" aria-hidden="true"></i>
   <span>189 стр</span>
<i class="lmfont-views" aria-hidden="true"></i>
   32k
</div>
<ul class="pagination"><a href="https://litmarket.ru/books/ebooks?page=10836">10836</a></ul>
<div class="card-author"><a itemprop="author" href="/other">Другой автор</a></div>
<span class="adult-warning">18+</span>"""


def test_litmarket_cards():
    from bookkeeper.sites.litmarket import parse_list
    books, last = parse_list(LM_LIST)
    b = books[0]
    assert last == 10836 and b.sid == "77" and b.title == "Неверный" and b.authors == ["Айрин Лакс"]
    assert b.tags == ["Современный любовный роман", "бывшие"] and not b.adult and b.access == "partial"
    assert (b.likes, b.pop_raw, b.views, b.status, b.created_at) == (666, 3622, 32_000, "completed", "2026-11-19")
    assert b.extra["series"] == "Генералы #3" and b.extra["pages"] == 189 and b.complete


# ----- Prodaman
PM_CARD = """<div style="display:table;width:100%;" class="uii-grid-a basic-products-list-item adv-1">
<img src="https://www.prodaman.ru/c.jpg" class="sam-list-pic scale" />
<p class="blog-title"><a href="/Ivan-Petrov/books/Drakon">Дракон</a></p>
<span class="nan" title="Рейтинг: 4.50 * 6">&#9734;</span><strong><a href="/Ivan-Petrov">Иван Петров</a></strong>
<p class="blog-text"> Жил-был дракон.... <a class="more more-items" href="/x">подробнее</a></p>
<p class="blog-info"><strong class="adult18" title="18">18+</strong></p>
<p class="blog-info"><span style="float:right"><span class='inprocess-text'>В процессе написания<br/>для всех</span></span>
<span>Размер: <strong>0,99</strong> алк / <strong>72000</strong> знаков / <strong>3</strong> стр</span></p>
<p class="blog-info">Категории: <span><a href="/books/Fentezi/"><strong>Фэнтези</strong></a></span></p>
<p class="blog-info"> <a href="/x">19 просмотров</a> | <a href="/x">0 комментариев</a> | <a href='/x'>4 в избранном</a></p>
<p class="blog-info"> Хэштег: <a href="?tag=%D0%B4">#драконы_и_люди</a> </p></div></div></div>
<div style="" class="ui-single-block-a ui-table-grid"></div><a href="/books/?sortby=-1&amp;page=1034">1034</a>"""
PM_READER = """<p class="status">Показано
        <strong>1</strong> из <strong>2</strong> страниц</p>
<div class="blog-text noselect reader-box obamacare" onmousedown="return false;">Первая строка.<br />Вторая.</div>"""


def test_prodaman_list_and_reader():
    from bookkeeper.sites.prodaman import Prodaman, parse_list
    books, last = parse_list(PM_CARD)
    b = books[0]
    assert last == 1034 and b.sid == "Ivan-Petrov/Drakon" and b.authors == ["Иван Петров"] and b.rating == 9.0
    assert b.adult and b.status == "ongoing" and b.access == "free" and b.words == 10000 and b.likes == 4
    assert b.tags == ["Фэнтези", "драконы и люди"]
    site = Prodaman(FakeHttp({"https://prodaman.ru/Ivan-Petrov/books/Drakon?nav=ok": PM_READER}))
    chs = site.chapters({"sid": "Ivan-Petrov/Drakon"})
    assert [c.id for c in chs] == ["1", "2"]
    assert site.chapter_text({"sid": "Ivan-Petrov/Drakon"}, chs[0]) == "Первая строка.\nВторая."


# ----- Litgorod
LG_BOOK = """<script type="application/ld+json">{"@type": "Book", "name": "Она попала!", "url": "u",
"image": "https://litgorod.ru/api/v1/images/covers/a.jpg", "description": "Шаг — и я дома.",
"author": {"@type": "Person", "name": "Наталья"}, "genre": ["Фэнтези", "Любовное фэнтези", "Фэнтези"],
"keywords": ["дракон", "истинная пара"], "dateModified": "2026-11-22", "offers": {"price": "127.00"},
"interactionStatistic": [{"interactionType": "https://schema.org/LikeAction", "userInteractionCount": 402}]}</script>
<div class="b-book_adult_old"> 16+ </div><div
   class="b-book_item__status b-book_item__status-1">
   <div class="_text"> В процессе написания </div></div>
<div class="b-book_item__cycle"> Цикл <a href="/c"><b>Она попала!</b></a></div>
<div data-tooltip="Просмотры &#183; 70163" class="b"></div><div data-tooltip="Библиотеки &#183; 3075" class="b"></div>
<div data-tooltip="Количество знаков &#183; 72000" class="b"></div>"""


def test_litgorod_sitemaps_and_book_pages():
    from bookkeeper.sites.litgorod import Litgorod
    pages = {"https://litgorod.ru/sitemap.xml": "<sitemapindex><sitemap><loc>https://litgorod.ru/sitemap_1.xml</loc>"
                                                 "</sitemap><sitemap><loc>https://litgorod.ru/sitemap_2.xml</loc></sitemap>",
             "https://litgorod.ru/sitemap_1.xml": "<url><loc>https://litgorod.ru/blogs/x</loc></url>",
             "https://litgorod.ru/sitemap_2.xml": "<url><loc>https://litgorod.ru/books/view/7</loc></url>"
                                                  "<url><loc>https://litgorod.ru/books/view/9</loc></url>",
             "https://litgorod.ru/books/view/7": LG_BOOK}
    site = Litgorod(FakeHttp(pages))
    state = {}
    batches = list(site.discover(state))
    b = batches[0][0]
    assert len(batches) == 1 and b.sid == "7" and state["full_done"] and state["max_id"] == 9  # book 9 is gone
    assert b.title == "Она попала!" and b.authors == ["Наталья"] and b.status == "ongoing" and b.age_rating == "16+"
    assert b.tags == ["Фэнтези", "Любовное фэнтези", "дракон", "истинная пара"] and b.access == "partial"
    assert (b.likes, b.views, b.pop_raw, b.words) == (402, 70163, 3075, 10000) and b.extra["series"] == "Она попала!"


# ----- Bookriver
BR_ITEM = {"id": 47743, "slug": "vera-mest", "name": "Месть", "authors": [{"name": "Вера Ветрова"}], "age": "16+",
           "annotation": "— Лен, это что?", "genres": [{"name": "Современный любовный роман"}],
           "tags": [{"name": "измена"}], "statusComplete": "complete", "symbols": 72000, "free": False,
           "coverImages": [{"sizeType": "s", "url": "small.jpg"}, {"sizeType": "original", "url": "big.jpg"}]}


def test_bookriver_list_and_details():
    from bookkeeper.sites.bookriver import Bookriver

    def page(state):
        return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps({"props": {"pageProps": {"state": state}}})}</script>'
    detail = {**BR_ITEM, "counters": {"views": 2242, "likes": 5, "readNow": 100, "readLater": 17},
              "createdAt": "2026-11-12T10:00:00+00:00", "cycle": {"name": "Мужчины"}}
    site = Bookriver(FakeHttp({
        "https://bookriver.ru/genre": page({"pagesFilter": {"genre": {"books": [BR_ITEM]}},
                                            "pagination": {"total": 48, "perPage": 24}}),
        "https://bookriver.ru/book/vera-mest": page({"book": {"bookPage": detail}})}))
    state = {}
    b = next(site.discover(state))[0]
    assert b.sid == "47743" and b.cover == "big.jpg" and b.words == 10000 and b.status == "completed"
    assert b.tags == ["Современный любовный роман", "измена"] and b.access == "partial"
    d = site.details({"sid": "47743", "extra": b.extra})
    assert (d.views, d.likes, d.pop_raw, d.created_at, d.extra["series"]) == (2242, 5, 117, "2026-11-12", "Мужчины")


# ----- NovelKlo
NK_BOOK = """<header><a href="/fandom/bts">BTS</a></header><footer>site</footer>
<script type="application/ld+json">{"@type": "Book", "name": "Яр", "description": "Лихо.", "inLanguage": "uk",
"author": [{"@type": "Person", "name": "Яна"}], "datePublished": "2026-07-01T14:47:41Z", "genre": ["Драма"],
"additionalProperty": {"@type": "PropertyValue", "name": "wordCount", "value": 179228}}</script>
<h1 class="x">Яр</h1><p class="m">174<!-- --> <!-- -->розділи</p>
<a class="t" href="/tag/kokhannia">кохання</a><a class="f" href="/fandom/original-world">Свій світ</a>"""


def test_novelklo_book_page():
    from bookkeeper.sites.novelklo import parse_book
    b = parse_book("609", NK_BOOK)
    assert b.title == "Яр" and b.authors == ["Яна"] and b.words == 179228 and b.chapters == 174 and not b.adult
    assert b.tags == ["Драма", "кохання", "fandom:Свій світ"] and b.created_at == "2026-07-01"  # not the menu's BTS
    gated = parse_book("610", NK_BOOK.replace("<h1", "<h2>Ця книга має вікове обмеження</h2><h1"))
    assert gated.adult and gated.age_rating == "18+"


# ----- Fanfics.me and Ranobe.me
FF_ENTRY = """<div id="fic_251082" class="FicTable FicTable_First"><table class="FicTbl"><tr><td colspan="4">
<div class="FicTable_Title"> <h4><a href="/fic251082">Мисс Дюрандаль</a>&nbsp;<span class="small gen">(джен)</span></h4>
<div class="FicTable_Stat"><span class="Views" title="Количество просмотров 8 564" style="x">8.6k</span>
<span class="ReadersCount" title="Количество читателей 193" style="x">193</span>
<a><span class="DateUpdate" title="Опубликовано 07.10.2026, изменено 22.11.2026" style="x">22.11.2026</span></a></div>
</div></td></tr><tr><td class="FicTbl_sammary">Героиня открыла глаза.</td><td class="FicTbl_meta">
<b>Автор:</b>&nbsp;<span data-show-member="1"><a class="user" href="/user1">Shafotka</a></span> <br>
<b>Фандом:</b>&nbsp;<span data-show-fandom="2"><a href="/fandom2">Гарри Поттер</a></span> <br>
<b>Персонажи:</b>&nbsp;<a href="/character1">Гарри Поттер</a><br> <b>Рейтинг:</b>&nbsp;NC-17 <br>
<b>Жанры:</b>&nbsp;Фэнтези, AU <br><b>Размер:</b>&nbsp;Макси | 72 000 знаков <br>
<b>Статус:</b>&nbsp;<span class="red">В&nbsp;процессе</span><br><b>Предупреждения:</b>&nbsp;ООС, AU<br>
<b>События:</b>&nbsp;<a href="/find?keyword=9588">Чужая душа в одном из персонажей</a></td></tr></table></div>
<a href="/find?page=3806#fics">3806</a>"""
FF_READ = """<ul class="FicContents"><li><b>Главы:</b></li><li><a href="/read.php?id=251082&chapter=0#start_read">Глава 1</a></li>
<li><a href="/read.php?id=251082&chapter=1#start_read">Глава 2</a></li></ul>
<table><tr><td class="chNav r"></td></tr></table><div class="ReadContentCenter"><div class="ReadContent"><h2>Глава 1</h2>
<div class="chapter activeurl" id="c0"><a name="c0p1"></a> <p class="fict" id="c0p1">Дом не любил свет.</p>
<p class="fict" id="c0p2">Гарри сидел.</p></div></div></div><td class="chNav r">next</td>"""


def test_fanficsme_entry_chapters_and_text():
    from bookkeeper.sites.fanficsme import FanficsMe, parse_find
    books, last = parse_find(FF_ENTRY)
    b = books[0]
    assert last == 3806 and b.sid == "251082" and b.authors == ["Shafotka"] and b.age_rating == "NC-17" and b.adult
    assert (b.views, b.likes, b.words, b.status) == (8564, 193, 10000, "ongoing") and b.complete
    assert b.tags[:5] == ["джен", "Макси", "Фэнтези", "AU", "ООС"] and "fandom:Гарри Поттер" in b.tags
    assert "Чужая душа в одном из персонажей" in b.tags and b.created_at == "2026-10-07" and b.updated_at == "2026-11-22"
    site = FanficsMe(FakeHttp({"https://fanfics.me/read.php?chapter=0&id=251082": FF_READ}))
    chs = site.chapters({"sid": "251082"})
    assert [(c.id, c.title) for c in chs] == [("0", "Глава 1"), ("1", "Глава 2")]
    assert site.chapter_text({"sid": "251082"}, chs[0]) == "Дом не любил свет.\nГарри сидел."


def test_ranobeme_catalog():
    from bookkeeper.sites.fanficsme import parse_ranobe_catalog
    page = ('<a href="/catalog?page=30">30</a><div id="fic_297" class="FicTable"><div class="FicTable_Cover">'
            '<a href="/ranobe297"><img src="/images/covers/x.jpg"></a></div><div class="FicTable_Title">'
            '<a href="/ranobe297">Верховный Маг</a></div><span class="ChaptersCount" title="x">4510</span>'
            '<span class="uptodate" data-time="1790764492">x</span><div class="FicTable_Description">Дерек.'
            '<div class="FicTable_Genres"><a href="/catalog/genre/15">16+</a>, <a href="/catalog/genre/7">Фэнтези</a></div>')
    books, last = parse_ranobe_catalog(page)
    b = books[0]
    assert last == 30 and b.title == "Верховный Маг" and b.chapters == 4510 and b.age_rating == "16+"
    assert b.tags == ["Фэнтези"] and b.cover == "https://ranobe.me/images/covers/x.jpg" and b.updated_at == "2026-09-30"


# ----- Sufficient Velocity
SV_FORUM = """<div class="structItem structItem--thread js-threadListItem-1" data-author="Ithillid">
<i class="structItem-status structItem-status--sticky"></i><div class="structItem-title">
<a href="/threads/catalog.1/">Catalog</a></div><a href="/threads/catalog.1/threadmarks" data-xf-click="overlay">Words: 160</a>
</div><div class="structItem structItem--thread js-threadListItem-2" data-author="Lermis">
<div class="structItem-title"><a href="/threads/operation-eclipse.161055/" class="" data-tp-primary="on">Operation ECLIPSE</a></div>
<li class="structItem-startDate"><a href="/x"><time class="u-dt" datetime="2026-11-14T10:46:44-0400">x</time></a></li>
<a href="/threads/operation-eclipse.161055/threadmarks" data-xf-click="overlay">Words: 101k</a>
<a href="/f?tags[0]=mass" class="labelLink tagItem tagItem--cat_7 "><i class="fa--xf far fa-globe" title="Setting"></i> mass effect </a>
<a href="/f?tags[0]=original" class="labelLink tagItem tagItem--cat_7 "><i class="fa" title="Setting"></i> original </a>
<a href="/f?tags[0]=action" class="labelLink tagItem tagItem--cat_4 "><i class="fa" title="Genre"></i> action </a>
<div class="structItem-cell structItem-cell--meta" title="Thread reaction score: 88"><dl><dt>Replies</dt> <dd> 78 </dd></dl>
<dl><dt>Views</dt><dd>821</dd></dl></div><time class="structItem-latestDate u-dt" datetime="2026-11-20T10:31:58-0400">x</time>
</div><div class="structItem structItem--thread js-threadListItem-3" data-author="Talk">
<div class="structItem-title"><a href="/threads/chat.3/">Chat</a></div></div>
<a href="/forums/user-fiction.2/page-497">497</a>"""
SV_READER = """<h1 class="p-title-value">Operation ECLIPSE</h1><dl><dt>Watchers</dt> <dd>19</dd></dl>
<dl><dt>Threadmarks</dt> <dd> 62 </dd></dl>
<a class="tagItem tagItem--cat_7"><i class="fa" title="Setting"></i> mass effect<br>(video game series) </a>
<article class="threadmarkListingHeader-extraInfoChild message-body"><div class="bbWrapper">A planet goes missing.</div>
</article><article class="message message--post hasThreadmark" data-author="Lermis">
<span id="threadmark-1" class="threadmarkLabel threadmarkLabel--unread" title="t">Prologue</span>
<div class="bbWrapper">I woke up on the ship.</div></article>
<a href="/threads/operation-eclipse.161055/reader/page-6">6</a>"""


def test_sufficientvelocity_forum_and_reader():
    from bookkeeper.sites.sufficientvelocity import SufficientVelocity, parse_forum, parse_reader
    books, last = parse_forum(SV_FORUM)
    assert last == 497 and [b.sid for b in books] == ["161055"]  # the sticky and the thread without threadmarks go
    b = books[0]
    assert b.title == "Operation ECLIPSE" and b.authors == ["Lermis"] and (b.words, b.views, b.likes) == (101_000, 821, 88)
    assert b.tags == ["fandom:mass effect", "Original", "action"] and b.partial_tags
    assert b.created_at == "2026-11-14" and b.updated_at == "2026-11-20" and b.extra["replies"] == 78
    r = parse_reader(SV_READER)
    assert r["description"] == "A planet goes missing." and r["threadmarks"] == 62 and r["pages"] == 6
    assert r["posts"] == [("Prologue", "I woke up on the ship.")]
    site = SufficientVelocity(FakeHttp({"https://forums.sufficientvelocity.com/threads/operation-eclipse.161055/reader/":
                                        SV_READER}))
    ref = {"sid": "161055", "extra": {"slug": "operation-eclipse"}}
    d = site.details(ref)
    assert d.tags == ["fandom:mass effect (video game series)"] and d.chapters == 62 and d.description
    assert [c.id for c in site.chapters(ref)] == [str(n) for n in range(1, 7)]
    assert site.opening_text(ref) == ["I woke up on the ship."]
