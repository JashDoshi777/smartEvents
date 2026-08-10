"""Fix Pune active_on_district flag — should be False (Tier-2, expansion opportunity)"""
import asyncio, sys
sys.path.insert(0, '.')

async def fix():
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        r = await db.execute(text("SELECT name, tier, active_on_district FROM cities WHERE active_on_district = true ORDER BY tier"))
        print("Currently active cities:")
        for row in r.all():
            print(f"  Tier {row[1]}: {row[0]}")

        # Only Tier-1 metros should be active
        await db.execute(text("UPDATE cities SET active_on_district = false WHERE name = 'Pune'"))
        await db.commit()

        r2 = await db.execute(text("SELECT COUNT(*) FROM cities WHERE active_on_district = true"))
        count = r2.scalar()
        print(f"\nAfter fix — active_on_district=True count: {count}")
        assert count == 4, f"Expected 4, got {count}"
        print("FIXED OK")

asyncio.run(fix())
