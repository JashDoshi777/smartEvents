"""
LiveIQ — Competitor Intelligence Worker
Scrapes District's own listings and BookMyShow's public event pages
(no API exists for either — see district_scraper.py / bookmyshow_scraper.py
docstrings for why) and upserts results into the events table.

District events (source="district") represent District's own live
inventory — real data for dashboard/pricing/ML, same as Ticketmaster sync.
BookMyShow events (source="bookmyshow") represent competitor inventory —
feeds /competitors/intelligence with real counts instead of estimates.

Schedule: every 12 hours (see celery_app.py beat_schedule)
"""

import structlog
from celery import Task

from app.workers.celery_app import celery_app
from app.workers.run_utils import run_async
from app.services.ingestion.district_scraper import scrape_all_cities as scrape_district_all
from app.services.ingestion.bookmyshow_scraper import scrape_all_cities as scrape_bms_all
from app.services.ingestion.scraped_event_upsert import upsert_scraped_events

logger = structlog.get_logger()


async def _run_scrape() -> dict:
    results = {"district": {}, "bookmyshow": {}}

    try:
        district_events = await scrape_district_all()
        results["district"]["scraped"] = len(district_events)
        results["district"].update(await upsert_scraped_events(district_events))
    except Exception as exc:
        logger.error("competitor_intel: District scrape failed", error=str(exc))
        results["district"]["error"] = str(exc)

    try:
        bms_events = await scrape_bms_all()
        results["bookmyshow"]["scraped"] = len(bms_events)
        results["bookmyshow"].update(await upsert_scraped_events(bms_events))
    except Exception as exc:
        logger.error("competitor_intel: BookMyShow scrape failed", error=str(exc))
        results["bookmyshow"]["error"] = str(exc)

    return results


@celery_app.task(
    name="app.workers.competitor_intel.scrape_all_platforms",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
)
def scrape_all_platforms(self: Task):
    """Scrape District + BookMyShow public listings, upsert into events table."""
    logger.info("competitor_intel: starting scrape cycle")
    try:
        result = run_async(_run_scrape())
        logger.info("competitor_intel: scrape cycle complete", **result)
        return result
    except Exception as exc:
        logger.error("competitor_intel: scrape cycle failed", error=str(exc))
        raise self.retry(exc=exc)
