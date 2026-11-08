import importlib
import json
import sqlite3
import sys
import time

import pytest


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKKEEPER_DATA", str(tmp_path / "data"))
    from bookkeeper import config
    importlib.reload(config)
    from bookkeeper import db, tags, library, matching, search
    importlib.reload(db); importlib.reload(tags); importlib.reload(matching); importlib.reload(library)
    importlib.reload(search)
    db.init(tmp_path / "test.db")
    return tmp_path


# ---------------------------------------------------------------- the shared tag list
def test_tag_list_is_consistent(env):
    from bookkeeper import tags as T
    assert T.collisions() == []                        # no synonym is listed under two different tags
    assert all(t in T.UK for t in T.TAGS)              # every tag has a Ukrainian name
    assert all(b in T.TAGS for bs in T.RULES.values() for b in bs)
    assert {v[2] for v in T.TAGS.values()} <= set(T.CATEGORY_ORDER)


def test_tags_merge_across_sites_and_languages(env):
    from bookkeeper import tags as T
    assert T.canonical("Special Abilities") == T.canonical("Сверхспособности") == ["special-abilities"]
    assert T.canonical("Slow Romance") == T.canonical("Медленная романтика") == ["slow-burn"]
    assert T.canonical("Враги становятся возлюбленными") == ["enemies-to-lovers"]
    assert T.canonical("Ecchi") == ["ecchi"] and T.canonical("Mature") == ["mature-themes"]   # not "18+"
    assert T.canonical("#ГарриПоттер") == T.canonical("Harry Potter") == ["fandom-harry-potter"]
    assert T.canonical("Саске") == ["саске", "fandom-naruto"]     # the character stays, the fandom is added
    assert T.canonical("Воспоминания из другого мира") == ["past-life-memories"]
    assert "romance" in T.implied({"slow-burn"}) and "reincarnation" in T.implied({"past-life-memories"})
    assert T.info("fantasy")["label_uk"] == "Фентезі"


# ---------------------------------------------------------------- 18+ books
def test_adult_books_are_shown_unless_hidden(env):
    from bookkeeper import db, library, search
    from bookkeeper.sites.base import BookInfo
    library.upsert_book("x", BookInfo(sid="1", url="u", title="Обычная книга"))
    library.upsert_book("x", BookInfo(sid="2", url="u", title="Книга 18+", adult=True))
    library.upsert_book("x", BookInfo(sid="3", url="u", title="Книга с тегом", tags=["Эротика"]))
    titles = lambda p: {b["title"] for b in search.search(p)["books"]}  # noqa: E731
    assert titles({}) == {"Обычная книга", "Книга 18+", "Книга с тегом"}
    assert titles({"adult": "only"}) == {"Книга 18+", "Книга с тегом"}
    db.set_setting("hide_adult", True)
    assert titles({}) == {"Обычная книга"}
    assert all(b["adult"] for b in search.search({"adult": "only"})["books"])


# ---------------------------------------------------------------- downloads made by a browser extension
def test_extension_download_is_picked_up(env, monkeypatch):
    from bookkeeper import config, db, handoff, library
    importlib.reload(handoff)
    from bookkeeper.sites.base import BookInfo
    downloads = env / "Downloads"
    downloads.mkdir()
    (downloads / "old.fb2").write_text("already here")
    monkeypatch.setattr(handoff, "user_downloads_dir", lambda: downloads)
    monkeypatch.setattr(handoff, "open_in_user_browser", lambda url: "Waterfox")
    monkeypatch.setattr(handoff, "_ensure_watcher", lambda: None)
    bid = library.upsert_book("authortoday", BookInfo(sid="7", url="https://author.today/work/7",
                                                        title="Третий Генерал", authors=["Зот"]))
    st = handoff.start(bid)
    assert st["waiting"] and st["folder"] == str(downloads)
    (downloads / "Зот - Третий Генерал.fb2").write_text("<FictionBook/>", encoding="utf-8")
    p = handoff._pending[bid]
    handoff._check(p)          # first look: remember the size
    assert handoff.status(bid)
    handoff._check(p)          # same size again: the download is finished
    assert handoff.status(bid) is None
    row = db.conn().execute("SELECT fmt, state, file FROM downloads WHERE book_id=?", (bid,)).fetchone()
    assert tuple(row) == ("fb2", "done", "Зот - Третий Генерал.fb2")
    assert (config.DOWNLOADS_DIR / row["file"]).read_text(encoding="utf-8") == "<FictionBook/>"


# ---------------------------------------------------------------- accounts
@pytest.mark.skipif(sys.platform != "win32", reason="passwords are encrypted with Windows (DPAPI)")
def test_saved_password_is_encrypted(env):
    from bookkeeper import accounts, config, secret
    importlib.reload(accounts)
    accounts.save_credentials("authortoday", "reader@example.com", "s3cret-pass")
    raw = (config.DATA_DIR / "accounts" / "authortoday.login").read_bytes()
    assert b"s3cret" not in raw and raw.startswith(b"DPAPI")
    assert accounts.credentials("authortoday") == {"login": "reader@example.com", "password": "s3cret-pass"}
    accounts.save_credentials("authortoday", "reader@example.com", None)   # keeps the saved password
    assert accounts.credentials("authortoday")["password"] == "s3cret-pass"
    assert secret.unprotect(secret.protect(b"x")) == b"x"


def test_login_copied_from_waterfox_profile(env, monkeypatch):
    from bookkeeper import accounts
    importlib.reload(accounts)
    from bookkeeper.sites.authortoday import AuthorToday
    profile = env / "profile"
    profile.mkdir()
    con = sqlite3.connect(profile / "cookies.sqlite")
    con.execute("CREATE TABLE moz_cookies(name, value, host, path, isSecure, isHttpOnly, expiry)")
    future, past = int(time.time()) + 86400, int(time.time()) - 86400
    con.executemany("INSERT INTO moz_cookies VALUES(?,?,?,?,?,?,?)", [
        ("LoginCookie", "abc", ".author.today", "/", 1, 1, future),
        ("cf_clearance", "passed-by-your-browser", ".author.today", "/", 1, 1, future),  # never copied
        ("__cf_bm", "z", ".author.today", "/", 1, 1, future),
        ("old", "x", "author.today", "/", 1, 0, past),
        ("other", "y", ".example.com", "/", 0, 0, future)])
    con.commit()
    con.close()
    monkeypatch.setattr(accounts, "user_profile_dir", lambda: profile)
    data = accounts.import_from_user_waterfox(AuthorToday)
    assert [c["name"] for c in data["cookies"]] == ["LoginCookie"] and data["how"] == "waterfox"


# ---------------------------------------------------------------- new sites
class FakePage:
    def __init__(self, text, url="https://example/"):
        self.text, self.url, self.status = text, url, 200


class FakeHttp:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url, **kw):
        for key, text in self.pages.items():
            if key in url:
                return FakePage(text, url)
        raise AssertionError(f"unexpected request {url}")


def test_ranobehub_reads_the_catalog_data_stream(env):
    from bookkeeper.sites.ranobehub import RanobeHub
    flight = ('0:["$","div",null,{"children":[["$","$L30","catalog-1",{"result":{"items":[{"id":3386,"slug":"x",'
              '"title":"Однажды я обнаружил","originalTitle":"Aru hi","description":"Комедия","year":2019,'
              '"status":"В процессе","rating":9.5,"views":"470","chapters":21,"isOriginalWork":false,'
              '"posterUrl":"/api/media/1?size=medium","updatedAt":"$D2026-11-07T10:44:00.000Z","tags":["Комедия"]}],'
              '"total":1,"page":1,"pages":1}}]]}]\n')
    page = f'<script>self.__next_f.push([1,{json.dumps(flight)}])</script>'
    site = RanobeHub(FakeHttp({"/ranobe": page}), {})
    books, pages = site._catalog(1)
    b = books[0]
    assert (b.sid, b.title, b.status, b.views, b.chapters, b.updated_at) == \
        ("3386", "Однажды я обнаружил", "ongoing", 470, 21, "2026-11-07")
    assert b.is_translation and b.tags == ["Комедия"] and pages == 1


def test_ranobes_catalog_card(env):
    from bookkeeper.sites.ranobes import Ranobes
    card = ('<article class="block story shortstory mod-poster"><h2 class="title"><a href="https://ranobes.com/'
            'ranobe/659867-the-landlady.html">Рожденные для богатой жизни</a></h2><strong>3.7</strong>&nbsp;<small>'
            '(<span id="vote-num-id-659867" class="ignore-select">3</span>)</small> <figure class="cover" '
            'style="background-image: url(https://ranobes.com/c.jpg);"></figure><div class="short-desc"> Описание '
            '</div><div class="grey ellipses small"> Комедия, Романтика </div><li class="meta_author" '
            'title="Уникальных просмотров: 1 963">1 963</li></article>')
    site = Ranobes(FakeHttp({"/ranobe/": '<html>' + card}), {})
    b = site._catalog(1)[0]
    assert (b.sid, b.rating, b.votes, b.views, b.tags) == ("659867", 7.4, 3, 1963, ["Комедия", "Романтика"])


def test_rulate_card_reads_numbers_with_thin_spaces(env):
    from bookkeeper.sites.rulate import Rulate
    card = ("<img src='/i/book/1.jpg' alt=''/><p class='book-tooltip'><a href='/book/422?bt_page=search'>Маг на полную "
            "ставку</a><br/><small style='color:#888'>Versatile Mage</small></p><small class='cat'><a href='/search?cat=5'>"
            "Китайские</a></small> <span class=\"label\" rel=\"tooltip\" title=\"Кол-во глав всего / Кол-во платных глав\">"
            "<i class=\"icon-book icon-white\"></i> 2 146 / 300</span> <span class=\"label\" rel=\"tooltip\" "
            "title=\"Рейтинг\"><i class=\"icon-star icon-white\"></i> 4.4 / 2 781</span> <span class=\"label\" "
            "rel=\"tooltip\" title=\"Лайки\"><i class=\"icon-thumbs-up icon-white\"></i> 2 019</span>"
            "<p><em>состояние перевода: <span style=\"color: green;\">Завершён</span></em></p>")
    b = Rulate(FakeHttp({}), {})._card(card)
    assert (b.sid, b.chapters, b.access, b.rating, b.votes, b.likes, b.status, b.origin) == \
        ("422", 2146, "partial", 8.8, 2781, 2019, "completed", "cn")


def test_ficbook_card_and_spam(env):
    from bookkeeper.sites.ficbook import Ficbook
    def card(title, likes, rating="NC-17"):
        return (f'<h3 class="fanfic-inline-title"><a class="visit-link" href="/readfic/abc{likes}">{title}</a></h3>'
                f'<div class="direction-slash direction"><span class="hidden-xs">Слэш</span></div>'
                f'<div class="ds-label ds-label-rating-{rating}">{rating}</div><div class="ds-label ds-label-status-finished">'
                f'</div><span class="js-like-count">{likes}</span><dl><dt>Автор:</dt><dd><a href="/authors/1">Автор</a></dd>'
                f'</dl><dl><dt>Размер:</dt><dd> 41 208 слов, 10 частей</dd></dl><div class="tags"><span>Метки:</span>'
                f'<a href="/tags/1" class="tag ">Драма</a></div>')
    site = Ficbook(FakeHttp({}), {})
    b = site._card(card("Тьма", 12))
    assert (b.sid, b.adult, b.status, b.words, b.chapters, b.likes) == ("abc12", True, "completed", 41208, 10, 12)
    assert b.tags == ["Слэш", "18+", "Драма"]
    assert site._card(card("Buy verified PayPal accounts", 0, "G")) is None


def test_litmir_catalog_card(env):
    from bookkeeper.sites.litmir import LitMir
    card = ('<div class="book_name"><a href="/bd/?b=212477"><span itemprop="name">Платина и шоколад (СИ)</span></a>'
            '</div><span class="orange_desc">9.05</span>&nbsp;(635) <div class="desc_box"><span class="desc1">Автор:'
            '</span><span itemprop="author" class="desc2"> <a href="/a/?id=1">Чацкая Настя</a></span></div><div '
            'class="desc_box"><span class="desc1">Жанр:</span><span class="desc2"><a href="/bs/?g=sg102&hc=1">Эротика'
            '</a>, <a href="/bs/?g=sg103&hc=1">Любовно-фантастические романы</a></span></div><div class="desc_box">'
            '<span class="desc1">Язык книги:</span><span class="desc2"> Русский</span><span class="desc1">Страниц:'
            '</span><span class="desc2"> 203 </span></div><span class="desc1">Книга закончена</span>')
    b = LitMir(FakeHttp({}), {})._card(card)
    assert (b.sid, b.rating, b.votes, b.lang, b.status, b.adult) == ("212477", 9.05, 635, "ru", "completed", True)
    assert b.authors == ["Чацкая Настя"] and b.extra["self_published"]


def test_royallib_captcha_stops_instead_of_retrying(env):
    from bookkeeper.http import Blocked
    from bookkeeper.sites.royallib import RoyalLib
    site = RoyalLib(FakeHttp({"/book/": "<html><title>Проверка</title><script>window.__RLD={}</script>"}), {})
    with pytest.raises(Blocked):
        site.details({"sid": "a/b"})


def test_bilingual_labels_use_the_known_side(env):
    from bookkeeper import tags as T
    assert T.canonical("Naruto / Наруто") == ["fandom-naruto"]
    assert T.canonical("Hurt/Comfort") == ["hurt-comfort"]          # a real slash in a known label stays whole


def test_samlib_splits_a_work_into_chapters(env):
    from bookkeeper.sites.samlib import Samlib
    text = "Владелец заводов\n" + "\n".join(f"Глава {n}\n" + "Текст главы. " * 50 for n in range(1, 4))
    parts = Samlib.split_chapters(text)
    assert [t for t, _ in parts] == ["Глава 1", "Глава 2", "Глава 3"]
    assert Samlib.split_chapters("слово " * 20000)[0][0] == "Часть 1"   # no headings: even parts
