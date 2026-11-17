"""SquidgeWorld Archive (squidgeworld.org): a fan-run archive by Squidge.org on AO3's open-source code, about 105,000
works (mostly fan fiction, some original works).

Its pages sit behind Anubis, an "are you a bot?" check that by default stops programs pretending to be browsers and
lets through programs that say what they are. So on this site Bookkeeper doesn't present itself as a browser: it
sends "Bookkeeper/<version> (personal book catalog)" and gets the normal pages. It doesn't get around the check.
Everything else works as on AO3 (same pages, same robots.txt rules): Bookkeeper reads the tags you choose (Settings),
most recently updated first, slowly."""
from .. import __version__
from .ao3 import Ao3

BASE = "https://squidgeworld.org"
DEFAULT_TAGS = ("Original Works - Others [Unlisted], Original Works - Novel, Original Works - Long Form Prose, "
                "Original Works - Novella, Original Works - Short Form Prose, First Person, LitRPG, Isekai, "
                "Reincarnation, Time Travel")


class SquidgeWorld(Ao3):
    id = "squidgeworld"
    name = "SquidgeWorld Archive"
    home = BASE
    min_interval = 5.0
    user_agent = f"Bookkeeper/{__version__} (personal book catalog)"
    note = ("A fan-run archive on AO3's software. Bookkeeper reads the tags and fandoms you choose (Settings), most "
            "recently updated first. Its “are you a bot?” check lets Bookkeeper in because Bookkeeper says what it is.")
    extra_settings = {
        "tags": {"label": "Tags or fandoms to collect, comma-separated, as SquidgeWorld names them (Original Works - "
                          "Novel, a fandom such as Star Wars - All Media Types, or a tag such as First Person)",
                 "default": DEFAULT_TAGS},
        "pages": {"label": "Pages to read per tag (25 works each, most recently updated first)", "default": "200"},
        "languages": {"label": "Languages to keep (en, ru, uk)", "default": "en, ru, uk"},
    }

    def _tags(self) -> list[str]:
        raw = str(self.settings.get("tags") or DEFAULT_TAGS)
        return [t.strip() for t in raw.split(",") if t.strip()]
