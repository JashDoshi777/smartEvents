# LiveIQ — AI Agent Handoff Document
**Project:** LiveIQ — Business Intelligence Platform for Zomato District
**Handoff Date:** 2026-07-24
**Sprint Completed:** Sprint 4 (all items done + audited)
**Next Work:** Sprint 5 (see Future Scope section)

---

> **Hey, incoming AI agent.** This document is written directly for you.
> Before you write a single line of code, read this entire file carefully.
> Then follow the "Read These Files First" section to load full context.
> The user has zero tolerance for hardcoded data — everything must come from the backend API.
> The UI must always feel like Apple iOS 26 glassmorphic design. No emojis anywhere.

---

## 1. What This Project Is

**LiveIQ** is an internal B2B intelligence platform built for **Zomato District**'s business team.
District is India's premium live experiences app (concerts, comedy shows, dining experiences, sports events).

The business team uses LiveIQ to make data-driven decisions on:
- Which artists to sign and for which city
- Which venue to book for an event
- How to price tickets (ML-powered)
- Which cities are expansion opportunities
- Which competitor (BookMyShow, Insider, Paytm) is winning where
- What the top trending artists/comedians/athletes are right now

**This is not a consumer app. It is an internal ops dashboard.**

---

## 2. Tech Stack (Do Not Change These)

| Layer | Technology | Version |
|-------|-----------|---------|
| Backend framework | FastAPI | 0.111.0 |
| Backend runtime | Python | 3.13 |
| Frontend framework | Next.js App Router | 14 |
| Frontend language | TypeScript | strict mode |
| Primary DB | NeonDB (PostgreSQL) | asyncpg |
| Document store | MongoDB | motor (async) |
| Cache / Queue | Redis + Celery | 5.4 |
| ML | scikit-learn | 1.9.0 |
| AI / LLM | Groq (Llama 3.3 70B) | groq>=1.5.0 |
| Animations | framer-motion | — |
| Data fetching | SWR | — |
| Styling | Vanilla CSS Modules | — |

---

## 3. Repository Structure

```
event/
├── backend/                        ← FastAPI Python app
│   ├── main.py                     ← App factory, all routers registered here
│   ├── requirements.txt            ← All Python deps including scikit-learn
│   ├── .env                        ← Secret keys (NOT committed)
│   ├── .env.example                ← Template — read this for all env var names
│   ├── ml_models/                  ← Trained ML model files (joblib)
│   │   ├── pricing_gbr.joblib      ← GradientBoosting price model (R2=0.98)
│   │   ├── fillrate_gbr.joblib     ← GradientBoosting fill-rate model (R2=0.90)
│   │   ├── pricing_encoders.joblib ← LabelEncoder for category feature
│   │   └── pricing_meta.json       ← Training metadata + R2 scores
│   ├── app/
│   │   ├── api/routes/             ← All API endpoints
│   │   │   ├── dashboard.py        ← /dashboard/summary, /dashboard/alerts
│   │   │   ├── entities.py         ← /entities/* (search, score, detail)
│   │   │   ├── trends.py           ← /trends/* (breakout, radar)
│   │   │   ├── cities.py           ← /cities/* (intel, venues, gaps)
│   │   │   ├── competitors.py      ← /competitors/* (intel, gaps, feed)
│   │   │   ├── pricing.py          ← /pricing/* (optimize with ML, elasticity)
│   │   │   ├── executive.py        ← /executive/* (kpis, briefing, portfolio)
│   │   │   ├── copilot.py          ← /copilot/* (chat with Groq)
│   │   │   ├── auth.py             ← /auth/* (JWT, stub for now)
│   │   │   └── health.py           ← GET / (health check)
│   │   ├── models/                 ← SQLAlchemy ORM models
│   │   │   ├── entity.py           ← Entity (artists, comedians, athletes, films)
│   │   │   ├── metrics.py          ← EntityMetric (time-series, TimescaleDB)
│   │   │   ├── event.py            ← Event (concerts, shows, all events)
│   │   │   ├── city.py             ← City (12 Indian cities, market scores)
│   │   │   ├── venue.py            ← Venue (capacity, type, city)
│   │   │   ├── intelligence.py     ← IntelligenceReport (AI verdicts)
│   │   │   └── user.py             ← User (auth)
│   │   ├── workers/                ← Celery background tasks
│   │   │   ├── celery_app.py       ← Beat schedule (6 jobs registered)
│   │   │   ├── entity_metrics.py   ← Collects Last.fm/YouTube/GTrends/NewsAPI
│   │   │   ├── event_sync.py       ← Ticketmaster → NeonDB (writes to DB now)
│   │   │   ├── anomaly_detection.py← IsolationForest → breakout_probability
│   │   │   ├── social_listening.py ← Social media monitoring
│   │   │   ├── trend_signals.py    ← Trend breakout detection
│   │   │   └── competitor_intel.py ← Competitor scraping
│   │   ├── services/
│   │   │   ├── ml/
│   │   │   │   └── pricing_engine.py ← GBR ML engine (loads from ml_models/)
│   │   │   ├── ingestion/          ← API clients
│   │   │   │   ├── ticketmaster_client.py
│   │   │   │   ├── lastfm_client.py
│   │   │   │   ├── youtube_client.py
│   │   │   │   ├── google_trends_client.py
│   │   │   │   ├── newsapi_client.py
│   │   │   │   ├── reddit_client.py
│   │   │   │   ├── spotify_client.py
│   │   │   │   └── tmdb_client.py
│   │   │   ├── groq_service.py     ← Groq Llama 3.3 70B wrapper
│   │   │   ├── scoring/            ← Composite score computation
│   │   │   └── ai/                 ← AI insight generation
│   │   └── core/
│   │       ├── config.py           ← Pydantic settings (reads .env)
│   │       ├── database.py         ← AsyncSessionLocal, get_db, check_db_connection
│   │       ├── mongodb.py          ← Motor client, get_mongo_db
│   │       └── redis_client.py     ← Redis connection
│   ├── scripts/
│   │   ├── seed_entities.py        ← Seeds 51 entities to NeonDB (run once)
│   │   ├── seed_cities.py          ← Seeds 12 Indian cities to NeonDB (run once)
│   │   ├── retrain_pricing_model.py← Retrain ML on real events (run when >50 events)
│   │   └── init_db.sql             ← TimescaleDB hypertable creation
│   └── tests/                      ← pytest test suite
│
└── frontend/                       ← Next.js 14 App Router
    ├── src/
    │   ├── app/
    │   │   ├── globals.css         ← MASTER design system (CSS variables, glassmorphism)
    │   │   ├── layout.tsx          ← Root layout: Sidebar + Topbar
    │   │   ├── page.tsx            ← Dashboard (live KPIs, alerts, portfolio)
    │   │   ├── intelligence/       ← Entity Intelligence Hub
    │   │   ├── pricing/            ← Pricing Optimizer (ML-powered)
    │   │   ├── copilot/            ← AI Copilot (Groq chat)
    │   │   ├── trends/             ← Trend Radar
    │   │   ├── markets/            ← City Markets + Venue Selector + Restaurant Engine
    │   │   ├── competitors/        ← Competitor Intel
    │   │   ├── events/             ← Fill Rate Monitor
    │   │   ├── executive/          ← Executive Suite
    │   │   └── settings/           ← Settings (stub — needs to be built in Sprint 5)
    │   ├── components/
    │   │   ├── layout/
    │   │   │   ├── Sidebar.tsx     ← Navigation sidebar
    │   │   │   └── Topbar.tsx      ← Top bar with theme toggle
    │   │   ├── ui/
    │   │   │   ├── GlassCard.tsx   ← Core glassmorphic card component
    │   │   │   └── MetricTile.tsx  ← KPI tile component
    │   │   └── providers/
    │   │       └── ThemeProvider.tsx ← Dark/Light mode context
    │   └── lib/
    │       └── api.ts              ← All API calls + TypeScript types
    └── package.json
```

---

## 4. Read These Files First (Critical Context)

AI agent: Open and fully read each of these files before doing any work.
They contain the full design decisions and sprint history.

ARCHITECTURE:
  c:\Users\Jeel\Desktop\event\backend\main.py
  c:\Users\Jeel\Desktop\event\backend\.env.example
  c:\Users\Jeel\Desktop\event\frontend\src\app\globals.css
  c:\Users\Jeel\Desktop\event\frontend\src\lib\api.ts

MODELS (understand data shape before touching anything):
  c:\Users\Jeel\Desktop\event\backend\app\models\entity.py
  c:\Users\Jeel\Desktop\event\backend\app\models\metrics.py
  c:\Users\Jeel\Desktop\event\backend\app\models\event.py
  c:\Users\Jeel\Desktop\event\backend\app\models\city.py
  c:\Users\Jeel\Desktop\event\backend\app\models\venue.py

KEY ROUTES:
  c:\Users\Jeel\Desktop\event\backend\app\api\routes\dashboard.py
  c:\Users\Jeel\Desktop\event\backend\app\api\routes\pricing.py
  c:\Users\Jeel\Desktop\event\backend\app\api\routes\entities.py
  c:\Users\Jeel\Desktop\event\backend\app\api\routes\cities.py

ML ENGINE:
  c:\Users\Jeel\Desktop\event\backend\app\services\ml\pricing_engine.py
  c:\Users\Jeel\Desktop\event\backend\app\workers\anomaly_detection.py
  c:\Users\Jeel\Desktop\event\backend\ml_models\pricing_meta.json

---

## 5. How to Start the App Locally

### Backend
  cd c:\Users\Jeel\Desktop\event\backend
  venv\Scripts\activate
  uvicorn main:app --reload --port 8000
  API docs at: http://localhost:8000/docs

### Frontend
  cd c:\Users\Jeel\Desktop\event\frontend
  npm run dev
  App at: http://localhost:3000

### Seed Data (run once after fresh DB)
  venv\Scripts\python scripts\seed_entities.py   (51 entities)
  venv\Scripts\python scripts\seed_cities.py     (12 cities + venues)

---

## 6. UI/UX Rules — Non-Negotiable

1. Apple iOS 26 Glassmorphic UI — every component must feel like iOS 26
2. No emojis anywhere — not in code, not in UI, not in text content
3. Dark mode by default — with a toggle to light mode (ThemeProvider handles this)
4. No purple — the accent color is Apple blue (#0a84ff)
5. No hardcoded data — if backend is offline, show empty states. Never fake numbers
6. Not a stock dashboard — feels like District/Zomato (events, artists, experiences)
7. Smooth animations — use framer-motion for all transitions
8. Apple-like typography — SF Pro Display → Inter fallback (in globals.css)
9. Glassmorphism tokens in globals.css:
   --glass-bg     = rgba(255,255,255,0.05)
   --glass-border = rgba(255,255,255,0.08)
   --glass-blur   = backdrop-filter: blur(24px) saturate(180%)
   --surface      = rgba(18,18,20,0.95) (dark mode base)
10. Run npx tsc --noEmit after EVERY frontend change. Zero errors required.

---

## 7. Completed Work — Sprints 0 to 4

Sprint 0: FastAPI foundation, SQLAlchemy models, NeonDB/MongoDB/Redis clients
Sprint 1: All data ingestion clients (Ticketmaster, Last.fm, YouTube, Google Trends, NewsAPI, Reddit, Spotify, TMDB)
Sprint 2: Composite scoring engine, entity/trends routes, 51 entities seeded, 12 cities seeded
Sprint 3: Cities/Competitors/Executive/Pricing/Dashboard/Copilot routes all live
Sprint 4:
  - All 9 frontend pages complete (zero TypeScript errors)
  - event_sync.py: now writes to NeonDB (was TODO since Sprint 1)
  - anomaly_detection.py: NEW IsolationForest ML worker, writes breakout_probability
  - pricing_engine.py: NEW GBR ML model (R2=0.98 price, R2=0.90 fill rate)
  - /pricing/optimize now returns: recommended_price + predicted_fill_rate + sensitivity_curve
  - ml_models/: 4 trained model files in correct location
  - Sprint 4 audit: 55/55 checks passed, 2 bugs found and fixed

---

## 8. API Endpoint Map

| Frontend Page | API Calls |
|---|---|
| Dashboard    | GET /dashboard/summary, GET /dashboard/alerts |
| Intelligence | GET /entities/?search=, GET /entities/{id} |
| Pricing      | POST /pricing/optimize, GET /pricing/benchmarks |
| Copilot      | POST /copilot/chat |
| Trends       | GET /trends/breakout, GET /trends/radar |
| Markets      | GET /cities/top, GET /cities/{city}/intelligence, GET /cities/{city}/venues |
| Competitors  | GET /competitors/intelligence, GET /competitors/activity-feed |
| Events       | GET /entities/?with_events=true |
| Executive    | GET /executive/kpis, GET /executive/briefing, GET /executive/portfolio |

---

## 9. Known Technical Debt

| Issue | Severity |
|---|---|
| auth.py is a stub — no real authentication | Medium |
| predict.py is a stub — /predict returns 404 | Low |
| social.py is a stub — social listening via worker only | Low |
| competitor_intel.py worker is only 472 bytes, barely implemented | Medium |
| trend_signals.py worker is only 478 bytes | Medium |
| Spotify client partially wired (strict rate limits) | Low |
| No TTL index on MongoDB breakout_alerts collection | Low |
| No pagination on /entities (add ?page=&limit= as entities grow) | Medium |
| ML models are synthetic — retrain when >50 real events exist | Medium |
| executive/page.tsx is thin (4.5KB) — needs portfolio table + AI briefing | Low |

---

## 10. Future Scope — Sprint 5 and Beyond

SPRINT 5A — Retrain ML on Real Events
  Run: venv\Scripts\python scripts\retrain_pricing_model.py
  (Already written. Run when event_sync has synced >50 completed events)

SPRINT 5B — Settings Page
  settings/page.tsx is a stub. Build: API key status, theme prefs, entity watchlist, report export.

SPRINT 5C — Event Deal Modeler (/events/model)
  POST /events/model: artist + city + venue → full P&L simulation
  Shows: break-even tickets, revenue at 3 fill-rate scenarios

SPRINT 5D — Notification System
  Backend already writes alerts to MongoDB.
  Build: bell icon in Topbar, dropdown with breakout alerts
  Add WebSocket: ws://localhost:8000/ws/alerts

SPRINT 5E — Report Export
  GET /executive/report/pdf using reportlab or weasyprint
  Include: KPI summary, top 10 entities, city market map, AI briefing

SPRINT 6A — Production-Grade Fill Rate Predictor
  New features: days_since_last_event_in_city, competitor_events_same_weekend
  Use cross_val_score to validate quality

SPRINT 6B — Artist Pairing Recommender
  POST /intelligence/pair-recommend
  Input: city + date + budget → two artists that pair well (cosine similarity on score vectors)

SPRINT 6C — Demand Forecasting (Prophet)
  GET /intelligence/{entity_id}/forecast?city=Mumbai&months=6
  Use Facebook Prophet on google_trend_score time-series

SPRINT 7 — Platform Features
  7A: Multi-user JWT auth with roles (viewer/analyst/admin)
  7B: Watchlist — users watch specific entities, get priority alerts
  7C: Venue Availability Calendar — heatmap of open/booked weekends
  7D: Real Zomato restaurant API integration for Markets page

---

## 11. User Notes

- Goes by "Jeel"
- Runs on Windows (PowerShell) — use Select-Object -Last 5 not tail
- Will catch hardcoded data immediately — never do it
- Dislikes when things look like "stock dashboards"
- When he says "continue" — check what is left in the current sprint plan first
- Appreciates proactive audits before declaring work done

---

*End of handoff. The foundation is solid. Keep it Apple-clean.*
