"""All sites Bookkeeper knows about."""
from .authortoday import AuthorToday
from .base import Site
from .flibusta import Flibusta
from .litnet import Litnet
from .ranobelib import RanobeLib
from .wattpad import Wattpad
from .wuxiaclick import WuxiaClick

SITES: dict[str, type[Site]] = {cls.id: cls for cls in (RanobeLib, AuthorToday, Litnet, Flibusta, WuxiaClick, Wattpad)}

# Sites on the list that don't have a connector yet, and why.
_CLOUDFLARE = "Shows a bot check to my test server; needs a test run from your computer first."
_BLOCKS_SERVER = "Blocks my test server outright; needs a test run from your computer first."
PLANNED = [
    {"id": "ficbook", "name": "Ficbook", "home": "https://ficbook.net", "reason": _CLOUDFLARE},
    {"id": "scribblehub", "name": "Scribble Hub", "home": "https://www.scribblehub.com", "reason": _CLOUDFLARE},
    {"id": "rulate", "name": "Rulate", "home": "https://tl.rulate.ru", "reason": _BLOCKS_SERVER},
    {"id": "kubikus", "name": "Kubikus (+ forum recommendations)", "home": "https://www.kubikus.ru",
     "reason": "Coming next."},
    {"id": "webnovel", "name": "WebNovel", "home": "https://www.webnovel.com", "reason": _CLOUDFLARE},
    {"id": "ranobehub", "name": "RanobeHub", "home": "https://ranobehub.org", "reason": "Coming next."},
    {"id": "ranobes", "name": "Ranobes", "home": "https://ranobes.com", "reason": "Coming next."},
    {"id": "fanfiction", "name": "FanFiction.net", "home": "https://www.fanfiction.net", "reason": _CLOUDFLARE},
    {"id": "ao3", "name": "Archive of Our Own", "home": "https://archiveofourown.org",
     "reason": "Was refusing requests (maintenance). Will be added when it is back."},
    {"id": "novelupdates", "name": "NovelUpdates (tags only)", "home": "https://www.novelupdates.com",
     "reason": _CLOUDFLARE},
    {"id": "samlib", "name": "Samlib", "home": "http://samlib.ru", "reason": "Didn't answer my test server."},
    {"id": "royalroad", "name": "Royal Road", "home": "https://www.royalroad.com", "reason": _CLOUDFLARE},
    {"id": "royallib", "name": "RoyalLib", "home": "https://royallib.com", "reason": _BLOCKS_SERVER},
    {"id": "rulit", "name": "RuLit", "home": "https://www.rulit.me", "reason": "Coming next."},
    {"id": "litmir", "name": "LitMir", "home": "https://litmir.club", "reason": "Coming next."},
    {"id": "litvek", "name": "Litvek", "home": "https://litvek.com", "reason": "Coming next."},
]
