"""All sites Bookkeeper knows about."""
from .ao3 import Ao3
from .authortoday import AuthorToday
from .base import Site
from .booknet import Booknet
from .bookriver import Bookriver
from .fanficsme import FanficsMe, RanobeMe
from .fanmtl import FanMtl
from .fantlab import Fantlab
from .ficbook import Ficbook
from .ficdb import Ficdb
from .flibusta import Flibusta
from .freewebnovel import FreeWebNovel
from .goodnovel import GoodNovel
from .hardcover import Hardcover
from .kubikus import KubikusForum
from .litgorod import Litgorod
from .litmarket import Litmarket
from .litmir import LitMir
from .litvek import Litvek
from .litnet import Litnet
from .novelfire import NovelFire
from .novelklo import NovelKlo
from .prodaman import Prodaman
from .ranobehub import RanobeHub
from .ranobelib import RanobeLib
from .ranobes import Ranobes
from .royallib import RoyalLib
from .rulate import Rulate
from .rulit import RuLit
from .samlib import Samlib
from .scryer import Scryer
from .squidgeworld import SquidgeWorld
from .sufficientvelocity import SufficientVelocity
from .sunset import Sunset
from .wattpad import Wattpad
from .webnovel import WebNovel
from .wtrlab import WtrLab
from .wuxiaclick import WuxiaClick

SITES: dict[str, type[Site]] = {cls.id: cls for cls in (
    RanobeLib, AuthorToday, Litnet, Flibusta, WuxiaClick, Wattpad, RanobeHub, Ranobes, Samlib, Rulate, Ficbook, WebNovel, RoyalLib, LitMir, RuLit, Litvek, WtrLab, FreeWebNovel, FanMtl,
    Ao3, SquidgeWorld, Scryer, Hardcover, Ficdb, KubikusForum,
    Booknet, Litmarket, Prodaman, Litgorod, Bookriver, FanficsMe, RanobeMe, NovelKlo, Fantlab,
    NovelFire, GoodNovel, Sunset, SufficientVelocity)}

# Sites on the list that don't have a connector yet, and why.
_WORKS_HERE = "Your site test worked from this computer. Connector coming next."
_CHECK = "Shows a bot check. The test now opens Waterfox so you can pass it: press Test again."
_BLOCKS_BOTS = ("Blocks programs like Bookkeeper with Cloudflare (your own Waterfox works). Bookkeeper doesn't get "
                "around such checks, so it can't collect this site.")
_ANUBIS = ("Its “are you a bot?” check (Anubis) stops programs that pretend to be browsers. Like SquidgeWorld, it "
           "would probably let Bookkeeper in if Bookkeeper said what it is, but that needs your OK for this site.")
_MANGA = "Manga, for the manga part of the plan (Bookkeeper collects books for now). "
PLANNED = [
    {"id": "royalroad", "name": "Royal Road", "home": "https://www.royalroad.com", "reason": _CHECK},
    {"id": "novelupdates", "name": "NovelUpdates (tags only)", "home": "https://www.novelupdates.com", "reason": _CHECK},
    {"id": "scribblehub", "name": "Scribble Hub", "home": "https://www.scribblehub.com", "reason": _BLOCKS_BOTS},
    {"id": "fanfiction", "name": "FanFiction.net", "home": "https://www.fanfiction.net",
     "reason": _BLOCKS_BOTS + " Its catalog comes in through Scryer (above)."},
    {"id": "fictionpress", "name": "FictionPress", "home": "https://www.fictionpress.com",
     "reason": ("FanFiction.net's sister site for original fiction. Its lists open, but its story pages show programs "
                "a Cloudflare check, and Bookkeeper doesn't get around such checks.")},
    {"id": "spacebattles", "name": "SpaceBattles", "home": "https://forums.spacebattles.com",
     "reason": ("Sufficient Velocity's sister forum. Its forum lists open, but its story threads show programs a "
                "Cloudflare check. Ficdb (above) lists many of its stories with tags.")},
    {"id": "questionablequesting", "name": "Questionable Questing", "home": "https://forum.questionablequesting.com",
     "reason": "Runs the same forum software as Sufficient Velocity, and its threads open. Connector coming next."},
    {"id": "litsovet", "name": "Litsovet", "home": "https://litsovet.ru",
     "reason": ("Has tags and a detailed classifier, but its robots.txt keeps programs off its tag pages and every "
                "list page after the first, so there's no allowed way through its catalog.")},
    {"id": "livelib", "name": "LiveLib", "home": "https://www.livelib.ru",
     "reason": ("Readers' tags for published books, but its book pages answer programs with a DDoS-Guard block. "
                "Bookkeeper doesn't get around such blocks.")},
    {"id": "litres", "name": "Litres", "home": "https://www.litres.ru",
     "reason": ("Tags on every book, but it sits behind DDoS-Guard and its robots.txt keeps programs off search and "
                "every address with a “?”, so only its sitemaps would do. Not written yet.")},
    {"id": "storygraph", "name": "The StoryGraph", "home": "https://thestorygraph.com", "reason": _BLOCKS_BOTS},
    {"id": "librarything", "name": "LibraryThing", "home": "https://www.librarything.com", "reason": _BLOCKS_BOTS},
    {"id": "romanceio", "name": "Romance.io", "home": "https://www.romance.io", "reason": _BLOCKS_BOTS},
    {"id": "goodreads", "name": "Goodreads", "home": "https://www.goodreads.com",
     "reason": "Its robots.txt keeps programs off its book, search and API pages, and it has had no public API since 2020."},
    {"id": "honeyfeed", "name": "Honeyfeed", "home": "https://www.honeyfeed.fm", "reason": _BLOCKS_BOTS},
    {"id": "ranobesnet", "name": "Ranobes (English)", "home": "https://ranobes.net",
     "reason": "The English Ranobes answers programs with a bot check. Bookkeeper doesn't get around such checks."},
    {"id": "literotica", "name": "Literotica (18+)", "home": "https://www.literotica.com", "reason": _BLOCKS_BOTS},
    {"id": "adastra", "name": "Ad Astra (AO3 software)", "home": "https://www.adastrafanfic.com", "reason": _ANUBIS},
    {"id": "cfaarchive", "name": "CFA Archive", "home": "https://www.cfaarchive.org", "reason": _ANUBIS},
    {"id": "superlove", "name": "Superlove (AO3 software)", "home": "https://superlove.sayitditto.net",
     "reason": "Its robots.txt asks every program to stay off the whole site."},
    {"id": "isfdb", "name": "ISFDB", "home": "https://www.isfdb.org",
     "reason": ("Readers' tags for science fiction and fantasy, but its robots.txt asks programs to wait 1,000 seconds "
                "between pages. Its weekly database download has the tags too: that's the way, not written yet.")},
    {"id": "tvtropes", "name": "TV Tropes", "home": "https://tvtropes.org",
     "reason": ("Trope lists for every work. Its pages open to programs, but long lists are split over many subpages "
                "and its texts may only be reused non-commercially. Not written yet.")},
    {"id": "syosetu", "name": "Shōsetsuka ni Narō (Japanese)", "home": "https://syosetu.com",
     "reason": ("The Japanese originals of many translated web novels, 1.27 million, with authors' keywords, through "
                "an official API. Waiting for matching originals to their translations and for translated tags.")},
    {"id": "kakuyomu", "name": "Kakuyomu (Japanese)", "home": "https://kakuyomu.jp",
     "reason": "Japanese web novels with tags (robots.txt keeps programs off chapters). Waits for the same as Narō."},
    {"id": "jjwxc", "name": "JJWXC (Chinese)", "home": "https://www.jjwxc.net",
     "reason": "Chinese web novels with content tags. Waits for the same as Narō."},
    {"id": "novelpia", "name": "Novelpia (Korean)", "home": "https://novelpia.com",
     "reason": "Its robots.txt asks every program to stay off the whole site."},
    {"id": "wlnupdates", "name": "WLNUpdates", "home": "https://www.wlnupdates.com",
     "reason": "An open NovelUpdates-like database with an API, but it answered with server errors (HTTP 500) when tested."},
    {"id": "openlibrary", "name": "Open Library", "home": "https://openlibrary.org",
     "reason": ("Shows programs a “verify you're human” page, and its robots.txt keeps them off search and the API. "
                "Its monthly data downloads could work, but they hold mostly publishing details.")},
    {"id": "vndb", "name": "VNDB (visual novels)", "home": "https://vndb.org",
     "reason": ("Asks programs not to crawl its pages, but has a free API and database downloads that a connector "
                "could use. Visual novels, not books.")},
    {"id": "mangalib", "name": "MangaLib (manga)", "home": "https://mangalib.me",
     "reason": _MANGA + "It runs on the same API as RanobeLib, so most of that connector carries over."},
    {"id": "remanga", "name": "ReManga (manga)", "home": "https://remanga.org",
     "reason": _MANGA + "Genres and categories; its robots.txt keeps programs off its API, so it would be read page by page."},
    {"id": "mangadex", "name": "MangaDex (manga)", "home": "https://mangadex.org",
     "reason": _MANGA + ("Tags through an open API, but the API shows programs that pretend to be browsers a check; "
                         "saying what Bookkeeper is would need your OK.")},
    {"id": "mangaupdates", "name": "MangaUpdates (manga and novels)", "home": "https://www.mangaupdates.com",
     "reason": _MANGA + ("Thousands of reader-voted categories, light novels included, through an official API, "
                         "which answered with errors (HTTP 429 and 502) when tested.")},
    {"id": "anilist", "name": "AniList (anime, manga, light novels)", "home": "https://anilist.co",
     "reason": _MANGA + ("Ranked tags with spoiler marks through a free API. Its terms forbid collecting its data in "
                         "bulk, so it can only look up books one by one; commercial use needs a licence.")},
    {"id": "shikimori", "name": "Shikimori (anime, manga, ranobe)", "home": "https://shikimori.one",
     "reason": _MANGA + ("Russian database with genres and an API for registered apps (robots.txt keeps crawlers off "
                         "/api).")},
    {"id": "myanimelist", "name": "MyAnimeList (anime, manga, light novels)", "home": "https://myanimelist.net",
     "reason": _MANGA + "Its official API needs an app ID; the unofficial Jikan API didn't answer when tested."},
]
