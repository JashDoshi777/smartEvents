"""
LiveIQ — District (Zomato) Event Scraper
No public API exists for District, BookMyShow, or Insider — Ticketmaster's
India event inventory is effectively empty (verified: 0 events across all
classifications/keywords for countryCode=IN, while US returns 10,000+).
Scraping District's own public listing pages is the only way to get real,
current Indian event data. Read-only, public pages only.

District (district.in) is a Next.js app. Event listings render server-side
in the initial HTML/DOM once JS hydrates — no embedded JSON payload was
found, so this parses rendered card text rather than an API response.
The city is switched via the "Select Location" modal (no city URL param
exists), so each city requires driving that UI through Playwright.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import re

import structlog
from playwright.async_api import async_playwright

logger = structlog.get_logger()

BASE_URL = "https://www.district.in/events"
SOURCE = "district"

# District city display name -> LiveIQ tracked city name
CITY_SEARCH_TERMS: Dict[str, str] = {
    "Mumbai": "Mumbai",
    "Delhi NCR": "Delhi",
    "Bengaluru": "Bengaluru",
    "Hyderabad": "Hyderabad",
    "Pune": "Pune",
    "Chennai": "Chennai",
    "Kolkata": "Kolkata",
    "Ahmedabad": "Ahmedabad",
    "Jaipur": "Jaipur",
    "Chandigarh": "Chandigarh",
    "Kochi": "Kochi",
    "Indore": "Indore",
}

CATEGORY_KEYWORDS = {
    "comedy": "comedy",
    "stand up": "comedy",
    "theatre": "theatre",
    "theatrical": "theatre",
    "sports": "sports",
    "workshop": "workshop",
    "dining": "dining",
    "food": "dining",
    "water park": "experience",
    "amusement": "experience",
}


def _guess_category(title: str) -> str:
    t = title.lower()
    for kw, cat in CATEGORY_KEYWORDS.items():
        if kw in t:
            return cat
    return "music"


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Matches the first "<Day> <Mon>" occurrence, e.g. "28 Aug" in
# "Fri, 28 Aug – Sun, 30 Aug, 10:00 AM". Optionally captures a time like
# "10:00 AM" / "7:00 PM" appearing anywhere in the string.
_DATE_RE = re.compile(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", re.IGNORECASE)
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(AM|PM)", re.IGNORECASE)


def _parse_event_date(date_text: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """
    Best-effort parse of District's free-form date strings (no year given,
    inconsistent format, sometimes "Multiple Dates"/"To be announced").
    Returns the first matching date, rolled into next year if it would
    otherwise be in the past. Returns None if nothing parseable is found —
    callers must treat that as "unknown date", never default to today.
    """
    now = now or datetime.now(timezone.utc)
    date_match = _DATE_RE.search(date_text)
    if not date_match:
        return None

    day = int(date_match.group(1))
    month = _MONTHS[date_match.group(2).lower()[:3]]

    hour, minute = 0, 0
    time_match = _TIME_RE.search(date_text)
    if time_match:
        hour = int(time_match.group(1)) % 12
        minute = int(time_match.group(2))
        if time_match.group(3).upper() == "PM":
            hour += 12

    year = now.year
    try:
        candidate = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    except ValueError:
        return None

    if candidate < now:
        try:
            candidate = datetime(year + 1, month, day, hour, minute, tzinfo=timezone.utc)
        except ValueError:
            return None

    return candidate


def _parse_price(price_text: str) -> tuple[Optional[float], Optional[float]]:
    """'₹1499 onwards' -> (1499.0, None). '₹500' -> (500.0, 500.0)."""
    nums = re.findall(r"[\d,]+", price_text.replace("₹", ""))
    if not nums:
        return None, None
    val = float(nums[0].replace(",", ""))
    return val, val


def _parse_card_text(text: str) -> Optional[Dict[str, Any]]:
    """
    District event cards render as a fixed 5-line text block:
      line 0: date/time string (free-form, not reliably parseable to a date)
      line 1: event title
      line 2: venue (often "Venue Name | Area, City")
      line 3: price (e.g. "₹799 onwards")
      line 4: "Book tickets" CTA — ignored
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) < 4:
        return None

    date_text, title, venue_line, price_text = lines[0], lines[1], lines[2], lines[3]
    price_min, price_max = _parse_price(price_text)
    venue_name = venue_line.split("|")[0].strip() if "|" in venue_line else venue_line.split(",")[0].strip()

    return {
        "title": title,
        "date_text": date_text,
        "venue_name": venue_name,
        "venue_line": venue_line,
        "ticket_price_min": price_min,
        "ticket_price_max": price_max,
        "category": _guess_category(title),
    }


async def _switch_city(page, city_search_term: str) -> bool:
    """
    Drive the 'Select Location' modal to switch to the target city.
    District auto-detects a default city (e.g. "Gurugram") and shows it as
    plain text at the very top of the page — clicking that text opens the
    location picker modal. There is no dedicated "Select Location" button
    visible before that click, and no URL query param that changes city.
    """
    try:
        # The current auto-detected city (e.g. "Gurugram") renders as plain
        # text at the very top of the page, immediately above the state name.
        # Clicking it opens the location picker modal.
        body_text = await page.inner_text("body")
        first_line = next((l.strip() for l in body_text.split("\n") if l.strip()), None)
        if not first_line:
            logger.warning("district_scraper: could not read current city label")
            return False
        await page.click(f"text={first_line}", timeout=5000)
    except Exception as exc:
        logger.warning("district_scraper: could not open location picker", error=str(exc))
        return False

    try:
        search_input = page.locator('input[placeholder="Search city, area or locality"]')
        await search_input.wait_for(timeout=5000)
        await search_input.fill(city_search_term)
        await page.wait_for_timeout(1500)

        # Pick the exact "<City>\n<City>, <State>" suggestion by enumerating
        # candidates in Python — Playwright's text= regex doesn't reliably
        # match embedded newlines, and substring matches like "Mumbai Central"
        # or "Mumbaikar's" would otherwise false-positive.
        exact_prefix = f"{city_search_term}\n{city_search_term},"
        candidates = await page.query_selector_all('li, div[role="option"], button')
        target = None
        for c in candidates:
            t = (await c.inner_text()).strip()
            if t.startswith(exact_prefix):
                target = c
                break

        if target is None:
            logger.warning("district_scraper: no exact city suggestion found", city=city_search_term)
            return False

        await target.click(timeout=5000)
        await page.wait_for_timeout(2500)
        await page.wait_for_load_state("networkidle", timeout=15000)
        return True
    except Exception as exc:
        logger.warning("district_scraper: city switch failed", city=city_search_term, error=str(exc))
        return False


async def scrape_city(city_name: str, max_events: int = 30) -> List[Dict[str, Any]]:
    """
    Scrape District's public /events listing for one city.
    Returns a list of normalized event dicts ready for the events table.
    """
    search_term = CITY_SEARCH_TERMS.get(city_name, city_name)
    events: List[Dict[str, Any]] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )
        )
        try:
            await page.goto(BASE_URL, wait_until="networkidle", timeout=20000)

            switched = await _switch_city(page, search_term)
            if not switched:
                # Scraping anyway would tag the DEFAULT city's events (e.g.
                # Gurugram) with the requested city's name — a silent data
                # integrity bug. Bail out instead; caller sees an empty list
                # for this city and can retry later.
                logger.error("district_scraper: could not switch city, aborting", requested=city_name)
                return []

            links = await page.query_selector_all('a[href*="buy-tickets"]')
            seen_titles = set()
            now = datetime.now(timezone.utc)

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

                    event_date = _parse_event_date(parsed["date_text"], now=now)
                    if event_date is None:
                        # e.g. "To be announced" — no usable date, skip rather
                        # than guess one.
                        continue

                    events.append({
                        "external_id": href.rstrip("/").split("/")[-1],
                        "source": SOURCE,
                        "title": parsed["title"],
                        "category": parsed["category"],
                        "booking_url": href,
                        "venue_name": parsed["venue_name"],
                        "city": city_name,
                        "ticket_price_min": parsed["ticket_price_min"],
                        "ticket_price_max": parsed["ticket_price_max"],
                        "event_date": event_date,
                        "raw_date_text": parsed["date_text"],
                        "status": "upcoming",
                        "scraped_at": now,
                    })
                except Exception as exc:
                    logger.warning("district_scraper: card parse failed", error=str(exc))
                    continue

            logger.info("district_scraper: city scraped", city=city_name, count=len(events))

        except Exception as exc:
            logger.error("district_scraper: page load failed", city=city_name, error=str(exc))
        finally:
            await browser.close()

    return events


async def scrape_all_cities(cities: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Scrape District listings for all (or a subset of) tracked cities, sequentially."""
    targets = cities or list(CITY_SEARCH_TERMS.keys())
    all_events: List[Dict[str, Any]] = []
    for city in targets:
        city_events = await scrape_city(city)
        all_events.extend(city_events)
    return all_events
