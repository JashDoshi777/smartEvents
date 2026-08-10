"""
LiveIQ — BookMyShow Event Scraper (Competitor Intelligence)
No public API exists for BookMyShow. Read-only scraping of public event
listing pages — the same category of data collection any competitor
intelligence tool in this space does (see ARCHITECTURE doc's own
"BookMyShow Scraper: Playwright + BS4" plan).

IMPORTANT — BookMyShow runs Cloudflare bot protection and WILL return 403
"Attention Required" after a burst of rapid requests (confirmed empirically:
4 requests within ~10s triggered it). This module is intentionally
sequential with real delays between city requests — do not parallelize
city scraping or reduce REQUEST_DELAY_SECONDS without re-verifying against
a fresh IP, or the scraper will get blocked.

Each event card on a BMS city listing page is a single <a href="/events/...">
containing 4 lines of text: title, venue, category, price. Category comes
directly from BMS's own taxonomy (e.g. "Concerts", "Stand up Comedy",
"Art Exhibitions") which is more reliable than keyword-guessing.
"""

import asyncio
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import re

import structlog
from playwright.async_api import async_playwright

logger = structlog.get_logger()

BASE_URL = "https://in.bookmyshow.com/explore/events-{slug}"
SOURCE = "bookmyshow"

# Only slugs empirically verified to return real event listings (not a
# Cloudflare block or an empty/error page) are included. Multi-word cities
# need their real BMS slug confirmed individually before being added here —
# guessing wrong slugs is what triggered the Cloudflare block during testing.
CITY_SLUGS: Dict[str, str] = {
    "Mumbai": "mumbai",
    "Delhi NCR": "national-capital-region-ncr",  # confirmed via BMS's own site footer link
    "Bengaluru": "bengaluru",
    "Pune": "pune",
    "Hyderabad": "hyderabad",
    "Chennai": "chennai",
    "Kolkata": "kolkata",
    "Ahmedabad": "ahmedabad",
    "Jaipur": "jaipur",
    "Chandigarh": "chandigarh",
    "Kochi": "kochi",
    "Indore": "indore",
}

CATEGORY_MAP = {
    "concerts": "music",
    "music shows": "music",
    "stand up comedy": "comedy",
    "comedy shows": "comedy",
    "plays": "theatre",
    "performances": "theatre",
    "sports": "sports",
    "workshops": "workshop",
    "food and drinks": "dining",
    "art exhibitions": "experience",
    "exhibitions": "experience",
    "kids": "experience",
    "meetups": "workshop",
    "conferences": "workshop",
    "spirituality": "experience",
    "talks": "workshop",
    "screening": "movie",
}

REQUEST_DELAY_SECONDS = (8, 15)  # random delay range between city requests
DETAIL_PAGE_DELAY_SECONDS = (4, 8)  # delay between per-event detail page fetches

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_DETAIL_DATE_RE = re.compile(
    r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})\b", re.IGNORECASE
)
_DETAIL_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(AM|PM)", re.IGNORECASE)


def _parse_detail_date(body_text: str) -> Optional[datetime]:
    """Extract the event's real date+time from its detail page body text."""
    lines = [l for l in body_text.split("\n") if l.strip()]
    for i, line in enumerate(lines):
        m = _DETAIL_DATE_RE.search(line)
        if not m:
            continue
        day, month, year = int(m.group(1)), _MONTHS[m.group(2).lower()[:3]], int(m.group(3))
        hour, minute = 0, 0
        # Time is usually the very next non-empty line.
        if i + 1 < len(lines):
            t = _DETAIL_TIME_RE.search(lines[i + 1])
            if t:
                hour = int(t.group(1)) % 12
                minute = int(t.group(2))
                if t.group(3).upper() == "PM":
                    hour += 12
        try:
            return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


async def _fetch_event_date(page, detail_url: str) -> Optional[datetime]:
    try:
        resp = await page.goto(detail_url, wait_until="domcontentloaded", timeout=15000)
        if resp is not None and resp.status == 403:
            logger.warning("bookmyshow_scraper: detail page blocked (403)", url=detail_url)
            return None
        await page.wait_for_timeout(1500)
        body = await page.inner_text("body")
        return _parse_detail_date(body)
    except Exception as exc:
        logger.warning("bookmyshow_scraper: detail date fetch failed", url=detail_url, error=str(exc))
        return None
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _parse_price(price_text: str) -> tuple[Optional[float], Optional[float]]:
    nums = re.findall(r"[\d,]+", price_text.replace("₹", ""))
    if not nums:
        return None, None
    val = float(nums[0].replace(",", ""))
    return val, val


def _parse_card_text(text: str) -> Optional[Dict[str, Any]]:
    """
    BMS event cards render as a 4-line text block:
      line 0: event title
      line 1: venue (often "Venue Name: City" or "Venue Name, Area")
      line 2: category (BMS's own taxonomy, e.g. "Concerts")
      line 3: price (e.g. "₹ 499 onwards")
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) < 4:
        return None

    title, venue_line, category_raw, price_text = lines[0], lines[1], lines[2], lines[3]
    price_min, price_max = _parse_price(price_text)
    venue_name = venue_line.split(":")[0].split(",")[0].strip()
    category = CATEGORY_MAP.get(category_raw.strip().lower(), "music")

    return {
        "title": title,
        "venue_name": venue_name,
        "venue_line": venue_line,
        "category_raw": category_raw,
        "category": category,
        "ticket_price_min": price_min,
        "ticket_price_max": price_max,
    }


async def scrape_city(
    city_name: str,
    max_events: int = 30,
    fetch_real_dates: bool = False,
    max_date_fetches: int = 8,
) -> List[Dict[str, Any]]:
    """
    Scrape one city's BookMyShow /explore/events-{slug} listing page.
    Returns [] (not an exception) if the slug is unverified, blocked, or
    the page returns no parseable events — callers should treat an empty
    result as "no data available", not as proof no events exist.

    BMS listing cards don't include a date — only the per-event detail page
    does. fetch_real_dates=True visits up to max_date_fetches detail pages
    (sequentially, with delay) to backfill event_date; events beyond that
    cap are returned with event_date=None rather than guessed, and it's off
    by default since it multiplies request volume against a Cloudflare-
    protected site.
    """
    slug = CITY_SLUGS.get(city_name)
    if not slug:
        logger.warning("bookmyshow_scraper: no verified slug for city, skipping", city=city_name)
        return []

    events: List[Dict[str, Any]] = []
    url = BASE_URL.format(slug=slug)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=USER_AGENT)
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            if resp is not None and resp.status == 403:
                logger.error(
                    "bookmyshow_scraper: blocked by Cloudflare (403) — back off and retry later",
                    city=city_name, url=url,
                )
                return []

            await page.wait_for_timeout(3000)

            links = await page.query_selector_all('a[href*="/events/"]')
            seen_titles = set()

            for link in links[:max_events]:
                try:
                    text = (await link.inner_text()).strip()
                    href = await link.get_attribute("href")
                    parsed = _parse_card_text(text)
                    if not parsed or not href:
                        continue
                    if parsed["title"] in seen_titles:
                        continue
                    seen_titles.add(parsed["title"])

                    external_id = href.rstrip("/").split("/")[-1]
                    events.append({
                        "external_id": external_id,
                        "source": SOURCE,
                        "title": parsed["title"],
                        "category": parsed["category"],
                        "booking_url": href,
                        "venue_name": parsed["venue_name"],
                        "city": city_name,
                        "ticket_price_min": parsed["ticket_price_min"],
                        "ticket_price_max": parsed["ticket_price_max"],
                        "event_date": None,  # backfilled below if fetch_real_dates
                        "status": "upcoming",
                        "scraped_at": datetime.now(timezone.utc),
                    })
                except Exception as exc:
                    logger.warning("bookmyshow_scraper: card parse failed", error=str(exc))
                    continue

            if fetch_real_dates:
                for i, ev in enumerate(events[:max_date_fetches]):
                    ev["event_date"] = await _fetch_event_date(page, ev["booking_url"])
                    if i < min(len(events), max_date_fetches) - 1:
                        await asyncio.sleep(random.uniform(*DETAIL_PAGE_DELAY_SECONDS))

            logger.info("bookmyshow_scraper: city scraped", city=city_name, count=len(events))

        except Exception as exc:
            logger.error("bookmyshow_scraper: page load failed", city=city_name, error=str(exc))
        finally:
            await browser.close()

    return events


async def scrape_all_cities(
    cities: Optional[List[str]] = None,
    fetch_real_dates: bool = True,
    max_date_fetches: int = 8,
) -> List[Dict[str, Any]]:
    """
    Scrape BookMyShow listings for all (or a subset of) verified cities,
    strictly sequentially with a randomized delay between each city to
    avoid tripping Cloudflare's rate-based bot detection.

    fetch_real_dates defaults to True here because event_date is a NOT NULL
    column on Event — without it, every scraped row gets silently dropped
    by upsert_scraped_events (an earlier version of this pipeline shipped
    with this off by default and inserted zero events on every scheduled
    run without ever raising an error).
    """
    targets = [c for c in (cities or list(CITY_SLUGS.keys())) if c in CITY_SLUGS]
    all_events: List[Dict[str, Any]] = []

    for i, city in enumerate(targets):
        city_events = await scrape_city(
            city, fetch_real_dates=fetch_real_dates, max_date_fetches=max_date_fetches
        )
        all_events.extend(city_events)

        if i < len(targets) - 1:
            delay = random.uniform(*REQUEST_DELAY_SECONDS)
            logger.debug("bookmyshow_scraper: pacing delay", seconds=round(delay, 1))
            await asyncio.sleep(delay)

    return all_events
