"""Sunset (sunset.femslash.club): a femslash archive on AO3's open-source code, about 7,000 works (fan fiction and
original works about women who love women).

Everything works as on AO3 (same pages; its robots.txt lets programs in): Bookkeeper reads the tags you choose
(Settings), most recently updated first, slowly. By default that's the F/F category, which nearly every work on the
archive has, so the whole archive comes in."""
from .ao3 import Ao3

BASE = "https://sunset.femslash.club"
DEFAULT_TAGS = "F/F"


class Sunset(Ao3):
    id = "sunset"
    name = "Sunset"
    home = BASE
    min_interval = 5.0
    note = ("A femslash archive on AO3's software, about 7,000 works. Bookkeeper reads the tags you choose "
            "(Settings), by default F/F, which nearly every work has.")
    extra_settings = {
        "tags": {"label": "Tags or fandoms to collect, comma-separated, as Sunset names them (F/F, a fandom such as "
                          "Original Work, or a tag such as First Person)", "default": DEFAULT_TAGS},
        "pages": {"label": "Pages to read per tag (20 works each, most recently updated first)", "default": "500"},
        "languages": {"label": "Languages to keep (en, ru, uk)", "default": "en, ru, uk"},
    }

    def _tags(self) -> list[str]:
        raw = str(self.settings.get("tags") or DEFAULT_TAGS)
        return [t.strip() for t in raw.split(",") if t.strip()]
