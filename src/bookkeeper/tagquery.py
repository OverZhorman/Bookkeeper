"""The tag search language behind the Tags and Fandoms fields of the library filters.

    romance                  books with the tag. Any name or alias works: Romance, Романтика, Любовь…
    -romance   !romance      books without it (also: NOT romance, НЕ romance)
    romance harem            both (a space, a comma, AND, И, & all mean "and")
    romance | harem          either one (also: OR, ИЛИ, АБО)
    (isekai | reincarnation) -harem      parentheses group things
    ?system                  has the tag, or possibly has it (found in the opening chapters)
    "slow burn"              a name with spaces; known multi-word names also work without quotes
    fandom*                  every tag that starts with "fandom"

Plain tags count only what's certain (the site's own tags, rules, your tags, other copies, the text check);
possible tags from the opening chapters count only with "?"."""
import re
from dataclasses import dataclass, field
from typing import Callable

from . import tags as T

KEYWORDS = {"or": "OR", "или": "OR", "або": "OR", "and": "AND", "и": "AND", "і": "AND", "not": "NOT", "не": "NOT"}
_TOKEN = re.compile(r'\s*(?:(\()|(\))|(\|\||\|)|(&&|&)|(,)|"([^"]*)"?|«([^»]*)»?|([^\s()|&,"«»]+))')
MAX_PHRASE = 6


@dataclass
class Term:
    text: str
    maybe: bool = False
    prefix: bool = False
    ids: list[str] = field(default_factory=list)
    known: bool = True


@dataclass
class Node:
    op: str                                   # term / and / or / not
    items: list = field(default_factory=list)
    term: Term | None = None


def _tokens(text: str) -> list[tuple]:
    """('LP',) ('RP',) ('OR',) ('AND',) ('NOT',) ('MAYBE',) ('WORD', text, bare) — bare = typed without quotes."""
    out, pos = [], 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            break
        pos = m.end()
        lp, rp, bar, amp, comma, q1, q2, word = m.groups()
        if lp:
            out.append(("LP",))
        elif rp:
            out.append(("RP",))
        elif bar:
            out.append(("OR",))
        elif amp or comma:
            out.append(("AND",))
        elif q1 is not None or q2 is not None:
            phrase = (q1 if q1 is not None else q2).strip()
            if phrase:
                out.append(("WORD", phrase, False))
        elif word:
            while word and word[0] in "-!?−":
                out.append(("MAYBE",) if word[0] == "?" else ("NOT",))
                word = word[1:]
            if word:
                out.append(("WORD", word, True))
    return out


Resolver = Callable[[str], list[str]]


def _known(phrase: str, exists: Callable[[str], bool] | None, resolve: Resolver = T.canonical) -> bool:
    ids = resolve(phrase)
    return bool(ids) and all(T.is_known(i) or (exists is not None and exists(i)) for i in ids)


def _merge_phrases(tokens: list[tuple], exists, resolve: Resolver = T.canonical) -> list[tuple]:
    """Join words typed without quotes into a known multi-word name: male lead, гг не ояш, slow burn."""
    out, i = [], 0
    while i < len(tokens):
        tok = tokens[i]
        if tok[0] == "WORD" and tok[2] and tok[1].lower() in KEYWORDS:
            # NOT / НЕ / OR… at the start always work as operators: "не гарем" means "without Harem" here, even
            # though a site tag is called that (write "не гарем" in quotes for the tag).
            out.append((KEYWORDS[tok[1].lower()],))
        elif tok[0] == "WORD" and tok[2]:
            j = i + 1
            while j < len(tokens) and j - i < MAX_PHRASE and tokens[j][0] == "WORD" and tokens[j][2]:
                j += 1
            merged = False
            for end in range(j, i + 1, -1):
                phrase = " ".join(t[1] for t in tokens[i:end])
                if _known(phrase, exists, resolve):
                    out.append(("WORD", phrase, False))
                    i, merged = end, True
                    break
            if merged:
                continue
            kw = KEYWORDS.get(tok[1].lower())
            out.append((kw,) if kw else ("WORD", tok[1], False))
        else:
            out.append(tok)
        i += 1
    return out


class _Parser:
    def __init__(self, tokens):
        self.t, self.i = tokens, 0

    def peek(self):
        return self.t[self.i][0] if self.i < len(self.t) else None

    def take(self):
        self.i += 1
        return self.t[self.i - 1]

    def parse(self) -> Node | None:
        parts = []
        while self.peek() is not None:
            node = self.parse_or()
            if node is not None:
                parts.append(node)
            elif self.peek() is not None:
                self.take()  # a stray ")" or operator: skip it
        if not parts:
            return None
        return parts[0] if len(parts) == 1 else Node("and", parts)

    def parse_or(self):
        items = [self.parse_and()]
        while self.peek() == "OR":
            self.take()
            items.append(self.parse_and())
        items = [x for x in items if x is not None]
        if not items:
            return None
        return items[0] if len(items) == 1 else Node("or", items)

    def parse_and(self):
        items = []
        while self.peek() not in (None, "RP", "OR"):
            if self.peek() == "AND":
                self.take()
                continue
            node = self.parse_unary()
            if node is not None:
                items.append(node)
        if not items:
            return None
        return items[0] if len(items) == 1 else Node("and", items)

    def parse_unary(self):
        kind = self.peek()
        if kind == "NOT":
            self.take()
            inner = self.parse_unary()
            return Node("not", [inner]) if inner is not None else None
        if kind == "MAYBE":
            self.take()
            inner = self.parse_unary()
            _mark_maybe(inner)
            return inner
        if kind == "LP":
            self.take()
            node = self.parse_or()
            if self.peek() == "RP":
                self.take()
            return node
        if kind == "WORD":
            return Node("term", term=Term(self.take()[1]))
        self.take()  # an operator where a tag should be
        return None


def _mark_maybe(node):
    if node is None:
        return
    if node.op == "term":
        node.term.maybe = True
    for child in node.items:
        _mark_maybe(child)


def parse(text: str, exists: Callable[[str], bool] | None = None, resolve: Resolver | None = None) -> Node | None:
    """Parse a query. `exists(tag_id)` says whether a tag id is in the library (for tags that aren't built in);
    `resolve(name)` turns a name into tag ids (default: the shared tag list; the Fandoms field reads names as fandoms)."""
    resolve = resolve or T.canonical
    node = _Parser(_merge_phrases(_tokens(text or ""), exists, resolve)).parse()
    for term in terms(node):
        if term.text.endswith("*") and len(term.text) > 1:
            term.prefix = True
            term.ids = []
            term.known = True
        else:
            term.ids = resolve(term.text)
            term.known = bool(term.ids) and all(T.is_known(i) or (exists is not None and exists(i)) for i in term.ids)
    return node


def terms(node: Node | None) -> list[Term]:
    if node is None:
        return []
    if node.op == "term":
        return [node.term]
    return [t for child in node.items for t in terms(child)]


def to_sql(node: Node | None) -> tuple[str, list]:
    """A WHERE condition on books `b`."""
    if node is None:
        return "1=1", []
    if node.op == "term":
        term = node.term
        source = "" if term.maybe else " AND source != 'maybe'"
        if term.prefix:
            like = re.sub(r"[%_\\]", "", term.text[:-1].lower().replace("ё", "е")) + "%"
            return (f"b.id IN (SELECT book_id FROM book_tags WHERE tag IN (SELECT id FROM tags WHERE id LIKE ? OR "
                    f"ulower(label) LIKE ? OR ulower(label_ru) LIKE ? OR ulower(label_uk) LIKE ?){source})", [like] * 4)
        if not term.ids:
            return "0=1", []
        parts = [f"b.id IN (SELECT book_id FROM book_tags WHERE tag = ?{source})" for _ in term.ids]
        return ("(" + " AND ".join(parts) + ")" if len(parts) > 1 else parts[0]), list(term.ids)
    if node.op == "not":
        sql, args = to_sql(node.items[0])
        return f"NOT ({sql})", args
    pieces = [to_sql(child) for child in node.items]
    joiner = " AND " if node.op == "and" else " OR "
    return "(" + joiner.join(p[0] for p in pieces) + ")", [a for p in pieces for a in p[1]]


def explain(node: Node | None, label: Callable[[str], str], parent: str | None = None) -> str:
    """The query in words: "Romance and not Harem and (Isekai or Reincarnation)"."""
    if node is None:
        return ""
    if node.op == "term":
        t = node.term
        if t.prefix:
            name = f"any tag starting with “{t.text[:-1]}”"
        elif not t.known:
            name = f"“{t.text}” (no such tag yet)"
        else:
            name = " + ".join(label(i) for i in t.ids)
        return f"possibly {name}" if t.maybe else name
    if node.op == "not":
        return "not " + explain(node.items[0], label, "not")
    joiner = " and " if node.op == "and" else " or "
    text = joiner.join(explain(child, label, node.op) for child in node.items)
    # Brackets wherever the reading would otherwise change: "not (A and B)", "A and (B or C)", "(A and B) or C".
    return f"({text})" if parent is not None and parent != node.op else text


def from_lists(must=(), anyof=(), exclude=()) -> str:
    """The old filter fields (must have / any of / exclude) written as a query."""
    def q(tag_id: str) -> str:
        return f'"{tag_id}"' if re.search(r"[\s()|&,\"«»]", tag_id) else tag_id
    parts = [q(t) for t in must]
    if anyof:
        parts.append("(" + " | ".join(q(t) for t in anyof) + ")" if len(anyof) > 1 else q(anyof[0]))
    parts += [f"-{q(t)}" for t in exclude]
    return " ".join(parts)
