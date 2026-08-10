"""Test entity metric collection and DB write."""
import asyncio, sys
sys.path.insert(0, '.')

async def main():
    from sqlalchemy import select, text
    from app.core.database import AsyncSessionLocal
    from app.models.entity import Entity
    from app.workers.entity_metrics import _process_single_entity

    print("Fetching 2 verified entities from DB...")
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Entity).where(Entity.is_verified == True).limit(2)
        )
        entities = result.scalars().all()
        entity_list = [
            {
                "id": e.id,
                "name": e.name,
                "external_ids": e.external_ids or {},
                "entity_type": e.entity_type,
            }
            for e in entities
        ]

    names = [e["name"] for e in entity_list]
    print(f"Processing: {names}")
    print()

    for e in entity_list:
        result = await _process_single_entity(e)
        score = result.get("composite_score")
        direction = result.get("trend_direction")
        listeners = result.get("listeners")
        completeness = result.get("data_completeness", 0)
        print(f"  {e['name']}")
        print(f"    score={score}  direction={direction}  listeners={listeners}  completeness={completeness:.0%}")

    # Verify rows were written
    print()
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM entity_metrics"))
        count = result.scalar()
        print(f"entity_metrics table rows: {count}")

        if count > 0:
            rows = await session.execute(
                text("""
                    SELECT e.name, m.composite_score, m.trend_velocity,
                           m.lastfm_listeners, m.news_mentions_7d,
                           m.google_trend_score, m.data_completeness
                    FROM entity_metrics m
                    JOIN entities e ON e.id = m.entity_id
                    ORDER BY m.time DESC LIMIT 5
                """)
            )
            print("\nLatest rows in entity_metrics:")
            for row in rows:
                name, score, velocity, lfm, news, trend, completeness = row
                direction = "rising" if (velocity or 0) > 2 else ("falling" if (velocity or 0) < -2 else "stable")
                print(f"  {name:<30} score={score}  dir={direction}  lfm_listeners={lfm}  news={news}  trend={trend}  completeness={completeness:.0%}" if completeness else f"  {name:<30} score={score}")

asyncio.run(main())
