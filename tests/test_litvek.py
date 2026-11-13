"""Litvek's pages (markup as the site writes it, made-up books), and Author.Today moving past a listing page that's gone."""
import pytest

from bookkeeper.http import NotFound
from bookkeeper.sites.authortoday import AuthorToday
from bookkeeper.sites.litvek import Litvek

CARD = """<div class="pbook" itemscope="" itemtype="http://schema.org/Book"><table><tbody><tr><td class='ob_cov'>
<a href='/books/111-kniga-ivan-ivanov-test'><img loading='lazy' itemprop='image' class='cover' src='/i/1/111/cover78.jpg'></a></td>
<td class='ob_info ob_infoo'><div class='ob_tit'><a href='/books/111-kniga-ivan-ivanov-test'><h2 itemprop='name'>Тестовая книга (СИ)</h2></a></div>
<div class='ob_avge'><p itemprop='author' itemscope itemtype='http://schema.org/Person'>Автор: <span itemprop='name'> <a class="abt" href="/avtor/1-avtor-ivan-ivanov" >Иван Иванов</a> </span></p>
<p>Жанр: <span itemprop='genre'> <a class='abt' href='/genre/popadanec-zhanr-popadantsyi'>Попаданцы</a>, <a class='abt' href='/genre/love_erotica-zhanr-erotika'>Эротика</a></span></p>
<p>Серия:  <a class="abt" href="/serial/5-seriya-test">Тест #1</a></p><p>Год издания: <span class='black'> - </span></p>
<p>Язык книги: <span class='black'>русский</span></p><p>Страниц: <span class='black'><span itemprop='numberOfPages'>100</span></span></p>
<p>Рейтинг: <span class='black'>оценок: 3 (средняя: <span class='o'>9.5</span>)</span></p></div>
<table><tbody><tr><td class='w200'><a class='ob_read   ' href='/book-read/111-kniga-ivan-ivanov-test-chitat-online'>Читать</a></td></tr></tbody></table>
</td></tr></tbody></table></div>"""
GONE = CARD.replace("111", "222").replace("<a class='ob_read   ' href='/book-read/222-kniga-ivan-ivanov-test-chitat-online'>",
                                          "<span class='ob_read dw_dis  bce' >").replace(
    "</div>\n<table>", "<p class='red'>Доступен ознакомительный фрагмент книги! </p></div>\n<table>")
LISTING = ("<a href='/genre/x?page=2'>2</a> <a href='/genre/x?page=40'>40 »</a>" + CARD + GONE).replace("/genre/x", "/genre/network")
BOOK = """<div>Автор: <a href="/avtor/9-avtor-other">Другой автор</a></div><h1 itemprop="name" data-widget-litres-book>Тестовая книга</h1>
<p itemprop='author' itemscope='' itemtype='http://schema.org/Person'>Автор: <span itemprop='name'> <a class="abt" href="/avtor/1-avtor-ivan-ivanov" data-widget-litres-author>Иван Иванов</a> </span></p>
<p>Жанр: <span itemprop='genre'> <a class='abt' href='/genre/popadanec-zhanr-popadantsyi'>Попаданцы</a></span></p>
<p>Год издания: <span class='black'><span itemprop='datePublished'>2024</span></span></p><p><span class="g">Книга закончена</span></p>
<p>день: <span class='o'>1</span> всего: <span class='o'>1 234</span></p>
<a class='ob_read   ' href='/book-read/111-kniga-ivan-ivanov-test-chitat-online'>Читать онлайн</a>
<tr><td colspan='2'><p class='ob_ann' itemprop='description'><p class="book">Герой попадает в другой мир.</p></p><br></td></tr>
<tr><td class='ob_kw tc' colspan='2'>Ключевые слова: <a href='/keywords/%D0%B0'>гг маг</a> <a href='/keywords/%D0%B1'>академия магии</a> <br><br></td></tr>"""
WORDS = " ".join(["Я открыл глаза и увидел незнакомый потолок, а рядом стояла девушка в странной одежде."] * 40)
READER = ("<div class='read_navi'><a class='mz5' href='?p=2'>2</a></div><div class='btext'><h3 class=\"book\">Иван Иванов\n"
          "Тестовая книга\n</h3>© Иванов И., 2024</p>\n<h3 class='book'>Глава 1\n</h3>" + WORDS + "</p>\n</div></main>")


class FakeHttp:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url, params=None, **kw):
        self.calls.append((url, params))
        key = url + (f"?p={params['p']}" if params and "p" in params else "")
        if key not in self.pages:
            raise NotFound(url)
        return type("P", (), {"text": self.pages[key]})()


def test_litvek_listing_details_and_text():
    site = Litvek(FakeHttp({"https://litvek.com/genre/network_literature-zhanr-samizdat-setevaya-literatura": LISTING,
                            "https://litvek.com/books/111-kniga-ivan-ivanov-test": BOOK,
                            "https://litvek.com/br/111?p=1": READER}))
    books, last = site._list(1)
    assert last == 40 and [b.sid for b in books] == ["111", "222"]
    a, b = books
    assert a.title == "Тестовая книга (СИ)" and a.authors == ["Иван Иванов"] and a.tags == ["Попаданцы", "Эротика"]
    assert a.rating == 9.5 and a.votes == 3 and a.access == "free" and a.adult and a.extra["series"] == "Тест #1"
    assert a.extra["self_published"] and a.url == "https://litvek.com/books/111-kniga-ivan-ivanov-test"
    assert b.access == "partial" and b.extra["fragment"] and b.extra["readable"] is False
    d = site.details({"sid": "111", "extra": a.extra})
    assert d.authors == ["Иван Иванов"]                      # not the author of a book shown above it
    assert d.tags == ["Попаданцы", "гг маг", "академия магии"] and d.status == "completed" and d.views == 1234
    assert d.description == "Герой попадает в другой мир." and d.created_at == "2024-01-01"
    pieces = site.opening_text({"sid": "111", "extra": d.extra})
    assert pieces and pieces[0].startswith("Я открыл глаза") and "©" not in "".join(pieces)
    chapters = site.chapters({"sid": "111", "extra": d.extra})
    assert [c.title for c in chapters] == ["Глава 1"]
    calls = len(site.http.calls)
    assert site.opening_text({"sid": "222", "extra": b.extra}) == [] and len(site.http.calls) == calls  # text taken down


def test_litvek_listing_setting():
    site = Litvek(FakeHttp({}), settings={"listing": "https://litvek.com/genre/fanfiction-zhanr-fanfik?page=3"})
    assert site._listing_path() == "/genre/fanfiction-zhanr-fanfik"
    site.settings = {"listing": "all"}
    assert site._listing_path() == "/"


def test_author_today_moves_past_a_missing_listing_page():
    site = AuthorToday(None)
    tries = []

    def listing(genre, sorting, page):
        tries.append((genre, page))
        if (genre, page) == ("litrpg", 339):
            raise NotFound("https://author.today/work/genre/litrpg")
        return []
    site._listing = listing
    state = {"queue": [["litrpg", "likes"], ["realrpg", "likes"]], "i": 0, "page": 339}
    for _ in range(2):  # the crawler tries again five minutes later, with the same state
        with pytest.raises(NotFound):
            list(site.discover(state))
    list(site.discover(state))  # the third time: on to the next listing
    assert tries[-1] == ("realrpg", 1) and state.get("full_done") and "missing" not in state
