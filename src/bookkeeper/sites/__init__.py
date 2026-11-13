"""All sites Bookkeeper knows about."""
from .authortoday import AuthorToday
from .base import Site
from .ficbook import Ficbook
from .flibusta import Flibusta
from .freewebnovel import FreeWebNovel
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
from .wattpad import Wattpad
from .webnovel import WebNovel
from .wtrlab import WtrLab
from .wuxiaclick import WuxiaClick

SITES: dict[str, type[Site]] = {cls.id: cls for cls in (
    RanobeLib, AuthorToday, Litnet, Flibusta, WuxiaClick, Wattpad, RanobeHub, Ranobes, Samlib, Rulate, Ficbook, WebNovel, RoyalLib, LitMir, RuLit, Litvek, WtrLab, FreeWebNovel,
    KubikusForum)}

# Sites on the list that don't have a connector yet, and why.
_WORKS_HERE = "Your site test worked from this computer. Connector coming next."
_CHECK = "Shows a bot check. The test now opens Waterfox so you can pass it: press Test again."
_BLOCKS_BOTS = ("Blocks programs like Bookkeeper with Cloudflare (your own Waterfox works). Bookkeeper doesn't get "
                "around such checks, so it can't collect this site.")
PLANNED = [
    {"id": "royalroad", "name": "Royal Road", "home": "https://www.royalroad.com", "reason": _CHECK},
    {"id": "novelupdates", "name": "NovelUpdates (tags only)", "home": "https://www.novelupdates.com", "reason": _CHECK},
    {"id": "scribblehub", "name": "Scribble Hub", "home": "https://www.scribblehub.com", "reason": _BLOCKS_BOTS},
    {"id": "fanfiction", "name": "FanFiction.net", "home": "https://www.fanfiction.net", "reason": _BLOCKS_BOTS},
    {"id": "ao3", "name": "Archive of Our Own", "home": "https://archiveofourown.org", "reason": _CHECK},
]
