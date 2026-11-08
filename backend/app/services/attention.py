"""Pure helpers for weekly Wikipedia attention history (no network, no DB).

Wikimedia daily pageviews (agent=user, access=all-access) are bucketed into ISO weeks (Monday-start, UTC).
Only COMPLETE weeks (Mon..Sun, last day <= yesterday) are ever stored, so a week total is never a partial sum.
The pageviews API omits days with zero views, so a missing day inside a fetched range counts as 0.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

HISTORY_WEEKS = 26


def iso_week_start(d: date) -> date:
    """Monday of the ISO week containing d."""
    return d - timedelta(days=d.weekday())


def last_complete_week_start(today: date) -> date:
    """Monday of the most recent fully elapsed ISO week (its Sunday is <= today-1)."""
    return iso_week_start(today - timedelta(days=7))


def week_range(today: date, weeks: int = HISTORY_WEEKS) -> List[date]:
    """The `weeks` most recent complete ISO weeks, oldest first."""
    last = last_complete_week_start(today)
    return [last - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]


def parse_ts(ts: str) -> date:
    """Wikimedia timestamp 'YYYYMMDD00' -> date."""
    return date(int(ts[0:4]), int(ts[4:6]), int(ts[6:8]))


def daily_from_items(items: Iterable[Mapping]) -> Dict[date, int]:
    out: Dict[date, int] = {}
    for it in items:
        v = it.get("views")
        if v is None or v < 0:
            continue
        d = parse_ts(it["timestamp"])
        out[d] = out.get(d, 0) + int(v)
    return out


def aggregate_weekly(daily: Mapping[date, int], today: date, weeks: int = HISTORY_WEEKS) -> Dict[date, int]:
    """Daily views -> {week_start: total} for each complete week in the window (absent days = 0)."""
    wk = week_range(today, weeks)
    first, last_end = wk[0], wk[-1] + timedelta(days=6)
    out = {w: 0 for w in wk}
    for d, v in daily.items():
        if first <= d <= last_end:
            out[iso_week_start(d)] += v
    return out


def trailing_sum(daily: Mapping[date, int], today: date, days: int) -> int:
    """Sum of the `days` complete UTC days ending yesterday (same definition as collect_free_signals)."""
    end = today - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    return sum(v for d, v in daily.items() if start <= d <= end)


def combine_weeks(en: Optional[Mapping[date, int]], hi: Optional[Mapping[date, int]]) -> List[Tuple[date, Optional[int], Optional[int], int]]:
    """Merge per-project weekly dicts -> [(week, en, hi, total)] (None = project not available for entity)."""
    weeks = sorted(set(en or {}) | set(hi or {}))
    return [(w, (en or {}).get(w) if en is not None else None, (hi or {}).get(w) if hi is not None else None,
             (en or {}).get(w, 0) + (hi or {}).get(w, 0)) for w in weeks]
