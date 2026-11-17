"""All sites Bookkeeper knows about."""
from .ao3 import Ao3
from .authortoday import AuthorToday
from .base import Site
from .fanmtl import FanMtl
from .ficbook import Ficbook
from .ficdb import Ficdb
from .flibusta import Flibusta
from .freewebnovel import FreeWebNovel
from .hardcover import Hardcover
from .kubikus import KubikusForum
from .litmir import LitMir
from .litvek import Litvek
from .litnet import Litnet
from .ranobehub import RanobeHub
from .ranobelib import RanobeLib
from .ranobes import Ranobes
from .royallib import RoyalLib
from .rulate import Rulate
from .rulit import RuLit
from .samlib import Samlib
from .scryer import Scryer
from .squidgeworld import SquidgeWorld
from .wattpad import Wattpad
from .webnovel import WebNovel
from .wtrlab import WtrLab
from .wuxiaclick import WuxiaClick

SITES: dict[str, type[Site]] = {cls.id: cls for cls in (
    RanobeLib, AuthorToday, Litnet, Flibusta, WuxiaClick, Wattpad, RanobeHub, Ranobes, Samlib, Rulate, Ficbook, WebNovel, RoyalLib, LitMir, RuLit, Litvek, WtrLab, FreeWebNovel, FanMtl,
    Ao3, SquidgeWorld, Scryer, Hardcover, Ficdb, KubikusForum)}

# Sites on the list that don't have a connector yet, and why.
_WORKS_HERE = "Your site test worked from this computer. Connector coming next."
_CHECK = "Shows a bot check. The test now opens Waterfox so you can pass it: press Test again."
_BLOCKS_BOTS = ("Blocks programs like Bookkeeper with Cloudflare (your own Waterfox works). Bookkeeper doesn't get "
                "around such checks, so it can't collect this site.")
PLANNED = [
    {"id": "royalroad", "name": "Royal Road", "home": "https://www.royalroad.com", "reason": _CHECK},
    {"id": "novelupdates", "name": "NovelUpdates (tags only)", "home": "https://www.novelupdates.com", "reason": _CHECK},
    {"id": "scribblehub", "name": "Scribble Hub", "home": "https://www.scribblehub.com", "reason": _BLOCKS_BOTS},
    {"id": "fanfiction", "name": "FanFiction.net", "home": "https://www.fanfiction.net",
     "reason": _BLOCKS_BOTS + " Its catalog comes in through Scryer (above)."},
    {"id": "storygraph", "name": "The StoryGraph", "home": "https://thestorygraph.com", "reason": _BLOCKS_BOTS},
    {"id": "librarything", "name": "LibraryThing", "home": "https://www.librarything.com", "reason": _BLOCKS_BOTS},
    {"id": "romanceio", "name": "Romance.io", "home": "https://www.romance.io", "reason": _BLOCKS_BOTS},
    {"id": "openlibrary", "name": "Open Library", "home": "https://openlibrary.org",
     "reason": ("Shows programs a “verify you're human” page, and its robots.txt keeps them off search and the API. "
                "Its monthly data downloads could work, but they hold mostly publishing details.")},
    {"id": "vndb", "name": "VNDB (visual novels)", "home": "https://vndb.org",
     "reason": ("Asks programs not to crawl its pages, but has a free API and database downloads that a connector "
                "could use. Visual novels, not books.")},
]
