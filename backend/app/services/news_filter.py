"""Title-level news filter that removes homonym noise (pure, no network).

An article counts toward `news_mentions_7d` only if its TITLE
  1. contains the entity's full name as whole words (case-insensitive; accents folded), AND
  2. contains at least one entity-type context term (singer, album, concert, IPL, film, box office ...).
Generic names (single common words / given names: King, Fighter, Jawan, Animal, Queen ...) are stricter:
  * the name must appear with the entity's own capitalisation (rejects "king of the jungle", "a jawan was killed"),
  * the title needs >= 2 distinct context terms, or 1 STRONG term (box office, concert, album, trailer, IPL ...),
    or the entity's Wikipedia disambiguator (e.g. "film" from "Jawan (film)"),
  * it must not be followed by "of" ("King of the jungle"), and when preceded by a capitalised word ("Burger King",
    "Stephen King") it needs >= 2 context terms ("Shah Rukh Khan Jawan film trailer" passes).
Confidence: 'strict' (non-generic name), 'generic_filtered' (generic name, >=1 title passed),
'ambiguous_skipped' (generic name, nothing passed -> caller stores NULL, never 0).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

# Single-word names that are ordinary words/given names; extend as audits find more.
GENERIC_NAMES = {
    "king", "queen", "fighter", "jawan", "animal", "pathaan", "sultaan", "baadshah", "divine", "future", "muse", "oasis",
    "soulmate", "sanam", "shubh", "shaan", "karthik", "madonna", "twice", "sade", "ditty", "avial", "chingaari",
    "saawariya", "eastwind", "nirvana", "drake",
   
}
CONTEXT_BY_TYPE = {
    "artist": ["singer", "song", "songs", "album", "concert", "tour", "band", "music", "musician", "rapper", "live", "gig", "track", "single", "bollywood", "performs", "performance", "fans", "lyrics", "video", "composer", "playback", "festival"],
    "comedian": ["comedian", "stand-up", "standup", "comedy", "special", "tour", "show", "netflix", "fans", "video"],
    "movie": ["film", "movie", "box office", "trailer", "bollywood", "teaser", "cast", "release", "ott"],
    "sports_team": ["ipl", "isl", "cricket", "football", "match", "kabaddi", "pkl", "season", "league", "hockey", "win", "beat"],
    "theatre_group": ["theatre", "play", "drama", "show", "staging"],
    "attraction": ["festival", "concert", "tour", "lineup", "line-up", "tickets", "edition"],
}
STRONG_TERMS = {"box office", "concert", "album", "trailer", "ipl", "isl", "tour", "stand-up", "standup", "singer",
                "festival", "lineup", "line-up", "teaser", "rapper", "bollywood", "kabaddi", "pkl"}
_CATEGORY_EXTRA = [("hip-hop", ["rapper", "hip-hop"]), ("hip hop", ["rapper", "hip-hop"]), ("edm", ["dj", "edm"]),
                   ("dj", ["dj", "edm"]), ("ipl", ["ipl"]), ("cricket", ["cricket", "ipl"]), ("football", ["football", "isl"]),
                   ("isl", ["isl", "football"]), ("kabaddi", ["kabaddi", "pkl"])]


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def strip_publisher(title: str) -> str:
    """Google News appends ' - Publisher'."""
    return re.sub(r"\s+-\s+[^-]{2,40}$", "", title or "").strip()


def context_terms(entity_type: Optional[str], category: Optional[str], disambiguator: Optional[str] = None) -> List[str]:
    terms = list(CONTEXT_BY_TYPE.get(entity_type or "", []))
    cat = (category or "").lower()
    for key, extra in _CATEGORY_EXTRA:
        if key in cat:
            terms += [t for t in extra if t not in terms]
    if not terms:
        terms = ["news"]
    if disambiguator:
        terms.append(disambiguator.lower())
    return terms


def is_generic_name(name: str) -> bool:
    n = re.sub(r"[^a-z0-9 ]+", "", _fold(name).lower()).strip()
    return n in GENERIC_NAMES


def disambiguator_of(wikipedia_title: Optional[str]) -> Optional[str]:
    """'Jawan (film)' -> 'film'; the part inside the trailing parentheses, else None."""
    m = re.search(r"\(([^)]+)\)\s*$", wikipedia_title or "")
    if not m:
        return None
    return m.group(1).lower()


def _term_in(term: str, lower_title: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", lower_title) is not None


def title_passes(title: str, name: str, terms: Iterable[str], generic: bool) -> bool:
    t = _fold(strip_publisher(title))
    n = _fold(name).strip()
    if not t or not n:
        return False
    name_pat = r"\s+".join(re.escape(p) for p in n.split())
    flags = 0 if generic else re.IGNORECASE
    matches = list(re.finditer(r"(?<![\w])" + name_pat + r"(?![\w])", t, flags))
    if not matches:
        return False
    low = t.lower()
    hits = {x for x in terms if _term_in(x.lower(), low)}
    if generic:
        if not hits or not (len(hits) >= 2 or hits & STRONG_TERMS):
            return False
        for m in matches:
            if re.match(r"\s+of\b", t[m.end():], re.IGNORECASE):
                continue                              # "King of the jungle"
            before = t[:m.start()].rstrip()
            prev_word = re.findall(r"[\w'-]+$", before)
            glued = bool(prev_word and prev_word[0][:1].isupper() and before[-1:] not in ".:!?\"'(")
            if glued and len(hits) < 2:
                continue                              # "Burger King ... concert": part of a longer capitalised name
            return True
        return False
    return bool(hits)


@dataclass
class FilterResult:
    count: Optional[int]                 # None when ambiguous_skipped
    confidence: str
    sample_titles: List[str] = field(default_factory=list)
    candidates: int = 0


def usable_aliases(name: str, aliases: Optional[Iterable[str]]) -> List[str]:
    """Aliases safe to match in headlines: distinct from the name, 3..60 chars, <= 6 words, and single-token aliases
    must not be dictionary words / generic names (they would re-introduce homonym noise)."""
    from app.services.entity_identity import is_generic_name as _dict_generic
    out, seen = [], {re.sub(r"\W+", "", _fold(name).lower())}
    for a in aliases or []:
        a = (a or "").strip()
        k = re.sub(r"\W+", "", _fold(a).lower())
        if not a or k in seen or len(a) < 3 or len(a) > 60 or len(a.split()) > 6:
            continue
        if len(a.split()) == 1 and (_dict_generic(a) or is_generic_name(a) or len(k) < 4):
            continue
        seen.add(k)
        out.append(a)
    return out


def filter_titles(titles: Iterable[str], name: str, entity_type: Optional[str] = None, category: Optional[str] = None,
                  disambiguator: Optional[str] = None, aliases: Optional[Iterable[str]] = None) -> FilterResult:
    """A headline counts if it passes for the full name OR any usable alias (same word-boundary + context rules;
    generic-name strictness applies to an alias when the entity name or the alias is itself generic)."""
    titles = [t for t in titles if t]
    generic = is_generic_name(name)
    terms = context_terms(entity_type, category, disambiguator)
    cands = [(name, generic)] + [(a, generic or is_generic_name(a)) for a in usable_aliases(name, aliases)]
    passing, seen = [], set()
    for t in titles:
        if any(title_passes(t, n, terms, g) for n, g in cands):
            k = re.sub(r"[^a-z0-9]+", " ", _fold(strip_publisher(t)).lower()).strip()
            if k not in seen:
                seen.add(k)
                passing.append(strip_publisher(t)[:120])
    if generic and not passing:
        return FilterResult(None, "ambiguous_skipped", [], len(titles))
    return FilterResult(len(passing), "generic_filtered" if generic else "strict", passing[:3], len(titles))
