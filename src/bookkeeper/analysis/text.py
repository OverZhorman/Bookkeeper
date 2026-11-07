"""Turning HTML into clean paragraphs, plus language detection."""
import html as _html
import re

_DROP = re.compile(r"(?is)<(script|style|noscript|template|svg|head)\b.*?</\1\s*>")
_BR = re.compile(r"(?i)<br\s*/?>")
_BLOCK = re.compile(r"(?i)</?(p|div|h[1-6]|li|ul|ol|blockquote|section|article|tr|table|hr|pre|dd|dt|dl|"
                    r"header|footer|aside|figure|figcaption|center|title|subtitle|epigraph|poem|stanza|v)\b[^>]*>")
_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t  -​  　]+")


def html_to_text(markup: str) -> str:
    """HTML to plain text, one paragraph per line."""
    if not markup:
        return ""
    s = _DROP.sub(" ", markup)
    s = _BR.sub("\n", s)
    s = _BLOCK.sub("\n", s)
    s = _TAG.sub("", s)
    s = _html.unescape(s)
    return clean_text(s)


def clean_text(text: str) -> str:
    lines = (_SPACES.sub(" ", line).strip() for line in text.replace("\r", "\n").split("\n"))
    return "\n".join(line for line in lines if line)


def paragraphs(text: str) -> list[str]:
    return [p for p in text.split("\n") if p.strip()]


UK_ONLY = re.compile(r"[іїєґІЇЄҐ]")
RU_ONLY = re.compile(r"[ыэъёЫЭЪЁ]")
CYR = re.compile(r"[А-Яа-яЁёІіЇїЄєҐґ]")
LAT = re.compile(r"[A-Za-z]")


EN_WORDS = re.compile(r"\b(the|and|of|to|was|that|with|for|you|his|her|it|in|is)\b", re.I)


def detect_lang(text: str) -> str:
    sample = text[:30000]
    cyr, lat = len(CYR.findall(sample)), len(LAT.findall(sample))
    if lat > cyr:
        words = max(1, len(re.findall(r"[A-Za-z]+", sample)))
        return "en" if len(EN_WORDS.findall(sample)) / words > 0.08 or words < 12 else "other"
    if not cyr:
        return "unknown"
    uk, ru = len(UK_ONLY.findall(sample)), len(RU_ONLY.findall(sample))
    return "uk" if uk > ru * 1.5 and uk > 20 else "ru"


def word_count(text: str) -> int:
    return len(re.findall(r"\w+", text))


def opening_pieces(text: str, enough_words: int = 6000, pieces: int = 3, skip_lines=None) -> list[str]:
    """The opening ~enough_words of a whole book, in a few even pieces (for the narration check, chapter breaks
    don't matter). Short lines before the text starts (title, epigraph, headings) are skipped, and so are lines
    matching `skip_lines` (a site's own notices)."""
    picked, words = [], 0
    for line in text.split("\n"):
        if skip_lines is not None and skip_lines.search(line):
            continue
        if not picked and len(line.split()) < 4:
            continue
        picked.append(line)
        words += len(line.split())
        if words >= enough_words:
            break
    if words < 300:
        return []
    out, chunk, chunk_words, size = [], [], 0, max(1, words // pieces)
    for line in picked:
        chunk.append(line)
        chunk_words += len(line.split())
        if chunk_words >= size and len(out) < pieces - 1:
            out.append("\n".join(chunk))
            chunk, chunk_words = [], 0
    if chunk:
        out.append("\n".join(chunk))
    return out
