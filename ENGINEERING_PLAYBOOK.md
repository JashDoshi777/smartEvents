# ⚙️ LiveIQ Engineering Playbook
### How Big Tech Engineers Build Large Projects — Precisely, Fast, Error-Free

---

## The Core Engineering Philosophy

> "Never add the next layer until the current layer is verified working."

Big tech engineers don't build everything then test. They build **one vertical slice at a time**, verify it fully, commit it, and move to the next. Every step has a **Definition of Done** — a checklist you must pass before moving forward.

### The 5 Laws We Follow
1. **Environment before code** — Docker, secrets, DB must work before writing a single business logic line
2. **Schema before everything** — the database schema is the contract; lock it before any service depends on it
3. **One integration at a time** — integrate Spotify, verify fully, commit. Then YouTube. Never both at once.
4. **Test the failure path** — every API call must handle the failure case before the success case is considered done
5. **Green main branch always** — never commit broken code to main. Feature branches + PRs only.

---

## Git Workflow (Non-Negotiable)

```
main          ← always deployable, always green
  └── dev     ← integration branch
        └── feature/sprint-1-docker-setup
        └── feature/sprint-1-db-schema
        └── feature/sprint-2-spotify-integration
        └── feature/sprint-2-entity-scoring
        ...
```

**Branch naming**: `feature/sprint-{N}-{description}`  
**Commit format**: `feat: add spotify monthly listeners ingestion` / `fix:` / `test:` / `chore:`  
**Rule**: Every feature branch must pass its verification gate before merging to `dev`

---

## Sprint Overview

| Sprint | Duration | Goal | Deliverable |
|--------|----------|------|-------------|
| **Sprint 0** | 2 days | Foundation — zero application code | Docker running, DB connected, CI passing |
| **Sprint 1** | 5 days | Data layer — first 3 APIs wired | Spotify + Google Trends + Ticketmaster ingesting |
| **Sprint 2** | 5 days | Core intelligence — scoring + city ranking | Artist score endpoint working, city ranking working |
| **Sprint 3** | 7 days | Frontend skeleton + 3 pages | Home + Intelligence + Cities pages live |
| **Sprint 4** | 7 days | ML models + remaining APIs | Trend predictor + revenue predictor working |
| **Sprint 5** | 7 days | AI layer + remaining pages | Gemini copilot + executive dashboard |
| **Sprint 6** | 5 days | Polish + production deploy | Live URL, auth, monitoring |

---

## 🟥 SPRINT 0 — Environment & Foundation (2 Days)

> **Goal**: A working skeleton where everything talks to everything. Zero business logic.

### Day 0.1 — Project Scaffold & Docker

**Step 1: Create directory structure**
```bash
mkdir liveiq && cd liveiq
mkdir -p backend/app/{api/routes,core,models,schemas,services/{scoring,ml,ai,ingestion},workers}
mkdir -p backend/{tests,ml_models}
mkdir -p frontend/src/{app,components/{ui,charts,maps,layout,features},lib/{stores,hooks},styles}
touch backend/main.py backend/requirements.txt backend/.env.example
touch frontend/package.json
touch docker-compose.yml .gitignore README.md
```

**Step 2: Write `docker-compose.yml` first**
```yaml
# Exact services — no more, no less than what we need right now
version: "3.9"
services:
  postgres:
    image: timescale/timescaledb:latest-pg15
    environment:
      POSTGRES_DB: liveiq
      POSTGRES_USER: liveiq
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports: ["5432:5432"]
    volumes: [postgres_data:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U liveiq"]
      interval: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s

  mongodb:
    image: mongo:7
    environment:
      MONGO_INITDB_ROOT_USERNAME: liveiq
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_PASSWORD}
    ports: ["27017:27017"]
    volumes: [mongo_data:/data/db]

  backend:
    build: ./backend
    ports: ["8000:8000"]
    env_file: ./backend/.env
    depends_on:
      postgres: {condition: service_healthy}
      redis: {condition: service_healthy}
    volumes: [./backend:/app]
    command: uvicorn main:app --reload --host 0.0.0.0 --port 8000

volumes:
  postgres_data:
  mongo_data:
```

**Step 3: Write `backend/Dockerfile`**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
```

**Step 4: Minimal `requirements.txt`** (only what we need RIGHT NOW)
```
fastapi==0.111.0
uvicorn[standard]==0.29.0
sqlalchemy==2.0.30
asyncpg==0.29.0
alembic==1.13.1
redis==5.0.4
motor==3.4.0          # async MongoDB
celery==5.4.0
python-dotenv==1.0.1
pydantic==2.7.1
pydantic-settings==2.2.1
httpx==0.27.0
```
> ⚠️ Rule: **Do NOT add ML libraries yet.** They make Docker builds slow. Add them in Sprint 4.

**Step 5: Minimal FastAPI app**
```python
# backend/main.py
from fastapi import FastAPI
from app.core.database import engine
from app.core.config import settings

app = FastAPI(title="LiveIQ API", version="0.1.0")

@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
```

**✅ SPRINT 0 GATE — Day 0.1:**
```bash
docker compose up --build
curl http://localhost:8000/health
# Must return: {"status": "ok", "version": "0.1.0"}
# Must see: postgres healthy, redis healthy, mongodb healthy
```
**Do not proceed if ANY of these fail.**

---

### Day 0.2 — Database Schema + Migrations

**Step 6: Setup Alembic**
```bash
cd backend
alembic init alembic
```

**Step 7: Write ALL models (the contract)**
```python
# backend/app/models/entity.py
from sqlalchemy import Column, String, Enum, Boolean, ARRAY
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid, enum

class EntityType(enum.Enum):
    ARTIST = "artist"
    MOVIE = "movie"
    SPORTS_TEAM = "sports_team"
    COMEDIAN = "comedian"
    THEATRE_GROUP = "theatre_group"
    ATTRACTION = "attraction"
    WORKSHOP = "workshop"
    RESTAURANT = "restaurant"
    BRAND = "brand"

class Entity(Base):
    __tablename__ = "entities"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    entity_type = Column(Enum(EntityType), nullable=False)
    external_ids = Column(JSONB, default={})
    # ... rest of fields
```

Write ALL models before the first migration. Then:
```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

**Step 8: Enable TimescaleDB hypertable**
```sql
-- Run once after migration
SELECT create_hypertable('entity_metrics', 'time', if_not_exists => TRUE);
```

**✅ SPRINT 0 GATE — Day 0.2:**
```bash
# Connect to DB and verify
docker exec -it liveiq-postgres-1 psql -U liveiq -d liveiq -c "\dt"
# Must show: entities, events, venues, cities, entity_metrics, ... all tables
alembic current
# Must show: head
```

**🎯 Sprint 0 Complete Criteria:**
- [ ] `docker compose up` → all 4 services start healthy
- [ ] `/health` returns 200
- [ ] All DB tables exist with correct schema
- [ ] `git commit -m "chore: sprint-0 foundation complete"`

---

## 🟧 SPRINT 1 — Data Ingestion Layer (5 Days)

> **Goal**: Real data flowing into the database. One API at a time.

### Day 1.1 — Configuration + Secrets Architecture

**Step 1: `.env.example`** (commit this, never commit `.env`)
```env
# Database
POSTGRES_URL=postgresql+asyncpg://liveiq:password@localhost:5432/liveiq
POSTGRES_PASSWORD=changeme
MONGO_URL=mongodb://liveiq:changeme@localhost:27017
REDIS_URL=redis://localhost:6379

# API Keys (get these before coding the integrations)
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
YOUTUBE_API_KEY=
TICKETMASTER_API_KEY=
TMDB_API_KEY=
NEWSAPI_KEY=
GEMINI_API_KEY=
MAPBOX_TOKEN=
```

**Step 2: Pydantic settings** (type-safe config, fails at startup if keys missing)
```python
# backend/app/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    postgres_url: str
    redis_url: str
    spotify_client_id: str
    spotify_client_secret: str
    youtube_api_key: str
    # ... etc
    
    class Config:
        env_file = ".env"

settings = Settings()  # Crashes immediately if any required key is missing
```

> ✅ This pattern means you can NEVER accidentally deploy without keys.

---

### Day 1.2 — Spotify Integration

**Rule: Integrate ONE API fully before touching the next.**

**Step 1: Write the client**
```python
# backend/app/services/ingestion/spotify_client.py
import httpx
from app.core.config import settings

class SpotifyClient:
    BASE_URL = "https://api.spotify.com/v1"
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    
    def __init__(self):
        self._token: str | None = None
    
    async def _get_token(self) -> str:
        # OAuth2 client credentials flow
        ...
    
    async def get_artist(self, spotify_id: str) -> dict:
        ...
    
    async def search_artist(self, name: str) -> list[dict]:
        ...
    
    async def get_artist_top_tracks(self, artist_id: str) -> list[dict]:
        ...
```

**Step 2: Write a test BEFORE wiring to DB**
```python
# backend/tests/test_spotify.py
import pytest
from app.services.ingestion.spotify_client import SpotifyClient

@pytest.mark.asyncio
async def test_search_artist():
    client = SpotifyClient()
    results = await client.search_artist("AP Dhillon")
    assert len(results) > 0
    assert results[0]["name"] is not None
    assert "followers" in results[0]

@pytest.mark.asyncio
async def test_get_artist_metrics():
    client = SpotifyClient()
    # AP Dhillon Spotify ID
    artist = await client.get_artist("4PULA4EFzYTiOBLo8cFBDr")
    assert artist["popularity"] >= 0
    assert artist["followers"]["total"] > 0
```

**Step 3: Run the test**
```bash
pytest tests/test_spotify.py -v
# MUST PASS before writing any DB code
```

**Step 4: Wire to DB — ingestion service**
```python
# backend/app/services/ingestion/entity_ingestion.py
async def ingest_artist_from_spotify(spotify_id: str, db: AsyncSession):
    spotify = SpotifyClient()
    data = await spotify.get_artist(spotify_id)
    
    # Upsert entity
    entity = await db.execute(
        select(Entity).where(Entity.external_ids["spotify_id"].astext == spotify_id)
    )
    if not entity.scalar():
        db.add(Entity(name=data["name"], entity_type=EntityType.ARTIST, ...))
    
    # Write time-series metric
    db.add(EntityMetric(
        time=datetime.utcnow(),
        entity_id=entity.id,
        monthly_listeners=data["followers"]["total"],
        spotify_popularity=data["popularity"],
        ...
    ))
    await db.commit()
```

**✅ GATE — Day 1.2:**
```bash
pytest tests/test_spotify.py -v  # All pass
# Manual verify in DB:
docker exec -it liveiq-postgres-1 psql -U liveiq -d liveiq \
  -c "SELECT name, entity_type FROM entities LIMIT 5;"
# Must show at least one artist
```

---

### Day 1.3 — Google Trends Integration

Same pattern. Client → Test → DB wire.

```python
# backend/app/services/ingestion/google_trends_client.py
from pytrends.request import TrendReq
import asyncio
from functools import partial

class GoogleTrendsClient:
    def __init__(self):
        self.pytrends = TrendReq(hl='en-IN', tz=330)
    
    async def get_interest_by_city(self, keyword: str) -> dict[str, float]:
        """Returns {city_name: interest_score} — 0 to 100"""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            partial(self._fetch_regional, keyword)
        )
        return result
    
    def _fetch_regional(self, keyword: str) -> dict:
        self.pytrends.build_payload([keyword], geo='IN')
        df = self.pytrends.interest_by_region(resolution='CITY')
        return df[keyword].to_dict()
```

**Test before wiring:**
```bash
pytest tests/test_google_trends.py -v
```

---

### Day 1.4 — Ticketmaster Integration

Same pattern. Then write a test that verifies events are being stored.

---

### Day 1.5 — Celery Workers + First Scheduled Job

**Step 1: Setup Celery**
```python
# backend/app/workers/celery_app.py
from celery import Celery
from celery.schedules import crontab

celery_app = Celery("liveiq", broker="redis://localhost:6379/0")

celery_app.conf.beat_schedule = {
    "sync-entity-metrics-every-6h": {
        "task": "workers.entity_metrics.sync_all_entities",
        "schedule": crontab(minute=0, hour="*/6"),
    },
}
```

**Step 2: Add Celery worker to docker-compose.yml**
```yaml
  celery_worker:
    build: ./backend
    command: celery -A app.workers.celery_app worker --loglevel=info
    depends_on: [redis, postgres]
    env_file: ./backend/.env

  celery_beat:
    build: ./backend
    command: celery -A app.workers.celery_app beat --loglevel=info
    depends_on: [redis]
    env_file: ./backend/.env
```

**✅ SPRINT 1 COMPLETE GATE:**
```bash
# Run all tests
pytest tests/ -v --tb=short
# Must show: all green

# Check DB has real data
docker exec -it liveiq-postgres-1 psql -U liveiq -d liveiq \
  -c "SELECT COUNT(*) FROM entities; SELECT COUNT(*) FROM entity_metrics;"
# entities: > 0, entity_metrics: > 0

# Celery worker running
docker compose logs celery_worker | grep "ready"
```

---

## 🟨 SPRINT 2 — Core Intelligence Endpoints (5 Days)

> **Goal**: The core business logic APIs work and return real intelligence.

### Day 2.1 — Entity Scoring Service (Python Script, no ML)

```python
# backend/app/services/scoring/entity_scorer.py

WEIGHTS_BY_TYPE = {
    EntityType.ARTIST: {
        "spotify_popularity": 0.20,
        "instagram_growth_7d": 0.15,
        "google_trend_score": 0.15,
        "youtube_views_30d": 0.10,
        "sentiment_positive": 0.10,
        "bandsintown_rsvps": 0.10,
        "news_mentions_7d": 0.05,
        "historical_fill_rate": 0.15,
    },
    EntityType.COMEDIAN: {
        # Different weights for comedians
        "youtube_views_30d": 0.25,
        "sentiment_positive": 0.20,
        ...
    },
}

def normalize(value: float, min_val: float, max_val: float) -> float:
    """Normalize any value to 0-100 range"""
    if max_val == min_val:
        return 50.0
    return max(0, min(100, (value - min_val) / (max_val - min_val) * 100))

def compute_entity_score(metrics: EntityMetric, entity_type: EntityType) -> dict:
    weights = WEIGHTS_BY_TYPE.get(entity_type, WEIGHTS_BY_TYPE[EntityType.ARTIST])
    
    normalized = {
        "spotify_popularity": normalize(metrics.spotify_popularity, 0, 100),
        "google_trend_score": normalize(metrics.google_trend_score, 0, 100),
        # ... all signals normalized
    }
    
    composite = sum(normalized[k] * weights[k] for k in weights if k in normalized)
    
    return {
        "composite_score": round(composite, 1),
        "breakdown": normalized,
        "recommendation": get_recommendation(composite),
        "trend": compute_trend_direction(metrics),
    }
```

**Write tests:**
```python
# tests/test_scoring.py
def test_high_popularity_artist():
    metrics = EntityMetric(spotify_popularity=95, google_trend_score=88, ...)
    result = compute_entity_score(metrics, EntityType.ARTIST)
    assert result["composite_score"] > 80
    assert result["recommendation"] == "Book immediately"

def test_low_popularity_artist():
    metrics = EntityMetric(spotify_popularity=20, google_trend_score=15, ...)
    result = compute_entity_score(metrics, EntityType.ARTIST)
    assert result["composite_score"] < 40
```

**Wire to API route:**
```python
# backend/app/api/routes/entities.py
@router.get("/{entity_id}/score")
async def get_entity_score(entity_id: UUID, db: AsyncSession = Depends(get_db)):
    entity = await get_entity_or_404(entity_id, db)
    metrics = await get_latest_metrics(entity_id, db)
    if not metrics:
        raise HTTPException(404, "No metrics available yet for this entity")
    score = compute_entity_score(metrics, entity.entity_type)
    return {"entity": entity, "score": score}
```

**✅ GATE — Day 2.1:**
```bash
curl http://localhost:8000/entities/{id}/score
# Must return: composite_score, breakdown (6 signals), recommendation
pytest tests/test_scoring.py -v  # All green
```

---

### Day 2.2 — City Demand Ranking (Python Script)

```python
# backend/app/services/scoring/city_ranker.py

TRACKED_CITIES = [
    "Mumbai", "Delhi", "Bangalore", "Pune", 
    "Hyderabad", "Ahmedabad", "Chandigarh", "Jaipur",
    "Chennai", "Kolkata", "Kochi", "Indore"
]

async def rank_cities_for_entity(entity_id: UUID, db: AsyncSession) -> list[dict]:
    results = []
    for city in TRACKED_CITIES:
        # Pull from city-level metrics in DB
        google_score = await get_city_trend_score(entity_id, city, db)
        social_score = await get_city_social_score(entity_id, city, db)
        historical = await get_city_historical_demand(entity_id, city, db)
        competitor = await get_city_competitor_count(entity_id, city, db)
        
        demand = (
            google_score * 0.35 +
            social_score * 0.25 +
            historical * 0.25 +
            competitor * 0.15
        )
        results.append({
            "city": city,
            "demand_score": round(demand, 1),
            "tier": get_city_tier(city),
            "confidence": calculate_confidence(google_score, historical),
        })
    
    return sorted(results, key=lambda x: x["demand_score"], reverse=True)
```

---

### Day 2.3 — Competitor Scraper

**Step 1: Write Playwright scraper for BookMyShow**
```python
# backend/app/services/ingestion/competitor_scraper.py
from playwright.async_api import async_playwright

async def scrape_bookmyshow_events(city: str, category: str) -> list[dict]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"https://in.bookmyshow.com/explore/events-{city.lower()}")
        # Wait for events to load
        await page.wait_for_selector(".event-card", timeout=10000)
        events = await page.query_selector_all(".event-card")
        # Extract: title, category, price, date, status
        ...
        await browser.close()
        return scraped_events
```

**Step 2: Test with a simple assertion**
```python
async def test_bms_scraper():
    events = await scrape_bookmyshow_events("mumbai", "music")
    assert len(events) > 0
    assert all("title" in e for e in events)
    assert all("price" in e for e in events)
```

> ⚠️ Add a `time.sleep(2)` between scrape calls to respect rate limits.

---

### Day 2.4 — API Layer + Response Schemas

Define every response schema in Pydantic before the frontend touches them:

```python
# backend/app/schemas/intelligence.py
from pydantic import BaseModel, UUID4
from datetime import datetime

class EntityScoreBreakdown(BaseModel):
    spotify_popularity: float
    google_trend_score: float
    social_score: float
    sentiment_score: float
    demand_score: float
    risk_score: float

class EntityScoreResponse(BaseModel):
    entity_id: UUID4
    entity_name: str
    entity_type: str
    composite_score: float
    breakdown: EntityScoreBreakdown
    recommendation: str
    recommendation_level: str  # "book_immediately" | "consider" | "monitor" | "avoid"
    trend_direction: str       # "rising" | "stable" | "declining"
    computed_at: datetime
```

> This is the contract between backend and frontend. Define it once, never change it without a versioned migration.

---

### Day 2.5 — Integration Test of Full Flow

```python
# tests/integration/test_full_score_flow.py
async def test_full_artist_score_flow():
    # 1. Ingest AP Dhillon from Spotify
    entity_id = await ingest_artist_from_spotify("4PULA4EFzYTiOBLo8cFBDr", db)
    
    # 2. Score the entity
    response = await client.get(f"/entities/{entity_id}/score")
    assert response.status_code == 200
    data = response.json()
    
    # 3. Verify structure
    assert "composite_score" in data
    assert 0 <= data["composite_score"] <= 100
    assert "breakdown" in data
    assert "recommendation" in data
    
    # 4. Verify city ranking
    cities = await client.get(f"/entities/{entity_id}/cities")
    assert cities.status_code == 200
    city_data = cities.json()
    assert len(city_data) >= 5
    assert city_data[0]["demand_score"] >= city_data[1]["demand_score"]  # sorted
```

**✅ SPRINT 2 COMPLETE GATE:**
```bash
pytest tests/ -v  # All tests green
# Test key endpoints manually:
curl http://localhost:8000/entities/search?q=AP+Dhillon
curl http://localhost:8000/entities/{id}/score
curl http://localhost:8000/entities/{id}/cities
curl http://localhost:8000/competitors/intelligence?city=Mumbai

# All must return valid JSON with expected structure
```

---

## 🟩 SPRINT 3 — Frontend Foundation (7 Days)

> **Goal**: Beautiful, working UI with real API data on 3 pages.

### Day 3.1 — Next.js Setup + Design System

```bash
# In frontend/
npx create-next-app@latest . --typescript --app --eslint --src-dir --no-tailwind
npm install react-apexcharts apexcharts @nivo/core @nivo/radar @nivo/line
npm install framer-motion zustand @tanstack/react-query axios
npm install react-map-gl mapbox-gl
npm install @radix-ui/react-dialog @radix-ui/react-tooltip
```

**Step 1: Design tokens in `globals.css` FIRST**
```css
/* src/styles/globals.css */
:root {
  --bg-primary: #0A0B0F;
  --bg-surface: #12141A;
  --bg-elevated: #1A1D27;
  --border: rgba(255, 255, 255, 0.06);
  
  --accent-primary: #6C63FF;
  --accent-green: #00D4AA;
  --accent-orange: #FF6B35;
  --accent-pink: #FF4D8D;
  --accent-blue: #4A9EFF;
  --accent-yellow: #FFD60A;
  
  --grad-primary: linear-gradient(135deg, #6C63FF, #4A9EFF);
  --grad-revenue: linear-gradient(135deg, #00D4AA, #6C63FF);
  --grad-danger: linear-gradient(135deg, #FF4D8D, #FF6B35);
  
  --glass-bg: rgba(255, 255, 255, 0.04);
  --glass-border: rgba(255, 255, 255, 0.08);
  
  --font-display: 'Plus Jakarta Sans', sans-serif;
  --font-body: 'Inter', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}
```

**Step 2: Build base components first (no page code yet)**
- `GlassCard.tsx` — the reusable glass card wrapper
- `KPICard.tsx` — animated number counter card
- `ScoreBadge.tsx` — colored score pill
- `TrendArrow.tsx` — ↑ ↓ → arrow with color
- `LoadingSkeleton.tsx` — shimmer loading states

**Test each component in isolation** before using in pages.

---

### Day 3.2 — API Client + Data Hooks

```typescript
// src/lib/api.ts
import axios from 'axios'

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  timeout: 10000,
})

// Request interceptor: add auth token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Response interceptor: handle errors globally
api.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401) {
      // redirect to login
    }
    return Promise.reject(error)
  }
)

export const entityAPI = {
  search: (q: string) => api.get(`/entities/search?q=${q}`),
  getScore: (id: string) => api.get(`/entities/${id}/score`),
  getCities: (id: string) => api.get(`/entities/${id}/cities`),
  compare: (ids: string[]) => api.post('/entities/compare', { ids }),
}
```

```typescript
// src/lib/hooks/useEntityScore.ts
import { useQuery } from '@tanstack/react-query'
import { entityAPI } from '@/lib/api'

export function useEntityScore(entityId: string | null) {
  return useQuery({
    queryKey: ['entity-score', entityId],
    queryFn: () => entityAPI.getScore(entityId!).then(r => r.data),
    enabled: !!entityId,
    staleTime: 5 * 60 * 1000,  // 5 min cache
    retry: 2,
  })
}
```

---

### Day 3.3 — Sidebar + Layout

Build the app shell BEFORE building any page content.
- Sidebar with all 12 nav items, icons, active state
- TopBar with search input, user avatar, notifications
- Layout wrapper with proper overflow handling
- Mobile: sidebar collapses to bottom tabs

**Test on all viewport sizes** before moving to pages.

---

### Day 3.4–3.5 — Home Dashboard Page

Build components in this exact order (each verified before next):
1. KPI cards row (top)
2. Trending Now horizontal scroll
3. Opportunity Feed (AI alerts)
4. Event calendar heatmap (D3)
5. Mini India map (Mapbox)
6. Connect real API data (replace mock data)

---

### Day 3.6 — Intelligence Hub (Entity Search + Profile)

1. Search bar with Elasticsearch-powered autocomplete
2. Search results grid with category icons
3. Entity score card (radar + breakdown cards)
4. City demand section (table + mini map)
5. Comparable entities row

---

### Day 3.7 — City Intelligence (Markets)

1. India Mapbox map with heatmap layer
2. City selector → side panel
3. City intelligence report card
4. Market gap table

**✅ SPRINT 3 COMPLETE GATE:**
```bash
# Frontend runs
npm run dev  # No errors in console

# All 3 pages load with real data
open http://localhost:3000         # Home — KPI cards show real numbers
open http://localhost:3000/intelligence  # Search "AP Dhillon" → score card
open http://localhost:3000/markets       # India map shows city data

# No broken API calls in Network tab
# No console errors
# Lighthouse score > 80 (run once)
```

---

## 🔵 SPRINT 4 — ML Models (7 Days)

> **Goal**: Real ML predictions. NLP sentiment. Trend forecasting.

### Day 4.1 — Add ML Dependencies (carefully)

```bash
# Add to requirements.txt ONLY NOW (not before)
scikit-learn==1.4.2
xgboost==2.0.3
prophet==1.1.5
transformers==4.40.0
torch==2.3.0 --index-url https://download.pytorch.org/whl/cpu
vaderSentiment==3.3.2
joblib==1.4.2
pandas==2.2.2
numpy==1.26.4
```

**Rebuild Docker:**
```bash
docker compose build backend  # Will take ~5min due to torch
docker compose up -d
```

---

### Day 4.2 — Sentiment Analyzer (NLP — No Training Data Needed)

```python
# backend/app/services/ml/sentiment_analyzer.py
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from transformers import pipeline

class SentimentAnalyzer:
    def __init__(self):
        self.vader = SentimentIntensityAnalyzer()
        # DistilBERT for topic extraction
        self.classifier = pipeline(
            "text-classification",
            model="distilbert-base-uncased-finetuned-sst-2-english",
            device=-1  # CPU
        )
    
    def analyze_post(self, text: str) -> dict:
        scores = self.vader.polarity_scores(text)
        return {
            "positive": scores["pos"],
            "negative": scores["neg"],
            "neutral": scores["neu"],
            "compound": scores["compound"],
            "label": "positive" if scores["compound"] > 0.05 
                     else "negative" if scores["compound"] < -0.05 
                     else "neutral"
        }
    
    def extract_topics(self, texts: list[str]) -> dict[str, int]:
        """Count occurrences of known topics across texts"""
        TOPICS = {
            "parking": ["parking", "traffic", "car"],
            "queues": ["queue", "wait", "line", "slow"],
            "sound": ["sound", "audio", "bass", "echo"],
            "pricing": ["expensive", "overpriced", "costly"],
            "performance": ["amazing", "brilliant", "wow", "fire"],
        }
        # Simple keyword counting — no ML needed for this
        topic_counts = {t: 0 for t in TOPICS}
        for text in texts:
            text_lower = text.lower()
            for topic, keywords in TOPICS.items():
                if any(kw in text_lower for kw in keywords):
                    topic_counts[topic] += 1
        return topic_counts
```

**Test:**
```python
def test_sentiment_positive():
    analyzer = SentimentAnalyzer()
    result = analyzer.analyze_post("Absolutely amazing concert! Best night of my life!")
    assert result["label"] == "positive"
    assert result["positive"] > 0.5

def test_sentiment_negative():
    result = analyzer.analyze_post("Terrible parking, waited 2 hours in queue")
    assert result["label"] == "negative"
```

---

### Day 4.3 — Trend Predictor (Prophet)

```python
# backend/app/services/ml/trend_predictor.py
from prophet import Prophet
import pandas as pd

class TrendPredictor:
    def predict_entity_trajectory(
        self, 
        entity_id: UUID, 
        metric: str,
        days_ahead: int,
        db: AsyncSession
    ) -> dict:
        # Get 90 days of historical data
        history = await get_metric_history(entity_id, metric, days=90, db=db)
        
        if len(history) < 30:
            return {"error": "Insufficient data (need 30+ days)"}
        
        df = pd.DataFrame(history, columns=["ds", "y"])
        
        model = Prophet(
            daily_seasonality=False,
            weekly_seasonality=True,
            yearly_seasonality=False,
            changepoint_prior_scale=0.1
        )
        model.fit(df)
        
        future = model.make_future_dataframe(periods=days_ahead)
        forecast = model.predict(future)
        
        return {
            "predicted_value_30d": forecast.iloc[-days_ahead]["yhat"],
            "predicted_value_90d": forecast.iloc[-1]["yhat"],
            "trend_direction": self._detect_direction(forecast),
            "confidence_interval": {
                "lower": forecast.iloc[-1]["yhat_lower"],
                "upper": forecast.iloc[-1]["yhat_upper"]
            }
        }
```

---

### Day 4.4–4.5 — Revenue & Event Success Predictor

**Step 1: Generate training data** (from Ticketmaster + Setlist.fm historical records)
```python
# backend/scripts/prepare_training_data.py
"""
Features: artist_score, city_tier, venue_capacity, 
          day_of_week, month, ticket_price, 
          genre_competition_score, weather_risk, days_until_event
Target:   fill_rate (0-1), gross_revenue
"""
```

**Step 2: Train models**
```python
# backend/scripts/train_models.py
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error
import joblib

# Load training data
df = load_training_data()
features = [...list of feature columns...]

X = df[features]
y_revenue = df["gross_revenue"]
y_fillrate = df["fill_rate"]

X_train, X_test, y_train, y_test = train_test_split(X, y_revenue, test_size=0.2)

revenue_model = xgb.XGBRegressor(
    n_estimators=300,
    max_depth=6,
    learning_rate=0.05,
    random_state=42
)
revenue_model.fit(X_train, y_train)
mae = mean_absolute_error(y_test, revenue_model.predict(X_test))
print(f"Revenue MAE: ₹{mae:,.0f}")  # Target: < ₹5L for events under ₹2Cr

# Save
joblib.dump(revenue_model, "ml_models/revenue_predictor_v1.pkl")
```

**Step 3: Load and serve in API**
```python
# Load once at startup, not on every request
@app.on_event("startup")
async def load_models():
    app.state.revenue_model = joblib.load("ml_models/revenue_predictor_v1.pkl")
    app.state.fillrate_model = joblib.load("ml_models/event_predictor_v1.pkl")
```

---

### Day 4.6–4.7 — More APIs + Remaining Pages

Wire YouTube, Bandsintown, Setlist.fm, TMDB (same pattern as Sprint 1)
Build Trend Radar page and Revenue Simulator page in frontend

**✅ SPRINT 4 COMPLETE GATE:**
```bash
# Test ML predictions
curl -X POST http://localhost:8000/predict/event-success \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "...", "venue_id": "...", "date": "2025-03-15", "ticket_price": 3200}'
# Must return: fill_rate_probability, revenue_estimate, risk_score

# Sentiment test
curl http://localhost:8000/social/sentiment/{entity_id}
# Must return: positive%, negative%, top topics

# All ML model tests pass
pytest tests/ml/ -v
```

---

## 🟣 SPRINT 5 — AI Layer (7 Days)

> **Goal**: Gemini AI copilot and executive dashboard working.

### Day 5.1 — Gemini Client

```python
# backend/app/services/ai/gemini_client.py
import google.generativeai as genai
from app.core.config import settings

genai.configure(api_key=settings.gemini_api_key)

class GeminiClient:
    def __init__(self):
        self.model = genai.GenerativeModel("gemini-1.5-pro")
    
    async def generate_recommendation(self, entity_data: dict) -> str:
        prompt = f"""
        You are an expert entertainment industry analyst for an Indian events platform.
        
        Here is the intelligence data for {entity_data['name']}:
        - Composite Score: {entity_data['score']}/100
        - Spotify Popularity: {entity_data['spotify_popularity']}
        - Trending: {entity_data['trend_direction']}
        - Top Cities by Demand: {entity_data['top_cities']}
        - Sentiment: {entity_data['sentiment']}% positive
        
        Provide a concise 2-3 sentence recommendation for whether to book this 
        artist/entity, which city to target first, and a specific ticket pricing 
        suggestion. Be specific with numbers. Be confident.
        """
        response = await self.model.generate_content_async(prompt)
        return response.text
    
    async def generate_executive_briefing(self, kpi_data: dict) -> str:
        # Similar pattern — inject structured data, get narrative out
        ...
```

---

### Day 5.2–5.3 — RAG Pipeline (AI Copilot)

```python
# backend/app/services/ai/rag_pipeline.py
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain.vectorstores.pgvector import PGVector
from langchain.chains import RetrievalQA

class CopilotRAG:
    def __init__(self):
        self.embeddings = GoogleGenerativeAIEmbeddings(
            model="models/embedding-001",
            google_api_key=settings.gemini_api_key
        )
        self.vectorstore = PGVector(
            connection_string=settings.postgres_url,
            embedding_function=self.embeddings,
            collection_name="liveiq_knowledge"
        )
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-pro",
            temperature=0.3,
            google_api_key=settings.gemini_api_key
        )
    
    async def query(self, question: str) -> AsyncIterator[str]:
        """Streaming response with RAG"""
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 8})
        
        qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            retriever=retriever,
            return_source_documents=True
        )
        
        # Stream response
        async for chunk in self.llm.astream(question):
            yield chunk.content
```

**WebSocket endpoint for streaming chat:**
```python
@router.websocket("/copilot/ws")
async def copilot_websocket(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            question = await websocket.receive_text()
            rag = CopilotRAG()
            async for chunk in rag.query(question):
                await websocket.send_text(chunk)
            await websocket.send_text("[DONE]")  # Signal completion
    except WebSocketDisconnect:
        pass
```

---

### Day 5.4–5.7 — Remaining Pages

Build Executive Dashboard, AI Copilot chat UI, Social Listening, Events Manager, Competitor Intel pages.

**✅ SPRINT 5 COMPLETE GATE:**
```bash
# AI copilot works
# Open browser: http://localhost:3000/copilot
# Ask: "Which city should we launch a Hip-Hop event in?"
# Must stream back a grounded answer with specific data

# Executive briefing works
curl http://localhost:8000/executive/briefing
# Must return AI-generated narrative with KPI analysis

# All 12 pages load without errors
# No 500 errors in API logs
```

---

## ⬛ SPRINT 6 — Production (5 Days)

### Day 6.1 — Auth System

```python
# JWT auth — add to ALL protected routes
# Only /health and /auth/* are public
```

### Day 6.2 — Rate Limiting + Security

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.get("/entities/{id}/score")
@limiter.limit("30/minute")  # 30 requests per minute per IP
async def get_score(...):
    ...
```

### Day 6.3 — Docker Production Config

```bash
# Separate docker-compose.prod.yml with:
# - No volume mounts (no --reload)
# - Gunicorn instead of uvicorn dev server
# - Nginx reverse proxy
# - SSL termination
```

### Day 6.4 — Deploy

**Backend → Railway:**
```bash
railway login
railway init
railway up
```

**Frontend → Vercel:**
```bash
vercel --prod
```

### Day 6.5 — Monitoring

```bash
# Grafana + Prometheus via docker compose
# Alert rules:
# - API p95 latency > 2s → alert
# - Error rate > 1% → alert  
# - DB connection pool exhausted → alert
# - Celery queue depth > 100 → alert
```

**✅ SPRINT 6 COMPLETE GATE:**
```bash
# Production URLs working
curl https://api.liveiq.app/health  # 200 OK
open https://liveiq.app             # Dashboard loads

# Load test
ab -n 1000 -c 50 https://api.liveiq.app/health
# p95 latency < 200ms for /health

# All Celery workers running in production
# Grafana dashboard showing green metrics
```

---

## Error Prevention Rules

### The "Never Do" List

| ❌ Never | ✅ Always |
|---------|----------|
| Commit secrets to git | Use `.env` + `.env.example` pattern |
| Write DB code before testing the API client | Client test → DB wire → integration test |
| Merge to main with failing tests | All tests green before merge |
| Add ML libraries from day 1 | Add them only in Sprint 4 |
| Hardcode any URL or key | Config via `settings.py` + env vars |
| Call an API without error handling | Every `httpx.get()` wrapped in try/except |
| Skip loading states in UI | Every data fetch has skeleton loading UI |
| Test only the happy path | Always write a test for 404, 500, timeout cases |
| Deploy without health checks | Every service has a healthcheck |
| Mix feature work with refactoring | Separate commits, separate PRs |

### Error Handling Template (use for every API call)

```python
async def safe_api_call(client_func, *args, entity_id=None, **kwargs):
    try:
        result = await client_func(*args, **kwargs)
        return result
    except httpx.TimeoutException:
        logger.warning(f"Timeout calling {client_func.__name__} for entity {entity_id}")
        return None  # Caller handles None gracefully
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            logger.warning("Rate limited — backing off 60s")
            await asyncio.sleep(60)
            return await safe_api_call(client_func, *args, **kwargs)  # Retry once
        logger.error(f"HTTP error {e.response.status_code}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error in {client_func.__name__}: {e}")
        return None
```

### Testing Philosophy

```
Unit Tests:       Test pure functions (scoring, normalization) — fast, no DB
Integration Tests: Test API endpoints with real DB — need docker compose
E2E Tests:        Test full user flows (search → score → city) — Playwright
```

Minimum coverage targets:
- Scoring service: **95%** (it's pure math, must be bulletproof)
- API routes: **80%**
- Ingestion clients: **70%** (hard to test 3rd party APIs)
- Frontend: **60%** (component-level tests)

---

## Timeline Summary

| Week | Sprint | Deliverable |
|------|--------|-------------|
| Week 1 (2 days) | Sprint 0 | Docker + DB + skeleton API live |
| Week 1–2 (5 days) | Sprint 1 | Spotify + Trends + Ticketmaster ingesting |
| Week 2–3 (5 days) | Sprint 2 | Score + city ranking API working |
| Week 3–4 (7 days) | Sprint 3 | Home + Intelligence + Cities pages live |
| Week 4–5 (7 days) | Sprint 4 | ML models running, trend + pricing working |
| Week 5–6 (7 days) | Sprint 5 | AI copilot + executive dashboard live |
| Week 7 (5 days) | Sprint 6 | Auth + deployed to production |

**Total: ~38 days to full production.** Realistic for one developer with AI assistance.

---

## Daily Standup Format (Do This Every Day)

```
Yesterday: What did I complete? (Link the commit)
Today:     What exactly am I building? (Specify the file/function)
Blocker:   Is anything blocked? (Don't let blockers sit > 4 hours)
Gate:      What does "done" look like for today's work?
```

This keeps you honest and prevents "I worked all day but nothing works" days.
