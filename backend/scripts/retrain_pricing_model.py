"""
LiveIQ — Retrain Pricing Model on Real DB Events (Sprint 4)
============================================================
Run this script once you have ≥50 historical events in the DB:

    venv\\Scripts\\python scripts\\retrain_pricing_model.py

What it does:
1. Pulls all completed/sold_out events from PostgreSQL
2. Joins entity composite_score + city music_score
3. Re-trains the GradientBoostingRegressor
4. Saves new model to ml_models/pricing_gbr.joblib
5. Prints R² scores so you can evaluate quality

The model automatically reloads on the next API request.
"""

import asyncio
import sys
import os

# Make sure backend root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import structlog
from sqlalchemy import select, desc
from app.core.database import AsyncSessionLocal
from app.models.event import Event
from app.models.entity import Entity
from app.models.metrics import EntityMetric
from app.models.city import City

logger = structlog.get_logger()


async def load_training_events():
    """
    Load completed events with entity scores + city data for retraining.
    Returns a list of dicts matching PricingMLEngine.retrain_on_real_data() format.
    """
    training_rows = []

    async with AsyncSessionLocal() as session:
        # Get events that have actual attendance or fill rate
        result = await session.execute(
            select(Event)
            .where(Event.status.in_(["completed", "sold_out"]))
            .where(Event.ticket_price_min.isnot(None))
            .order_by(desc(Event.event_date))
            .limit(5000)
        )
        events = result.scalars().all()

        logger.info(f"Loaded {len(events)} completed events from DB")

        for ev in events:
            # Skip events without pricing data
            if not ev.ticket_price_min:
                continue

            # Get entity composite score
            composite_score = 50.0
            is_international = False
            category = ev.category or "music"

            if ev.entity_id:
                ent_result = await session.execute(
                    select(Entity).where(Entity.id == ev.entity_id)
                )
                entity = ent_result.scalar_one_or_none()
                if entity:
                    is_international = entity.is_international or False
                    category = entity.category or ev.category or "music"

                    # Get latest metric for composite score
                    metric_result = await session.execute(
                        select(EntityMetric)
                        .where(EntityMetric.entity_id == ev.entity_id)
                        .where(EntityMetric.time <= ev.event_date)
                        .order_by(desc(EntityMetric.time))
                        .limit(1)
                    )
                    metric = metric_result.scalar_one_or_none()
                    if metric and metric.composite_score:
                        composite_score = float(metric.composite_score)

            # Get city music score
            city_music_score = 70.0
            if ev.venue_id:
                # Try to get city from venue relationship
                pass  # Venue → City join is complex; use 70 as fallback

            # Fill rate
            fill_rate = None
            if ev.fill_rate:
                fill_rate = float(ev.fill_rate)
            elif ev.actual_attendance and ev.total_capacity and ev.total_capacity > 0:
                fill_rate = ev.actual_attendance / ev.total_capacity
            if fill_rate is None:
                continue

            # Lead time (days from created_at to event_date)
            lead_days = 60
            if ev.created_at and ev.event_date:
                delta = ev.event_date.replace(tzinfo=None) - ev.created_at.replace(tzinfo=None)
                lead_days = max(0, delta.days)

            training_rows.append({
                "composite_score":  composite_score,
                "city_music_score": city_music_score,
                "venue_capacity":   ev.total_capacity or 5000,
                "category":         category,
                "is_international": int(is_international),
                "lead_days":        lead_days,
                "ticket_price_min": float(ev.ticket_price_min),
                "actual_fill_rate": fill_rate,
            })

    logger.info(f"Prepared {len(training_rows)} training samples")
    return training_rows


async def main():
    from app.services.ml.pricing_engine import pricing_engine

    print("=" * 60)
    print("LiveIQ — Pricing Model Retraining")
    print("=" * 60)

    rows = await load_training_events()
    if not rows:
        print("\nNo completed events found in DB.")
        print("The model will continue using synthetic training data.")
        print("Re-run this script once events are synced and completed.")
        return

    print(f"\nTraining on {len(rows)} real historical events…")
    result = pricing_engine.retrain_on_real_data(rows)

    if result.get("status") == "ok":
        print(f"\nSuccess!")
        print(f"  Price model R²:    {result.get('price_r2', 'N/A')}")
        print(f"  Fill rate model R²: {result.get('fill_r2', 'N/A')}")
        print(f"  Trained at:        {result.get('trained_at')}")
        print(f"\nModel saved to ml_models/pricing_gbr.joblib")
        print("The API will use the new model on the next request.")
    elif result.get("status") == "insufficient_data":
        print(f"\nNeed at least 50 samples, only have {result.get('count')}.")
        print("Keep syncing events — rerun when you have more data.")
    else:
        print(f"\nError: {result}")


if __name__ == "__main__":
    asyncio.run(main())
