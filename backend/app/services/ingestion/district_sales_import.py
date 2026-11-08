"""
District sales CSV import: strict row validation + conservative fuzzy matching (pure functions, unit-tested).

Columns (header row required, exact names):
  event_title, event_date, city, venue_name, artist_name, category, capacity, tickets_sold, gross_revenue_inr,
  ticket_price_min, ticket_price_max, [source_event_id]
Rows whose event_title starts with 'EXAMPLE' (e.g. 'EXAMPLE—...') are template rows and are always rejected.
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

REQUIRED = ["event_title", "event_date", "city", "venue_name", "artist_name", "category", "capacity", "tickets_sold",
            "gross_revenue_inr", "ticket_price_min", "ticket_price_max"]
OPTIONAL = ["source_event_id"]
CATEGORIES = {"music", "comedy", "sports", "theatre", "movie", "experience", "workshop", "dining", "nightlife"}  # = EventCategory
MAX_FILL = 1.05            # tickets_sold / capacity above this is a data error (comps/oversell tolerance 5%)
MAX_CAPACITY = 500_000
AUTO_LINK_SCORE = 92.0     # >= this AND clearly ahead of the runner-up -> auto-link
AUTO_LINK_MARGIN = 6.0
REVIEW_MIN_SCORE = 70.0    # between REVIEW_MIN_SCORE and AUTO_LINK_SCORE (or ambiguous) -> review queue, never linked
SOURCE = "district_sales"


def norm(s: Any) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"^the ", "", s)


def _num(v: Any, name: str, errors: List[str], integer: bool = False) -> Optional[float]:
    if v is None or str(v).strip() == "":
        errors.append(f"{name} is required")
        return None
    try:
        x = float(str(v).replace(",", "").strip())
    except ValueError:
        errors.append(f"{name} is not a number: {v!r}")
        return None
    if math.isnan(x) or math.isinf(x):
        errors.append(f"{name} is not finite")
        return None
    if integer and x != int(x):
        errors.append(f"{name} must be a whole number: {v!r}")
        return None
    return int(x) if integer else x


def parse_date(v: Any) -> Optional[datetime]:
    t = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(t, fmt)
        except ValueError:
            continue
    return None


def is_example_row(row: Dict[str, Any]) -> bool:
    return str(row.get("event_title") or "").strip().upper().startswith("EXAMPLE")


def validate_row(row: Dict[str, Any], known_cities: Optional[Iterable[str]] = None, today: Optional[date] = None) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """-> (clean row or None, errors). Clean row has typed values + fill_rate (0-1, capped at 1.0)."""
    today = today or date.today()
    errors: List[str] = []
    if is_example_row(row):
        return None, ["template EXAMPLE row (delete it)"]
    title = str(row.get("event_title") or "").strip()
    if not title:
        errors.append("event_title is required")
    when = parse_date(row.get("event_date"))
    if when is None:
        errors.append(f"event_date must be YYYY-MM-DD: {row.get('event_date')!r}")
    elif not (date(2015, 1, 1) <= when.date() <= today + timedelta(days=730)):
        errors.append(f"event_date out of range (2015-01-01 .. +2y): {when.date()}")
    city = str(row.get("city") or "").strip()
    if not city:
        errors.append("city is required")
    elif known_cities is not None:
        kc = {norm(c): c for c in known_cities}
        if norm(city) not in kc:
            errors.append(f"city {city!r} is not a tracked city")
        else:
            city = kc[norm(city)]
    cat = str(row.get("category") or "").strip().lower()
    if cat not in CATEGORIES:
        errors.append(f"category {cat!r} not in {sorted(CATEGORIES)}")
    cap = _num(row.get("capacity"), "capacity", errors, integer=True)
    sold = _num(row.get("tickets_sold"), "tickets_sold", errors, integer=True)
    gross = _num(row.get("gross_revenue_inr"), "gross_revenue_inr", errors)
    pmin = _num(row.get("ticket_price_min"), "ticket_price_min", errors)
    pmax = _num(row.get("ticket_price_max"), "ticket_price_max", errors)
    fill = None
    if cap is not None:
        if not (0 < cap <= MAX_CAPACITY):
            errors.append(f"capacity must be 1..{MAX_CAPACITY}")
        elif sold is not None:
            if sold < 0:
                errors.append("tickets_sold must be >= 0")
            else:
                fill = sold / cap
                if fill > MAX_FILL:
                    errors.append(f"fill {fill:.2f} exceeds {MAX_FILL} (tickets_sold {sold} > capacity {cap})")
    if gross is not None and gross < 0:
        errors.append("gross_revenue_inr must be >= 0")
    if pmin is not None and pmax is not None:
        if pmin < 0 or pmax < 0:
            errors.append("ticket prices must be >= 0")
        elif pmin > pmax:
            errors.append("ticket_price_min > ticket_price_max")
        elif sold and gross is not None and not errors:
            avg = gross / sold
            if pmax > 0 and not (0.3 * pmin <= avg <= 1.5 * pmax):
                errors.append(f"gross/tickets_sold = {avg:.0f} is inconsistent with price range {pmin:.0f}-{pmax:.0f}")
    if errors:
        return None, errors
    sid = str(row.get("source_event_id") or "").strip()
    if not sid:
        sid = "h:" + hashlib.sha1(f"{norm(title)}|{when.date()}|{norm(city)}|{norm(row.get('venue_name'))}".encode()).hexdigest()[:24]
    return {
        "event_title": title, "event_date": when, "city": city, "venue_name": str(row.get("venue_name") or "").strip(),
        "artist_name": str(row.get("artist_name") or "").strip(), "category": cat, "capacity": cap, "tickets_sold": sold,
        "gross_revenue": gross, "ticket_price_min": pmin, "ticket_price_max": pmax,
        "fill_rate": round(min(fill, 1.0), 4), "source_event_id": sid,
    }, []


@dataclass
class Match:
    status: str                      # 'linked' | 'review' | 'none'
    id: Optional[str] = None
    name: Optional[str] = None
    score: float = 0.0
    candidates: List[Tuple[str, str, float]] = field(default_factory=list)   # (id, name, score)


def fuzzy_match(query: str, candidates: Sequence[Tuple[str, Sequence[str]]]) -> Match:
    """candidates: [(id, [name, alias...])]. Auto-link only when the best score >= AUTO_LINK_SCORE and it leads the best
    OTHER candidate by AUTO_LINK_MARGIN; anything between REVIEW_MIN_SCORE and that is a review item; else none."""
    from rapidfuzz import fuzz
    q = norm(query)
    if not q:
        return Match("none")
    scored: List[Tuple[str, str, float]] = []
    for cid, names in candidates:
        best_name, best = None, 0.0
        for n in names:
            nn = norm(n)
            if not nn:
                continue
            sc = 100.0 if nn == q else float(fuzz.WRatio(q, nn))
            # WRatio rewards partial containment; demand a comparable token count for >=92 (avoid "Ali" ~ "Ali Zafar")
            if sc < 100.0 and abs(len(q.split()) - len(nn.split())) > 0 and sc > 91.0:
                sc = 91.0
            if sc > best:
                best_name, best = n, sc
        if best_name is not None:
            scored.append((cid, best_name, round(best, 1)))
    scored.sort(key=lambda t: -t[2])
    if not scored or scored[0][2] < REVIEW_MIN_SCORE:
        return Match("none", candidates=scored[:3])
    top = scored[0]
    runner = scored[1][2] if len(scored) > 1 else 0.0
    # exact duplicates of the same name across different ids are ambiguous
    if top[2] >= AUTO_LINK_SCORE and (top[2] - runner >= AUTO_LINK_MARGIN or (top[2] == 100.0 and runner < 100.0)):
        return Match("linked", top[0], top[1], top[2], scored[:3])
    return Match("review", None, None, top[2], scored[:3])
