"""
Pure helpers for exact entity identity + signal validation (no network, no DB).

Everything here is deterministic so it can be unit-tested with recorded fixtures.
"""
from __future__ import annotations

import os
import re
import unicodedata
from typing import Iterable, Optional

try:  # rapidfuzz is a declared dependency; degrade gracefully if absent
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover
    fuzz = None

# Entity types for which Last.fm (a music-only service) is meaningless.
MUSIC_TYPES = {"artist"}
NON_MUSIC_TYPES = {"sports_team", "comedian", "movie", "attraction", "festival", "theatre_group"}

INDIA_QID = "Q668"

# Names known (from audit) to collide with common words / unrelated works.
_KNOWN_GENERIC = {
    "king", "fighter", "jawan", "animal", "sultaan", "sultan", "pathaan", "karthik", "shaan", "divine",
    "raftaar", "badshah", "emiway", "prateek", "nucleya", "nikhil", "kabir", "ranveer", "krsna",
    "queen", "dhurandhar", "tiger", "dangal", "kantara", "pushpa", "salaar", "war", "don", "dhoom",
    "sanju", "kalki", "devara", "leo", "vikram", "kaithi", "master", "beast", "ra one", "zero",
    "stree", "raees", "kesari", "pink", "baaghi", "lootera", "tumbbad", "dunki", "bhool bhulaiyaa",
}


def _load_dictionary() -> set[str]:
    p = "/usr/share/dict/words"
    if not os.path.exists(p):
        return set()
    try:
        with open(p, encoding="utf-8", errors="ignore") as f:
            return {w.strip() for w in f if w.strip().islower() and w.strip().isalpha() and len(w.strip()) >= 3}
    except OSError:  # pragma: no cover
        return set()


_DICT: Optional[set[str]] = None


def norm_name(s: str) -> str:
    """Lowercase, strip diacritics/punctuation/spaces: 'Sidhu Moose Wala' == 'Sidhu Moosewala'."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().replace("&", "and")
    s = re.sub(r"^the\s+", "", s.strip())
    return re.sub(r"[^a-z0-9]+", "", s)


def is_generic_name(name: str) -> bool:
    """True if the whole name is a single common English word / known collision-prone title."""
    global _DICT
    n = re.sub(r"[^a-z0-9 ]+", "", unicodedata.normalize("NFKD", name or "").lower()).strip()
    if not n:
        return False
    if n in _KNOWN_GENERIC:
        return True
    if " " in n:
        return False
    if _DICT is None:
        _DICT = _load_dictionary()
    return n in _DICT


def title_similarity(name: str, title: str, aliases: Iterable[str] = ()) -> float:
    """0-100. Best of fuzzy ratio between the entity name/aliases and the channel title;
    100 when the title contains the full normalised name (and name is >=4 chars) or vice-versa."""
    if not title:
        return 0.0
    best = 0.0
    t_norm = norm_name(title)
    for cand in [name, *aliases]:
        if not cand:
            continue
        c_norm = norm_name(cand)
        if not c_norm:
            continue
        if len(c_norm) >= 4 and (c_norm in t_norm):
            best = max(best, 100.0)
            continue
        if fuzz is not None:
            best = max(best, fuzz.token_set_ratio(cand.lower(), title.lower()), fuzz.WRatio(cand.lower(), title.lower()) if len(c_norm) >= 4 else 0)
    return round(float(best), 1)


YT_MATCH_THRESHOLD = 85.0


def youtube_verdict(name: str, aliases: Iterable[str], channel: Optional[dict], source: str) -> dict:
    """channel = {'title':..., 'subscribers':int|None}. source: 'wikidata' | other.
    Returns {'verdict':..., 'similarity':..., 'title':..., 'subscribers':...}"""
    if not channel:
        return {"verdict": "unresolved", "similarity": None}
    sim = title_similarity(name, channel.get("title") or "", aliases)
    ok = sim >= YT_MATCH_THRESHOLD
    if ok and source == "wikidata":
        v = "verified_wikidata"
    elif ok:
        v = "name_match_unverified"
    else:
        v = "title_mismatch"
    return {"verdict": v, "similarity": sim, "title": channel.get("title"), "subscribers": channel.get("subscribers")}


_COUNTRY_TAGS = {
    "india": {"bollywood", "indian", "hindi", "punjabi", "tamil", "telugu", "desi", "indian pop", "indian hip hop",
              "desi hip hop", "bhangra", "carnatic", "hindustani", "sufi", "ghazal", "filmi", "malayalam", "kannada", "bengali", "marathi", "gujarati"},
}


def lastfm_tag_overlap(tags: Iterable[str], expected_genres: Iterable[str], india_expected: bool) -> bool:
    ts = {t.lower() for t in tags}
    if not ts:
        return False
    exp = {g.lower() for g in expected_genres if g}
    for t in ts:
        for g in exp:
            if g and (g in t or t in g):
                return True
    if india_expected and ts & _COUNTRY_TAGS["india"]:
        return True
    return False


def lastfm_verdict(entity_type: str, *, mbid_verified: bool, name_match: bool, generic: bool, tags_ok: bool, resolved: bool) -> str:
    if entity_type not in MUSIC_TYPES:
        return "wrong_type"
    if mbid_verified:
        return "verified_mbid"
    if not resolved:
        return "unresolved"
    if name_match and not generic and tags_ok:
        return "name_verified_tags"
    return "name_unverified"


# Leading demonym in a Wikidata English description ("Pakistani playback singer") -> country label
DEMONYMS = {
    "pakistani": "Pakistan", "american": "United States", "british": "United Kingdom", "english": "United Kingdom",
    "canadian": "Canada", "bangladeshi": "Bangladesh", "sri lankan": "Sri Lanka", "nepalese": "Nepal", "nepali": "Nepal",
    "australian": "Australia", "south korean": "South Korea", "korean": "South Korea", "norwegian": "Norway",
    "swedish": "Sweden", "german": "Germany", "french": "France", "dutch": "Netherlands", "canadian-american": "Canada",
    "emirati": "United Arab Emirates", "singaporean": "Singapore", "scottish": "United Kingdom", "irish": "Ireland",
    "afghan": "Afghanistan", "spanish": "Spain", "italian": "Italy", "jamaican": "Jamaica", "puerto rican": "Puerto Rico",
}


HISTORICAL_INDIA = {"British Raj", "Dominion of India", "Company rule in India", "British India", "Indian Empire"}
# Nepali-language descriptions often label Indian Gorkha/Darjeeling artists; do not let them override a sole P27=India
OVERRIDE_EXEMPT = {"Nepal"}


def description_demonym(desc: Optional[str]) -> Optional[str]:
    """Country implied by the first words of a Wikidata description, or None. 'Indian ...' -> 'India'."""
    d = (desc or "").lower().strip()
    if d.startswith("indian"):
        return "India"
    for k in sorted(DEMONYMS, key=len, reverse=True):
        if d.startswith(k + " ") or d.startswith(k + "-"):
            return DEMONYMS[k]
    return None


def classify_nationality(entity_type: str, p27: list, p495: list, p17: list, description: Optional[str] = None) -> Optional[dict]:
    """Inputs are lists of {'qid','label'} from Wikidata. Returns {'nationality','is_india','via','all','note'} or None
    when Wikidata gives nothing citable.

    Guards against unreliable P27 statements: India does not permit dual citizenship, so P27 = [India, X] is treated as
    a diaspora act (nationality X); and a sole P27 = India that contradicts the item's own description demonym
    ('Pakistani playback singer') defers to the description."""
    demo = description_demonym(description)
    # historical Indian polities count as India (Wikidata often lists them next to India itself)
    p27 = [{"qid": INDIA_QID, "label": "India"} if v.get("label") in HISTORICAL_INDIA else v for v in (p27 or [])]
    _seen = set()
    p27 = [v for v in p27 if not (v["qid"] in _seen or _seen.add(v["qid"]))]
    if p27:
        qids = [v["qid"] for v in p27]
        labels = [v["label"] for v in p27]
        if INDIA_QID in qids:
            others = [v for v in p27 if v["qid"] != INDIA_QID]
            if others and (demo == "India" or all(o["label"] in OVERRIDE_EXEMPT for o in others)):
                return {"nationality": "India", "is_india": True, "via": "P27", "all": labels,
                        "note": "description says Indian; extra P27 values ignored"}
            if others:
                return {"nationality": others[0]["label"], "is_india": False, "via": "P27", "all": labels,
                        "note": "P27 lists India plus another country -> diaspora"}
            if demo and demo != "India" and demo not in OVERRIDE_EXEMPT:
                return {"nationality": demo, "is_india": False, "via": "description", "all": labels,
                        "note": f"P27=India contradicts Wikidata description '{description}'"}
            return {"nationality": "India", "is_india": True, "via": "P27", "all": labels, "note": ""}
        return {"nationality": labels[0], "is_india": False, "via": "P27", "all": labels, "note": ""}
    for pid, vals in (("P495", p495), ("P17", p17)):
        if vals:
            qids = [v["qid"] for v in vals]
            labels = [v["label"] for v in vals]
            if INDIA_QID in qids:
                return {"nationality": "India", "is_india": True, "via": pid, "all": labels, "note": ""}
            return {"nationality": labels[0], "is_india": False, "via": pid, "all": labels, "note": ""}
    return None


def spelling_only_diff(a: str, b: str) -> bool:
    """True if two names differ only by case/diacritics/punctuation/spacing."""
    """True if two names differ only by diacritics/punctuation/spacing (pure case-only changes are NOT counted: they are
    usually deliberate stylisation such as BLACKPINK)."""
    return a != b and a.lower() != b.lower() and norm_name(a) == norm_name(b) and bool(norm_name(a))
