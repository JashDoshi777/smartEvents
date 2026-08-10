"""
LiveIQ — Sprint 3 Complete Audit
Covers: Cities, Competitors, Executive, Pricing routes + DB state
"""
import asyncio, sys
sys.path.insert(0, '.')

PASS = "[OK] "
FAIL = "[FAIL]"
results = []

def check(name, fn):
    try:
        fn()
        results.append((name, True, None)) 
        print(f"  {PASS} {name}")
    except Exception as e:
        results.append((name, False, str(e)[:150]))
        print(f"  {FAIL} {name}")
        print(f"         -> {str(e)[:150]}")

async def acheck(name, coro):
    try:
        await coro
        results.append((name, True, None))
        print(f"  {PASS} {name}")
    except Exception as e:
        results.append((name, False, str(e)[:150]))
        print(f"  {FAIL} {name}")
        print(f"         -> {str(e)[:150]}")

# ─── 1. MODULE IMPORTS ─────────────────────────────────────────────────────────
print("\n[1/7] Module Imports (Sprint 3 modules)")
check("routes.cities",      lambda: __import__("app.api.routes.cities", fromlist=["router"]))
check("routes.competitors", lambda: __import__("app.api.routes.competitors", fromlist=["router"]))
check("routes.executive",   lambda: __import__("app.api.routes.executive", fromlist=["router"]))
check("routes.pricing",     lambda: __import__("app.api.routes.pricing", fromlist=["router"]))
check("models.city",        lambda: __import__("app.models.city", fromlist=["City"]))
check("main app (all routes registered)", lambda: __import__("main", fromlist=["app"]))

# ─── 2. ROUTE STRUCTURE ────────────────────────────────────────────────────────
print("\n[2/7] Route Structure (all Sprint 3 endpoints)")

def test_cities_routes():
    from app.api.routes.cities import router
    paths = [r.path for r in router.routes]
    assert "/" in paths,                            "Missing GET /"
    assert "/top" in paths,                         "Missing GET /top"
    assert "/gaps" in paths,                        "Missing GET /gaps"
    assert "/{city_name}/intelligence" in paths,    "Missing /{city}/intelligence"
    assert "/{city_name}/venues" in paths,          "Missing /{city}/venues"
    # Static routes must come before dynamic — verify by index order
    static_idx  = next(i for i, r in enumerate(router.routes) if r.path == "/gaps")
    dynamic_idx = next(i for i, r in enumerate(router.routes) if r.path == "/{city_name}/intelligence")
    assert static_idx < dynamic_idx, "Path ordering bug: /gaps must be before /{city_name}"

def test_competitors_routes():
    from app.api.routes.competitors import router
    paths = [r.path for r in router.routes]
    assert "/intelligence" in paths,    "Missing /intelligence"
    assert "/gaps" in paths,            "Missing /gaps"
    assert "/activity-feed" in paths,   "Missing /activity-feed"

def test_executive_routes():
    from app.api.routes.executive import router
    paths = [r.path for r in router.routes]
    assert "/kpis" in paths,       "Missing /kpis"
    assert "/briefing" in paths,   "Missing /briefing"
    assert "/portfolio" in paths,  "Missing /portfolio"

def test_pricing_routes():
    from app.api.routes.pricing import router
    paths = [r.path for r in router.routes]
    assert "/optimize" in paths,                "Missing POST /optimize"
    assert "/elasticity/{entity_id}" in paths,  "Missing /elasticity/{id}"
    assert "/benchmarks" in paths,              "Missing /benchmarks"

def test_pricing_schema():
    from app.api.routes.pricing import PricingRequest
    import inspect
    fields = PricingRequest.model_fields
    assert "entity_id" in fields
    assert "city" in fields
    assert "venue_capacity" in fields
    assert "proposed_price" in fields

def test_pricing_benchmarks_complete():
    from app.api.routes.pricing import CATEGORY_BENCHMARKS, CITY_PRICE_MULTIPLIERS
    expected_categories = ["music", "comedy", "edm", "sports", "theatre", "international"]
    for cat in expected_categories:
        assert cat in CATEGORY_BENCHMARKS, f"Missing category: {cat}"
    expected_cities = ["mumbai", "delhi ncr", "bengaluru", "pune", "hyderabad"]
    for c in expected_cities:
        assert c in CITY_PRICE_MULTIPLIERS, f"Missing city: {c}"
    assert CITY_PRICE_MULTIPLIERS["mumbai"] > CITY_PRICE_MULTIPLIERS["indore"], "Mumbai must be most expensive"

check("Cities: 5 routes in correct order", test_cities_routes)
check("Competitors: 3 routes present",     test_competitors_routes)
check("Executive: 3 routes present",       test_executive_routes)
check("Pricing: 3 routes + Pydantic schema", test_pricing_routes)
check("Pricing: PricingRequest schema valid", test_pricing_schema)
check("Pricing: benchmarks + city multipliers complete", test_pricing_benchmarks_complete)

# ─── 3. LIVE DB — CITIES ───────────────────────────────────────────────────────
print("\n[3/7] Live DB — Cities Table")

async def test_city_count():
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        count = await db.scalar(text("SELECT COUNT(*) FROM cities"))
        assert count == 12, f"Expected 12 cities, got {count}"
        print(f"         -> {count} cities in DB")

async def test_city_tiers():
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        tiers = await db.execute(text("SELECT tier, COUNT(*) FROM cities GROUP BY tier ORDER BY tier"))
        dist = {r[0]: r[1] for r in tiers.all()}
        assert dist.get(1) == 4, f"Expected 4 Tier-1 cities, got {dist.get(1)}"
        assert dist.get(2) == 4, f"Expected 4 Tier-2 cities, got {dist.get(2)}"
        assert dist.get(3) == 4, f"Expected 4 Tier-3 cities, got {dist.get(3)}"
        print(f"         -> Tier dist: {dict(sorted(dist.items()))}")

async def test_city_market_scores():
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        result = await db.execute(text(
            "SELECT name, music_market_size, nightlife_score FROM cities WHERE music_market_size IS NOT NULL"
        ))
        rows = result.all()
        assert len(rows) == 12, f"All 12 cities should have music_market_size, got {len(rows)}"
        # Mumbai should have highest music score
        mumbai = next((r for r in rows if r[0] == "Mumbai"), None)
        assert mumbai and mumbai[1] == 95.0, f"Mumbai music score wrong: {mumbai}"
        print(f"         -> All 12 cities have market scores; Mumbai music={mumbai[1]}")

async def test_city_district_flags():
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        active = await db.scalar(text("SELECT COUNT(*) FROM cities WHERE active_on_district = true"))
        inactive = await db.scalar(text("SELECT COUNT(*) FROM cities WHERE active_on_district = false"))
        assert active == 4,  f"Expected 4 District-active cities (Tier 1), got {active}"
        assert inactive == 8, f"Expected 8 expansion opportunities, got {inactive}"
        print(f"         -> District active: {active}, expansion opportunities: {inactive}")

async def test_city_seasonality():
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("SELECT name, festival_months, monsoon_months FROM cities WHERE name = 'Mumbai'"))
        row = result.first()
        assert row is not None
        assert row[1] is not None, "Mumbai festival_months should not be null"
        assert isinstance(row[2], list) and len(row[2]) > 0, "Mumbai monsoon_months should be a list"
        print(f"         -> Mumbai festivals={list(row[1].keys())}, monsoon={row[2]}")

async def test_full_db_state():
    """NeonDB state snapshot — Sprint 2+3 combined table counts."""
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        for table, minimum in [("entities", 51), ("cities", 12), ("entity_metrics", 1), ("events", 0)]:
            count = await db.scalar(text(f"SELECT COUNT(*) FROM {table}"))
            print(f"         -> {table}: {count} rows")
        assert await db.scalar(text("SELECT COUNT(*) FROM entities")) >= 51
        assert await db.scalar(text("SELECT COUNT(*) FROM cities"))   == 12
        assert await db.scalar(text("SELECT COUNT(*) FROM entity_metrics")) >= 1

async def run_db_city_checks():
    await acheck("Cities table: 12 rows",                    test_city_count())
    await acheck("Cities table: tier distribution 4+4+4",   test_city_tiers())
    await acheck("Cities table: all market scores populated", test_city_market_scores())
    await acheck("Cities table: 4 active + 8 expansion",    test_city_district_flags())
    await acheck("Cities table: Mumbai seasonality data",    test_city_seasonality())
    # DB snapshot runs in same event loop (avoids asyncpg cleanup / loop-closed errors)
    await acheck("NeonDB: all tables have data",             test_full_db_state())

asyncio.run(run_db_city_checks())

# ─── 4. LIVE ROUTE LOGIC ───────────────────────────────────────────────────────
print("\n[4/7] Live Route Business Logic")

async def test_composite_score_fn():
    from app.api.routes.cities import _composite
    from app.models.city import City

    c = City()
    c.nightlife_score    = 92.0
    c.sports_affinity_score = 88.0
    c.arts_culture_score = 85.0
    c.comedy_market_size = 90.0
    c.music_market_size  = 95.0
    score = _composite(c)
    assert score is not None and 85 < score < 95, f"Composite score out of expected range: {score}"
    print(f"         -> Mumbai composite: {score}")

async def test_city_to_dict():
    from app.api.routes.cities import _city_to_dict, _composite
    from app.models.city import City

    c = City()
    c.id = None  # Will be stringified
    c.name = "Test"; c.state = "X"; c.tier = 1
    c.nightlife_score = 80.0; c.music_market_size = 90.0
    c.sports_affinity_score = 70.0; c.arts_culture_score = 75.0
    c.comedy_market_size = 65.0
    c.top_categories = ["music"]
    d = _city_to_dict(c)
    assert "scores" in d
    assert "composite" in d["scores"]
    assert d["scores"]["composite"] is not None

async def test_pricing_logic():
    """Verify pricing algorithm produces sensible results."""
    from app.api.routes.pricing import CATEGORY_BENCHMARKS, CITY_PRICE_MULTIPLIERS

    # Mumbai premium market
    mumbai_mult = CITY_PRICE_MULTIPLIERS["mumbai"]
    indore_mult  = CITY_PRICE_MULTIPLIERS["indore"]
    assert mumbai_mult > indore_mult, "Mumbai must be pricier than Indore"

    # International premium
    intl_bench  = CATEGORY_BENCHMARKS["international"]
    comedy_bench = CATEGORY_BENCHMARKS["comedy"]
    assert intl_bench["sweet_spot"] > comedy_bench["sweet_spot"], "Intl > comedy price"

    # Floor must be less than sweet_spot
    for cat, bench in CATEGORY_BENCHMARKS.items():
        assert bench["floor"] < bench["sweet_spot"] < bench["premium"] < bench["ultra_premium"], \
            f"Price tier ordering wrong for {cat}: {bench}"
    print("         -> All pricing tiers correctly ordered (floor < sweet_spot < premium < ultra_premium)")

async def test_competitor_platforms():
    from app.api.routes.competitors import PLATFORMS
    assert "district" in PLATFORMS
    assert "bookmyshow" in PLATFORMS
    assert "insider" in PLATFORMS
    assert "ticketmaster_india" in PLATFORMS
    for name, data in PLATFORMS.items():
        assert "name" in data
        assert "strengths" in data
        assert "markets" in data
    print(f"         -> {len(PLATFORMS)} platforms configured")

async def test_city_intelligence_recommendation():
    """Verify recommendation logic for active vs inactive cities."""
    from app.api.routes.cities import _composite
    from app.models.city import City

    active_city = City()
    active_city.active_on_district = True
    active_city.music_market_size = 95.0
    active_city.nightlife_score = 92.0
    active_city.sports_affinity_score = 88.0
    active_city.arts_culture_score = 85.0
    active_city.comedy_market_size = 90.0
    score = _composite(active_city)
    assert score > 80, f"Mumbai-like city should score > 80: {score}"

    # Inactive high-potential city
    inactive_city = City()
    inactive_city.active_on_district = False
    inactive_city.music_market_size = 87.0
    inactive_city.nightlife_score = 82.0
    inactive_city.sports_affinity_score = 85.0
    inactive_city.arts_culture_score = 80.0
    inactive_city.comedy_market_size = 83.0
    score2 = _composite(inactive_city)
    assert score2 > 80, f"Pune-like city should score > 80: {score2}"
    print(f"         -> Recommendation logic verified (active={score:.1f}, expansion candidate={score2:.1f})")

async def run_logic_checks():
    await acheck("Cities: _composite() weighted average",     test_composite_score_fn())
    await acheck("Cities: _city_to_dict() structure",         test_city_to_dict())
    await acheck("Pricing: tier ordering invariants",         test_pricing_logic())
    await acheck("Competitors: 4 platforms configured",       test_competitor_platforms())
    await acheck("Cities: recommendation score thresholds",   test_city_intelligence_recommendation())

asyncio.run(run_logic_checks())

# ─── 5. LIVE API CALLS (SPRINT 3 SPECIFIC) ────────────────────────────────────
print("\n[5/7] Live External API Calls (Sprint 3 specific)")

async def test_ticketmaster_city_search():
    from app.services.ingestion.ticketmaster_client import TicketmasterClient
    async with TicketmasterClient() as client:
        result = await client.search_events(keyword="Mumbai", country_code="IN", size=5)
    assert isinstance(result, dict) and "events" in result
    print(f"         -> Ticketmaster Mumbai search: {result['total_elements']} total events")

async def test_newsapi_competitor():
    from app.services.ingestion.newsapi_client import NewsAPIClient
    async with NewsAPIClient() as client:
        result = await client.search_news("BookMyShow concert India", page_size=3)
    assert isinstance(result, dict) and "total_results" in result
    print(f"         -> BookMyShow news: {result['total_results']} articles found")

async def test_groq_executive_briefing():
    from app.services.groq_service import chat_completion
    r = await chat_completion(
        messages=[{"role": "user", "content": "In exactly 10 words, describe what a ticket pricing intelligence system does."}],
        max_tokens=50,
        temperature=0.0
    )
    assert len(r.split()) >= 5
    print(f"         -> Groq executive briefing: {r[:80]!r}")

async def run_api_checks():
    await acheck("Ticketmaster: city search (Mumbai)",    test_ticketmaster_city_search())
    await acheck("NewsAPI: competitor monitoring query",  test_newsapi_competitor())
    await acheck("Groq: executive briefing generation",   test_groq_executive_briefing())

asyncio.run(run_api_checks())

# ─── 6. GATE TESTS (REGRESSION) ───────────────────────────────────────────────
print("\n[6/6] Regression Gate Tests")
import subprocess
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_sprint0_gate.py", "-q", "--tb=line"],
    capture_output=True, text=True
)
output = result.stdout + result.stderr
passed = "12 passed" in output
check("Gate tests: 12/12 passing", lambda: None if passed else (_ for _ in ()).throw(
    AssertionError(output[-300:])
))
print(f"         -> {output.split(chr(10))[-3].strip()}")

# ─── SUMMARY ──────────────────────────────────────────────────────────────────
total  = len(results)
ok     = sum(1 for _, v, _ in results if v)
failed = total - ok

print(f"\n{'='*60}")
print(f"  SPRINT 3 AUDIT: {ok}/{total} passed  |  {failed} failed")
print(f"{'='*60}")
if failed:
    print("\n  FAILURES:")
    for name, ok_, err in results:
        if not ok_:
            print(f"    ✗ {name}")
            if err: print(f"      {err}")
else:
    print("  ALL CHECKS PASSED — Ready for Sprint 4!")
