"""All sites Bookkeeper knows about."""
from .authortoday import AuthorToday
from .base import Site
from .flibusta import Flibusta
from .kubikus import KubikusForum
from .litnet import Litnet
from .ranobelib import RanobeLib
from .wattpad import Wattpad
from .wuxiaclick import WuxiaClick

SITES: dict[str, type[Site]] = {cls.id: cls for cls in (RanobeLib, AuthorToday, Litnet, Flibusta, WuxiaClick, Wattpad, KubikusForum)}

# Sites on the list that don't have a connector yet, and why.
_CLOUDFLARE = "Showed a bot check to the server Bookkeeper was built on. Press Test to try it from your computer."
_BLOCKS_SERVER = "Blocked the server Bookkeeper was built on. Press Test to try it from your computer."
PLANNED = [
    {"id": "ficbook", "name": "Ficbook", "home": "https://ficbook.net", "reason": _CLOUDFLARE},
    {"id": "scribblehub", "name": "Scribble Hub", "home": "https://www.scribblehub.com", "reason": _CLOUDFLARE},
    {"id": "rulate", "name": "Rulate", "home": "https://tl.rulate.ru", "reason": _BLOCKS_SERVER},
    {"id": "webnovel", "name": "WebNovel", "home": "https://www.webnovel.com", "reason": _CLOUDFLARE},
    {"id": "ranobehub", "name": "RanobeHub", "home": "https://ranobehub.org", "reason": "Not built yet. A test from your computer helps."},
    {"id": "ranobes", "name": "Ranobes", "home": "https://ranobes.com", "reason": "Not built yet. A test from your computer helps."},
    {"id": "fanfiction", "name": "FanFiction.net", "home": "https://www.fanfiction.net", "reason": _CLOUDFLARE},
    {"id": "ao3", "name": "Archive of Our Own", "home": "https://archiveofourown.org",
     "reason": "Was down for maintenance. Press Test once it is back."},
    {"id": "novelupdates", "name": "NovelUpdates (tags only)", "home": "https://www.novelupdates.com",
     "reason": _CLOUDFLARE},
    {"id": "samlib", "name": "Samlib", "home": "http://samlib.ru", "reason": "Didn't answer the server Bookkeeper was built on. Press Test to try it from your computer."},
    {"id": "royalroad", "name": "Royal Road", "home": "https://www.royalroad.com", "reason": _CLOUDFLARE},
    {"id": "royallib", "name": "RoyalLib", "home": "https://royallib.com", "reason": _BLOCKS_SERVER},
    {"id": "rulit", "name": "RuLit", "home": "https://www.rulit.me", "reason": "Not built yet. A test from your computer helps."},
    {"id": "litmir", "name": "LitMir", "home": "https://litmir.club", "reason": "Not built yet. A test from your computer helps."},
    {"id": "litvek", "name": "Litvek", "home": "https://litvek.com", "reason": "Not built yet. A test from your computer helps."},
]
