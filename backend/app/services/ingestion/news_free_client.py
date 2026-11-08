"""
Keyless news-mention signal (replaces NewsAPI when it is rate-limited / unconfigured).

Primary  : GDELT 2.0 DOC API  (https://api.gdeltproject.org/api/v2/doc/doc, mode=ArtList, timespan=7d).
           Politeness: <= 1 request / 5.5 s process-wide; on any failure GDELT is put on a 15-minute cooldown.
Fallback : Google News RSS search (hl=en-IN, gl=IN), `when:7d`, counted by <pubDate>.

Disambiguation (homonyms such as the film "Jawan"): the exact name is always quoted, and context words chosen by
entity_type/category are AND-ed in, e.g. "Jawan" (film OR movie OR Bollywood ...). Indian-outlet restriction
(`sourcecountry:IN`) is applied to GDELT for non-international entities. Articles are de-duplicated by normalised title.

`news_mentions_7d` therefore = number of distinct articles in the last 7 days matching that contextual exact-name
query (GDELT caps at 250 per query, Google News RSS at ~100; `capped` is recorded). NULL (None) is returned when no
source answered; a genuine empty result is 0. Every result carries provenance (source, query, retrieved).
Responses are cached on disk for 6 hours.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree

import httpx
import structlog

logger = structlog.get_logger()

UA = "LiveIQ-DataBot/1.0 (internal Zomato District analytics; jash.doshi@zomato.com)"
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GNEWS_URL = "https://news.google.com/rss/search"
CACHE_TTL = 6 * 3600
GDELT_MIN_GAP = 5.5
GNEWS_MIN_GAP = 2.0
GDELT_COOLDOWN = 15 * 60
CACHE_DIR = Path(os.environ.get("LIVEIQ_NEWS_CACHE") or (Path(__file__).resolve().parents[3] / ".cache" / "news_free"))

_CONTEXT = {
    "artist": ["singer", "musician", "concert", "band", "album"],
    "comedian": ["comedian", "stand-up", "comedy", "standup"],
    "movie": ["film", "movie", "Bollywood", "box office", "trailer"],
    "sports_team": ["cricket", "IPL", "football", "match", "kabaddi"],
    "theatre_group": ["theatre", "play", "drama"],
    "attraction": ["festival", "concert", "event", "tour"],
}
_CATEGORY_CONTEXT = [  # (substring of category, context words) - checked before the type default
    ("hip-hop", ["rapper", "hip-hop", "concert"]), ("hip hop", ["rapper", "hip-hop", "concert"]),
    ("edm", ["DJ", "EDM", "festival"]), ("dj", ["DJ", "EDM", "festival"]),
    ("ipl", ["IPL", "cricket"]), ("cricket", ["cricket", "IPL"]), ("isl", ["football", "ISL"]),
    ("football", ["football", "ISL"]), ("kabaddi", ["kabaddi", "PKL"]), ("hockey", ["hockey"]),
]


def context_words(entity_type: Optional[str], category: Optional[str]) -> List[str]:
    cat = (category or "").lower()
    if entity_type in ("artist", "sports_team", None):
        for key, words in _CATEGORY_CONTEXT:
            if key in cat:
                return words
    return _CONTEXT.get(entity_type or "", ["news"])


def _clean_name(name: str) -> str:
    return re.sub(r'["“”]', "", name or "").strip()


def build_query(name: str, entity_type: Optional[str], category: Optional[str] = None,
                is_international: bool = False, source: str = "gdelt", aliases: Optional[List[str]] = None) -> str:
    """Exact quoted name (OR up to 4 usable aliases) + context words (OR group). GDELT: + sourcecountry:IN for domestic entities."""
    ctx = " OR ".join(f'"{w}"' if " " in w or "-" in w else w for w in context_words(entity_type, category))
    names = [_clean_name(name)] + [_clean_name(a) for a in (aliases or [])[:4]]
    nm = f'"{names[0]}"' if len(names) == 1 else "(" + " OR ".join(f'"{n}"' for n in names) + ")"
    q = f'{nm} ({ctx})'
    if source == "gdelt" and not is_international:
        q += " sourcecountry:IN"
    return q


def _norm_title(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").lower()
    t = re.sub(r"\s+-\s+[^-]{2,40}$", "", t)          # strip trailing " - Publisher" (Google News)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


@dataclass
class NewsResult:
    count: Optional[int]
    source: str                      # 'gdelt' | 'google_news_rss'
    query: str
    capped: bool
    retrieved: str
    window_days: int = 7
    sample_titles: List[str] = field(default_factory=list)
    confidence: Optional[str] = None          # 'strict' | 'generic_filtered' | 'ambiguous_skipped' (count None)

    def provenance(self) -> Dict[str, Any]:
        return {"source": self.source, "query": self.query, "retrieved": self.retrieved,
                "window_days": self.window_days, "capped": self.capped,
                "confidence": self.confidence,
                "note": "distinct articles whose TITLE contains the full name + a type context term; keyless (not NewsAPI)"}


# ── parsing (pure, unit-tested against recorded fixtures) ─────────────────────

def parse_gdelt(payload: Any, days: int = 7, now: Optional[datetime] = None, all_titles: bool = False) -> Optional[tuple[int, bool, List[str]]]:
    """GDELT ArtList JSON -> (distinct articles, capped, sample titles). None if the payload is not a result object."""
    if not isinstance(payload, dict):
        return None
    arts = payload.get("articles")
    if arts is None:
        return (0, False, []) if payload == {} else None
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    seen, titles = set(), []
    for a in arts:
        sd = a.get("seendate") or ""
        try:
            when = datetime.strptime(sd, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            if when < cutoff:
                continue
        except ValueError:
            pass
        k = _norm_title(a.get("title") or a.get("url") or "")
        if k and k not in seen:
            seen.add(k)
            titles.append((a.get("title") or "")[:200])
    return len(seen), len(arts) >= 250, (titles if all_titles else titles[:5])


def parse_google_rss(xml_text: str, days: int = 7, now: Optional[datetime] = None, all_titles: bool = False) -> Optional[tuple[int, bool, List[str]]]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return None
    items = root.findall("./channel/item")
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    seen, titles = set(), []
    for it in items:
        try:
            when = parsedate_to_datetime(it.findtext("pubDate") or "")
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            if when < cutoff:
                continue
        except (TypeError, ValueError):
            pass
        title = it.findtext("title") or ""
        k = _norm_title(title)
        if k and k not in seen:
            seen.add(k)
            titles.append(title[:200])
    return len(seen), len(items) >= 100, (titles if all_titles else titles[:5])


# ── cache + politeness ────────────────────────────────────────────────────────

def _cache_get(key: str) -> Optional[dict]:
    p = CACHE_DIR / (key + ".json")
    try:
        d = json.loads(p.read_text())
        if time.time() - d["_ts"] < CACHE_TTL:
            return d["v"]
    except Exception:  # noqa: BLE001
        pass
    return None


def _cache_put(key: str, value: dict) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / (key + ".json")).write_text(json.dumps({"_ts": time.time(), "v": value}))
    except Exception:  # noqa: BLE001
        pass


_gap_lock = {"gdelt": asyncio.Lock(), "gnews": asyncio.Lock()}
_last_call = {"gdelt": 0.0, "gnews": 0.0}
_gdelt_dead_until = 0.0


async def _polite_get(kind: str, url: str, params: dict, gap: float, timeout: float) -> Optional[httpx.Response]:
    async with _gap_lock[kind]:
        wait = gap - (time.monotonic() - _last_call[kind])
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call[kind] = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": UA}, follow_redirects=True) as c:
                return await c.get(url, params=params)
        except httpx.HTTPError as exc:
            logger.warning("news_free request failed", source=kind, error=type(exc).__name__)
            return None


async def _gdelt(query: str, days: int) -> Optional[tuple[int, bool, List[str]]]:
    global _gdelt_dead_until
    if time.monotonic() < _gdelt_dead_until:
        return None
    r = await _polite_get("gdelt", GDELT_URL, {"query": query, "mode": "ArtList", "format": "json", "maxrecords": 250,
                                               "timespan": f"{days}d", "sort": "datedesc"}, GDELT_MIN_GAP, 25.0)
    parsed = None
    if r is not None and r.status_code == 200:
        try:
            parsed = parse_gdelt(r.json(), days, all_titles=True)
        except ValueError:      # plain-text throttle / error message instead of JSON
            parsed = None
    if parsed is None:
        _gdelt_dead_until = time.monotonic() + GDELT_COOLDOWN
        logger.warning("GDELT unavailable/throttled; cooling down", minutes=GDELT_COOLDOWN // 60)
    return parsed


async def _gnews(query: str, days: int) -> Optional[tuple[int, bool, List[str]]]:
    r = await _polite_get("gnews", GNEWS_URL, {"q": f"{query} when:{days}d", "hl": "en-IN", "gl": "IN", "ceid": "IN:en"},
                          GNEWS_MIN_GAP, 20.0)
    if r is None or r.status_code != 200:
        return None
    return parse_google_rss(r.text, days, all_titles=True)


async def fetch_news_mentions(name: str, entity_type: Optional[str] = None, category: Optional[str] = None,
                              is_international: bool = False, days: int = 7,
                              disambiguator: Optional[str] = None, aliases: Optional[List[str]] = None) -> Optional[NewsResult]:
    """Homonym-filtered distinct-article count (title must contain the full name + a context term; see news_filter).
    count is None with confidence 'ambiguous_skipped' for generic names where nothing passed; the whole result is
    None when no keyless source answered."""
    from app.services.news_filter import filter_titles, usable_aliases
    aliases = usable_aliases(name, aliases)
    gq = build_query(name, entity_type, category, is_international, "gdelt", aliases)
    nq = build_query(name, entity_type, category, is_international, "gnews", aliases)
    key = hashlib.sha1(f"v3|{gq}|{days}|{disambiguator}".encode()).hexdigest()
    hit = _cache_get(key)
    if hit:
        return NewsResult(**hit)
    today = datetime.now(timezone.utc).date().isoformat()

    def _f(titles):
        return filter_titles(titles, name, entity_type, category, disambiguator, aliases)

    result: Optional[NewsResult] = None
    g = await _gdelt(gq, days)
    fg = _f(g[2]) if g else None
    if fg and fg.count:
        result = NewsResult(fg.count, "gdelt", gq, g[1], today, days, fg.sample_titles, fg.confidence)
    else:
        n = await _gnews(nq, days)
        fn = _f(n[2]) if n else None
        if fn and fn.count:
            result = NewsResult(fn.count, "google_news_rss", nq, n[1], today, days, fn.sample_titles, fn.confidence)
        else:
            answered = [(src, q, f) for src, q, f in (("gdelt", gq, fg), ("google_news_rss", nq, fn)) if f is not None]
            if answered:
                src, q, f = answered[0]
                skipped = any(x[2].confidence == "ambiguous_skipped" for x in answered)
                result = NewsResult(None if skipped else 0, src, q, False, today, days, [],
                                    "ambiguous_skipped" if skipped else f.confidence)
    if result is not None:
        _cache_put(key, asdict(result))
    return result


# ── backfill (also scheduled as job `news_backfill`) ──────────────────────────

async def backfill_news_mentions(limit: int = 30) -> Dict[str, Any]:
    """Fill news_mentions_7d on each entity's NEWEST entity_metrics row when it is NULL. Small batches; counts logged."""
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as s:
        rows = (await s.execute(text("""
            SELECT e.id, e.name, e.entity_type, e.category, COALESCE(e.is_international, false) AS intl, m.time,
                   e.external_ids->>'wikipedia_title' AS wt, e.name_aliases AS al
            FROM entities e
            JOIN LATERAL (SELECT time, news_mentions_7d, news_confidence FROM entity_metrics WHERE entity_id = e.id
                          ORDER BY time DESC LIMIT 1) m ON true
            WHERE e.status = 'active' AND m.news_mentions_7d IS NULL AND m.news_confidence IS NULL
            ORDER BY m.time ASC LIMIT :n"""), {"n": limit})).mappings().all()
    if not rows:
        return {"rows": 0, "status": "nothing_to_do"}

    updates, failed, by_src, streak = [], 0, {}, 0
    for r in rows:
        from app.services.news_filter import disambiguator_of
        res = await fetch_news_mentions(r["name"], r["entity_type"], r["category"], r["intl"],
                                        disambiguator=disambiguator_of(r["wt"]), aliases=r["al"] or [])
        if res is None:
            failed += 1
            streak += 1
            if streak >= 8:      # both sources are throttling us: stop, retry on the next run
                logger.warning("news backfill: 8 consecutive failures, stopping early")
                break
            continue
        streak = 0
        by_src[res.source] = by_src.get(res.source, 0) + 1
        updates.append({"eid": r["id"], "t": r["time"], "n": res.count, "c": res.confidence,
                        "s": json.dumps(res.sample_titles), "p": json.dumps({"news_mentions_7d": res.provenance()})})
    if updates:
        async with AsyncSessionLocal() as s:
            await s.execute(text("""
                UPDATE entity_metrics SET news_mentions_7d = :n, news_confidence = :c,
                       news_sample_titles = CAST(:s AS jsonb),
                       signal_provenance = COALESCE(signal_provenance, '{}'::jsonb) || CAST(:p AS jsonb)
                WHERE entity_id = :eid AND time = :t AND news_mentions_7d IS NULL AND news_confidence IS NULL"""), updates)
            await s.commit()
    logger.info("news backfill", selected=len(rows), written=len(updates), failed=failed, by_source=by_src)
    return {"rows": len(updates), "selected": len(rows), "failed": failed, "by_source": by_src,
            "status": "complete" if not failed else "partial"}
