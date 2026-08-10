# 🎵 LiveIQ — Deep Research Report & Revised Implementation Plan
### Full Event Universe · ML vs Script Decisions · Visualization Architecture

---

## Part 1: Zomato District — Full Event Universe

> **Context**: District was built by combining Zomato LIVE + Paytm Insider + TicketNew (₹2,048 Cr acquisition). It inherited the entire Paytm Insider catalog, making it India's broadest going-out platform.

### The 9 Event Category Pillars

Our platform must support intelligence across **all 9**, not just music/artists.

---

#### 🎵 1. Music & Concerts
- Large-scale concerts (stadium/arena/amphitheatre)
- Music festivals (multi-day, multi-stage: Lollapalooza India, NH7 Weekender, Sunburn)
- Genre-specific shows: Bollywood, Punjabi Pop, Classical, Hip-Hop, EDM, Indie, Jazz, Sufi, K-Pop
- Club nights / DJ sets
- Intimate gig formats (100–500 cap)
- International artist India tours (Coldplay, Ed Sheeran, Imagine Dragons)

**Intelligence needed**: Artist scoring, pricing optimization, city demand, trend prediction

---

#### 🎬 2. Movies
- Multiplex bookings (PVR INOX, Cinepolis, Miraj, SPI)
- Special screenings (IMAX, 4DX, Dolby, drive-in)
- Film festivals (MAMI, IFFI, BIFFES)
- OTT premiere events
- Regional cinema (Tamil, Telugu, Kannada, Marathi, Bengali)

**Intelligence needed**: Box office prediction, occupancy optimization, regional language demand, optimal showtime pricing

---

#### 🏏 3. Sports
- Cricket: IPL, domestic T20, Test matches (BCCI venues)
- Football: ISL, I-League, international friendlies
- Kabaddi: PKL (Pro Kabaddi League)
- Badminton: Premier Badminton League
- Tennis: Challenger/ATP India events
- Wrestling: WWE India shows
- F1/MotoGP viewing events
- Fantasy sports meetups, watch parties

**Intelligence needed**: Team popularity by city, seat pricing by zone, rivalry matchup demand, seasonal calendar conflicts

---

#### 😂 4. Comedy & Standup
- Solo standup specials (Zakir Khan, Vir Das, Kanan Gill, Biswa, Kunal Kamra)
- Open mics (50–200 capacity)
- Group comedy shows (collaborative lineups)
- Improv theatre
- Comedy festivals (Headliners Comedy Festival)
- Corporate shows (private events)

**Intelligence needed**: Comedian popularity + city affinity, price elasticity, venue-size fit, best days (Fri/Sat spike)

---

#### 🎭 5. Theatre & Cultural
- Hindi/English plays
- Regional language theatre (Marathi Natak, Bengali theatre)
- Classical dance performances (Bharatanatyam, Kathak, Odissi)
- Musical theatre / Broadway-style productions
- Puppet shows / shadow theatre (family segment)
- Art exhibitions
- Cultural festivals (Hornbill Festival adjacent events, Navratri shows)

**Intelligence needed**: Regional audience preferences, seasonal cultural calendar (festivals), venue acoustics scoring

---

#### 🎢 6. Experiences & Attractions
- Amusement parks: Wonderla, Imagicaa, Adlabs Aquamagica
- Water parks, adventure zones
- Escape rooms (Smaaash, others)
- VR gaming centres
- Bowling, go-karting, laser tag (Timezone, PVR Fun Republic)
- Nature & wildlife experiences
- Haunted houses, seasonal experiences (Halloween)
- Planetariums, science museums

**Intelligence needed**: Seasonal demand patterns, family vs youth segmentation, weekend vs weekday demand curves, weather correlation

---

#### 🧪 7. Workshops & Experiences (Learning-Based)
- Art & craft workshops (pottery, painting, macramé)
- Cooking classes (professional chefs, cuisines)
- Photography/filmmaking workshops
- Music learning (guitar, tabla, singing)
- Fitness: yoga retreats, dance workshops (Zumba, Bollywood dance)
- Wellness: meditation, journaling, mindfulness
- Tech: coding bootcamps, AI workshops
- Business: entrepreneurship, pitch events, networking
- Kids' learning: science, art, coding

**Intelligence needed**: Hobbyist trend detection, price sensitivity, city-level interest mapping, instructor popularity scoring

---

#### 🍽️ 8. Dining Experiences
- Fine dining reservations
- Pop-up restaurants / chef's table events
- Food festivals (Mumbai Street Food Festival, etc.)
- Brewery tours / wine tastings
- Themed dining (murder mystery dinners, silent dining)
- Culinary tours
- Restaurant week events

**Intelligence needed**: Cuisine trend tracking, footfall prediction, cuisine popularity by neighborhood, competitive pricing vs nearby restaurants

---

#### 🌃 9. Nightlife & Shopping Events
- Club nights, bar takeovers
- Rooftop parties, villa parties
- Flash sales, brand pop-ups
- End-of-season sales (curated by District)
- Night markets
- Brand launch events

**Intelligence needed**: Nightlife hotspot mapping, brand event ROI, youth demographic targeting, day-of-week optimization

---

## Part 2: ML vs Python Scripts — Module-by-Module Decision

> **Key Principle**: ML solves what rules can't. Rules solve what ML is overkill for. The best production systems use both.

---

### Decision Framework Applied to Each Module

| Module | Approach | Why |
|--------|----------|-----|
| **M1: Entity Scoring** | ⚡ Weighted Python Script (v1) → ML (v2) | Rules first: weighted average of normalized signals. You control weights. ML later when you have labeled outcome data. |
| **M2: Trend Prediction** | 🤖 ML Required | Time-series pattern detection across 15+ signals simultaneously. Human rules can't spot the inflection points. LSTM or Prophet. |
| **M3: City Demand Ranking** | ⚡ Python Script | Normalize Google Trends + Setlist data per city. Simple ranked sort. No ML needed — it's just aggregation. |
| **M4: Ticket Pricing** | 🤖 ML Required | Demand elasticity curves are non-linear and vary by genre × city × artist. XGBoost regression learns these. Rules can't. |
| **M5: Competitor Intel** | ⚡ Python Script | Scrape → parse → aggregate → spot count trends. No prediction needed, just pattern counting + alerting. |
| **M6: AI Recommendation** | 🔀 Hybrid | Rules-based filtering (budget, genre, city) → ML re-ranking by predicted revenue. Best of both. |
| **M7: Social Listening** | 🤖 ML Required | NLP sentiment + topic extraction from unstructured social text. Can't be done with rules at scale. Use transformers (VADER + DistilBERT). |
| **M8: Event Success Predictor** | 🤖 ML Required | Multi-variable classification (fill rate, revenue, risk). Historical data trains a gradient boosting ensemble. |
| **M9: Exec Dashboard AI** | 🤖 LLM (Gemini) | Narrative generation and root cause analysis is an LLM job — structured data in, plain English explanation out. |
| **M10: AI Copilot** | 🤖 LLM + RAG | Natural language → SQL/vector lookup → grounded answer. Requires Gemini + pgvector. No other way. |

---

### Detailed Rationale

#### Where Python Scripts Are Enough (No ML Needed)

**Module 1 — Scoring Engine (v1)**
```python
# Pure Python weighted score — fully transparent, debuggable, fast to ship
def compute_score(artist):
    scores = {
        "spotify_popularity": normalize(artist.spotify_pop, 0, 100) * 0.20,
        "follower_growth":     normalize(artist.follower_delta_30d) * 0.15,
        "google_trend":        normalize(artist.trend_score) * 0.15,
        "youtube_views":       normalize(artist.yt_views_30d) * 0.10,
        "sentiment":           normalize(artist.sentiment_score) * 0.10,
        "bandsintown_demand":  normalize(artist.rsvp_score) * 0.10,
        "news_mentions":       normalize(artist.news_count_7d) * 0.05,
        ...
    }
    return sum(scores.values())
```
This is **transparent** (executives can explain it), **fast to ship**, and **works with zero training data**. Upgrade to XGBoost later when you have outcome labels (did the event sell out?).

**Module 3 — City Demand**
```python
# Pure aggregation — no ML needed
def rank_cities_for_entity(entity_id, category):
    cities = []
    for city in TRACKED_CITIES:
        demand = (
            get_google_trends(entity_id, city) * 0.35 +
            get_social_mentions(entity_id, city) * 0.25 +
            get_historical_event_attendance(entity_id, city) * 0.25 +
            get_competitor_events(entity_id, city) * 0.15
        )
        cities.append({"city": city, "demand_score": demand})
    return sorted(cities, key=lambda x: x["demand_score"], reverse=True)
```

**Module 5 — Competitor Intelligence**
```python
# Scraping + counting + trend detection — no ML needed
# BookMyShow, Insider, Paytm scrape → aggregate by genre × city
# Detect: count(events) this month vs last month per genre per city
```

---

#### Where ML is Non-Negotiable

**Module 2 — Trend Prediction**: You're looking for "hockey stick" inflection patterns in multi-variate time series. Human rules can't catch: "artist whose Reels saves tripled while search volume was flat, then both jumped — that's 3 weeks before blowup." LSTM or Facebook Prophet for time-series, combined with anomaly detection.

**Module 4 — Ticket Pricing**: Price elasticity is non-linear and depends on: genre + city + day-of-week + competition + weather + artist tier + venue type. An XGBoost regression model learns this from historical data. No rule can capture all these interactions.

**Module 7 — Sentiment**: Processing 10,000+ social posts per day into: "parking mentioned negatively 892 times, sound quality mentioned positively 1,200 times" requires NLP. Use VADER (fast, no training needed) for polarity, DistilBERT for topic extraction.

**Module 8 — Event Success Predictor**: This is pure supervised learning. Training data = past event records (artist + venue + city + date + price → actual fill rate + revenue). XGBoost Classifier for sell-out probability, XGBoost Regressor for revenue.

---

#### ML Models Required — Summary

| Model | Type | Library | Training Data Needed |
|-------|------|---------|---------------------|
| Trend Predictor | Time-series forecasting | Prophet / statsmodels | 90+ days of artist metrics |
| Revenue Predictor | Regression | XGBoost | Historical event data (Ticketmaster + Setlist.fm) |
| Sentiment Analyzer | NLP | VADER + DistilBERT (HuggingFace) | None (pre-trained models) |
| Event Success Predictor | Classification + Regression | XGBoost Ensemble | Historical event outcomes |
| Price Optimizer | Regression | XGBoost | Historical ticket + sales data |
| Anomaly Detector | Unsupervised | IsolationForest (sklearn) | Artist metric history |

---

## Part 3: Visualization Stack — What Will Look Amazing

### Recommended Stack (Final Decision)

```
Primary Charts:   ApexCharts (react-apexcharts)
                  → Best out-of-the-box animations, gradients, dark mode
                  → Built for exactly this type of SaaS analytics dashboard

Specialty Charts: Nivo
                  → Radar charts (artist score breakdown)
                  → Heatmaps (city demand grids)
                  → Bump charts (ranking over time)
                  → Treemaps (genre market share)

Geographic Maps:  Mapbox GL + react-map-gl
                  → Interactive India map with city demand heatlayer
                  → Venue location pins with popup cards

Complex Custom:   D3.js (sparingly)
                  → The "breakout prediction" wave chart
                  → Competitor market share radial chart
                  → Artist comparison spider chart (full custom)

Real-time:        Framer Motion (animations)
                  → Number counter animations on KPI cards
                  → Chart entry animations
                  → Page transitions
```

### Design System Specification

**Color Palette** (Dark Mode First):
```css
--bg-primary:     #0A0B0F;   /* Near-black, not pure black */
--bg-surface:     #12141A;   /* Card backgrounds */
--bg-elevated:    #1A1D27;   /* Elevated components */
--border:         rgba(255,255,255,0.06);

/* Accent Colors */
--accent-primary: #6C63FF;   /* Vibrant purple — main brand */
--accent-green:   #00D4AA;   /* Revenue, positive metrics */
--accent-orange:  #FF6B35;   /* Warnings, high competition */
--accent-pink:    #FF4D8D;   /* Social/trending metrics */
--accent-blue:    #4A9EFF;   /* Information, neutral */
--accent-yellow:  #FFD60A;   /* AI insights, copilot */

/* Gradient Recipes */
--grad-primary:   linear-gradient(135deg, #6C63FF, #4A9EFF);
--grad-revenue:   linear-gradient(135deg, #00D4AA, #6C63FF);
--grad-danger:    linear-gradient(135deg, #FF4D8D, #FF6B35);
--grad-trend:     linear-gradient(135deg, #FFD60A, #FF6B35);

/* Glassmorphism */
--glass-bg:       rgba(255,255,255,0.04);
--glass-border:   rgba(255,255,255,0.08);
--glass-blur:     backdrop-filter: blur(20px);
```

**Typography**:
```
Display:  "Plus Jakarta Sans" — modern, premium, variable weight
Body:     "Inter" — highly legible, widely supported
Mono:     "JetBrains Mono" — code blocks, metric values
```

### Chart-by-Chart Visualization Plan

| Chart | Library | Style |
|-------|---------|-------|
| **Artist score radar** | Nivo Radar | 6-axis radar, purple gradient fill, animated on load |
| **Metric trend lines** | ApexCharts Line | Area fill with gradient, smooth bezier, animated |
| **Revenue bar charts** | ApexCharts Bar | Gradient bars, rounded corners, hover tooltips |
| **City demand map** | Mapbox + heatmap layer | India map, orange-red heatmap overlay, zoomable |
| **Genre treemap** | Nivo Treemap | Color by momentum, label size = market size |
| **Breakout prediction** | D3 Wave | Custom "rising tide" wave chart, animated |
| **Competitor market share** | ApexCharts Donut | Animated entry, multi-ring for platform breakdown |
| **Social sentiment** | Custom CSS + ApexCharts | Horizontal bar with emoji labels |
| **Ranking over time** | Nivo BumpChart | Artist rank trajectories over 30/60/90 days |
| **Event calendar** | Custom D3 | Heat calendar (GitHub-style) for event density |
| **KPI cards** | Framer Motion counters | Number rolls up on load, color coded |
| **Category heatgrid** | Nivo Heatmap | Genre × City × Month demand grid |
| **Price elasticity curve** | D3 custom | Demand curve with optimal price marker |

### Example: Artist Score Card (UI Spec)

```
┌─────────────────────────────────────────────────────────┐
│  glass card · purple border glow · blur(20px) backdrop  │
│                                                         │
│  AP Dhillon             [BOOK NOW] ← gradient button    │
│  ════════════════════════════════════════════════════   │
│  SCORE  91/100          ↑ +7 this week                  │
│  ████████████████░░ 91%  (animated progress bar)        │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │        RADAR CHART (Nivo, animated)              │   │
│  │    Streaming  ●───────────── 91                  │   │
│  │   /          \                                   │   │
│  │  Social  Sentiment                               │   │
│  │   \          /                                   │   │
│  │    Demand──Risk                                  │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  Spotify: 12.3M listeners ↑23%    [area sparkline]     │
│  YouTube: 840M views ↑18%         [area sparkline]     │
│  Sentiment: 82% Positive           [bar chart]         │
│                                                         │
│  Top Cities: Mumbai · Delhi · Toronto                   │
│  Best Venue Size: 8,000–15,000 capacity                 │
└─────────────────────────────────────────────────────────┘
```

---

## Part 4: Revised Complete Architecture

### Updated Data Sources — All 9 Category Coverage

| Category | Primary APIs | Supplementary Scraping |
|----------|-------------|------------------------|
| Music/Artists | Spotify, YouTube, Bandsintown, Songkick, Setlist.fm, Last.fm | Billboard India charts |
| Movies | TMDB API, OMDB API, CBFC records | BookMyShow show listings |
| Sports | ESPN API, Cricbuzz API, Sportmonks | IPL/ISL official sites |
| Comedy | No dedicated API | YouTube comedian channels, BMS comedy listings |
| Theatre | No dedicated API | Bookmyshow theatre, cultural org websites |
| Experiences | Wonderla/Imagicaa APIs (if available) | BMS activities section scrape |
| Workshops | Eventbrite API (has workshops) | Local Facebook events, Meetup.com |
| Dining | Zomato public API, Google Places | Restaurant week sites |
| Nightlife | Foursquare/Google Places | Club websites, Paytm Insider nightlife |

### Entity Model (Revised for All Categories)

Instead of just "Artists", we have **Entities**:

```python
class Entity:
    entity_type: Enum[
        ARTIST,        # Musicians, bands, DJs
        MOVIE,         # Films  
        SPORTS_TEAM,   # IPL team, ISL club
        COMEDIAN,      # Stand-up comedians
        THEATRE_GROUP, # Theatre companies
        ATTRACTION,    # Amusement parks, venues
        WORKSHOP,      # Workshop series / instructors
        RESTAURANT,    # Dining experiences
        BRAND          # Shopping/lifestyle events
    ]
    # Then all modules work on ANY entity type
```

This means:
- "Score me Zakir Khan for Bangalore" → same M1 engine, comedy parameters
- "Should Royal Challengers Bengaluru host a watch party in Pune?" → sports demand model
- "Which comedy acts are trending in Tier 2 cities?" → trend engine, comedy category filter

### Scoring Model — Per-Category Weights

| Signal | Music | Comedy | Sports | Movie | Experience |
|--------|-------|--------|--------|-------|------------|
| Social media growth | 25% | 20% | 15% | 10% | 5% |
| Streaming/views | 20% | 15% | 5% | 20% | 0% |
| Search trends | 15% | 15% | 20% | 25% | 15% |
| Historical attendance | 15% | 20% | 25% | 10% | 30% |
| Sentiment score | 10% | 15% | 15% | 15% | 20% |
| Competitor activity | 10% | 10% | 15% | 15% | 20% |
| News coverage | 5% | 5% | 5% | 5% | 10% |

---

## Part 5: Final Tech Stack Decision

### Backend
```
FastAPI (Python)           — API layer, async, auto docs
PostgreSQL + TimescaleDB   — Primary DB + time-series metrics
MongoDB                    — Raw social data, unstructured docs
Redis                      — Cache, Celery broker, rate limiting
Celery                     — Scheduled data collection workers
Elasticsearch              — Full-text entity search
pgvector                   — Vector embeddings for AI Copilot
```

### ML / AI
```
scikit-learn + XGBoost     — Scoring, prediction, classification
Facebook Prophet           — Time-series trend forecasting
VADER + DistilBERT         — Sentiment analysis (HuggingFace)
IsolationForest            — Anomaly/breakout detection
Google Gemini 1.5 Pro      — Narrative AI, executive briefings
LangChain                  — RAG pipeline for AI Copilot
```

### Scraping
```
Playwright                 — Headless browser (BMS, Insider, Paytm)
BeautifulSoup              — HTML parsing
httpx                      — Async HTTP for APIs
APScheduler                — Cron-like scheduling for scrapers
```

### Frontend
```
Next.js 14 (App Router)    — Framework
ApexCharts                 — Primary charts (line, bar, donut, area)
Nivo                       — Specialty charts (radar, heatmap, bump, treemap)
D3.js                      — Custom bespoke visualizations
Mapbox GL                  — Geographic demand maps
Framer Motion              — Animations, page transitions, counters
Zustand                    — Client state management
TanStack Query             — Server state, caching, refetch
Google Fonts: Plus Jakarta Sans + Inter + JetBrains Mono
```

### Infrastructure
```
Docker + Docker Compose    — Dev environment
GitHub Actions             — CI/CD
Railway                    — Backend hosting (free tier: $5/mo after)
Vercel                     — Frontend hosting (free)
Cloudflare                 — CDN + rate limiting
```

---

## Part 6: Final Database Schema

```sql
-- ==================== CORE ENTITIES ====================
entities (
    id UUID PRIMARY KEY,
    name VARCHAR(255),
    entity_type ENUM('artist','movie','sports_team','comedian',
                     'theatre_group','attraction','workshop',
                     'restaurant','brand'),
    category VARCHAR(100),         -- sub-category
    sub_categories TEXT[],
    external_ids JSONB,            -- {spotify_id, tmdb_id, cricbuzz_id, ...}
    image_url VARCHAR(500),
    country VARCHAR(50),
    language VARCHAR(50),
    verified BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ==================== TIME-SERIES METRICS ====================
entity_metrics (
    time        TIMESTAMPTZ NOT NULL,
    entity_id   UUID REFERENCES entities(id),
    -- Streaming / Views
    monthly_listeners   INTEGER,
    total_plays_7d      BIGINT,
    youtube_views_30d   BIGINT,
    -- Social
    instagram_followers BIGINT,
    instagram_growth_7d FLOAT,
    twitter_mentions_7d INTEGER,
    reddit_posts_7d     INTEGER,
    -- Trend
    google_trend_score  FLOAT,   -- 0-100, normalized
    -- Sentiment
    sentiment_positive  FLOAT,
    sentiment_negative  FLOAT,
    sentiment_neutral   FLOAT,
    -- Composite
    composite_score     FLOAT,
    trend_velocity      FLOAT,   -- change in composite score
    PRIMARY KEY (time, entity_id)
);
-- TimescaleDB: SELECT create_hypertable('entity_metrics', 'time');

-- ==================== EVENTS ====================
events (
    id UUID PRIMARY KEY,
    entity_id UUID REFERENCES entities(id),
    venue_id UUID REFERENCES venues(id),
    category event_category_enum,
    date TIMESTAMPTZ,
    doors_open TIMESTAMPTZ,
    ticket_price_min NUMERIC(10,2),
    ticket_price_max NUMERIC(10,2),
    capacity INTEGER,
    tickets_sold INTEGER,
    fill_rate FLOAT,
    gross_revenue NUMERIC(14,2),
    platform VARCHAR(50),       -- 'district','bookmyshow','insider'
    status VARCHAR(20),         -- 'upcoming','sold_out','completed','cancelled'
    source VARCHAR(50),
    scraped_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ==================== VENUES ====================
venues (
    id UUID PRIMARY KEY,
    name VARCHAR(255),
    city_id UUID REFERENCES cities(id),
    address TEXT,
    lat FLOAT, lng FLOAT,
    capacity INTEGER,
    venue_type VARCHAR(50),     -- 'stadium','theatre','club','arena','outdoor'
    suitable_categories TEXT[], -- ['music','comedy','sports']
    avg_fill_rate FLOAT,
    avg_ticket_price NUMERIC(10,2),
    rating FLOAT,
    amenities JSONB
);

-- ==================== CITIES ====================
cities (
    id UUID PRIMARY KEY,
    name VARCHAR(100),
    state VARCHAR(100),
    country VARCHAR(50) DEFAULT 'India',
    tier INTEGER,               -- 1=metro, 2=major, 3=emerging
    population BIGINT,
    avg_monthly_income NUMERIC,
    top_categories TEXT[],      -- ['music','comedy','sports']
    active_on_district BOOLEAN DEFAULT true
);

-- ==================== INTELLIGENCE ====================
entity_predictions (
    id UUID PRIMARY KEY,
    entity_id UUID,
    venue_id UUID,
    city_id UUID,
    prediction_type VARCHAR(50), -- 'event_success','revenue','demand'
    event_date DATE,
    ticket_price_input NUMERIC,
    predicted_fill_rate FLOAT,
    predicted_revenue NUMERIC,
    predicted_attendance INTEGER,
    risk_score FLOAT,            -- 0-1, lower is better
    confidence FLOAT,
    model_version VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

competitor_listings (
    id UUID PRIMARY KEY,
    platform VARCHAR(50),       -- 'bookmyshow','insider','paytm'
    entity_name VARCHAR(255),
    city VARCHAR(100),
    category VARCHAR(100),
    event_date DATE,
    price_range_min NUMERIC,
    price_range_max NUMERIC,
    status VARCHAR(50),         -- 'available','filling_fast','sold_out'
    scraped_at TIMESTAMPTZ
);

social_posts (
    id UUID PRIMARY KEY,
    platform VARCHAR(50),
    entity_id UUID,
    post_id VARCHAR(255),
    content TEXT,
    sentiment FLOAT,
    themes TEXT[],
    engagement INTEGER,
    created_at TIMESTAMPTZ
);

trend_signals (
    id UUID PRIMARY KEY,
    entity_id UUID,
    signal_type VARCHAR(50),    -- 'reels_spike','search_breakout','news_burst'
    value FLOAT,
    delta_7d FLOAT,
    delta_30d FLOAT,
    detected_at TIMESTAMPTZ
);

-- AI layer
embeddings (id UUID, entity_type VARCHAR, entity_id UUID, 
            content TEXT, embedding vector(768));
exec_briefings (id UUID, city_id UUID, date DATE, 
                content TEXT, recommendations JSONB);
ai_sessions (id UUID, user_id UUID, messages JSONB[], created_at TIMESTAMPTZ);
```

---

## Part 7: Phased Build Plan (Revised)

### Phase 1 — Foundation & Data (Week 1–2)
- [ ] FastAPI project skeleton with proper folder structure
- [ ] PostgreSQL + TimescaleDB schema setup
- [ ] MongoDB + Redis setup (Docker Compose)
- [ ] Celery workers infrastructure
- [ ] API integrations: Spotify, YouTube, Google Trends, Ticketmaster, TMDB
- [ ] Entity ingestion pipeline (music + movies first)
- [ ] Basic entity scoring (Python weighted script — M1 v1)
- [ ] Next.js project setup + design system (colors, fonts, components)

### Phase 2 — Music & Comedy Intelligence (Week 3–4)
- [ ] Full artist/comedian scoring engine (M1) — all signals wired
- [ ] City demand ranking (M3) — Python script
- [ ] Ticket pricing model (M4) — v1 XGBoost
- [ ] Social listening pipeline (M7) — VADER sentiment
- [ ] Frontend: Artist search, score card, city demand map
- [ ] Frontend: Pricing simulator page

### Phase 3 — Sports, Movies & Trend Engine (Week 5–6)
- [ ] Sports entity model (cricbuzz, ESPN integration)
- [ ] Movie intelligence model (TMDB + BMS scrape)
- [ ] Trend Prediction engine (M2) — Prophet time-series
- [ ] Competitor scraper: BMS, Insider, Paytm (M5)
- [ ] Frontend: Trend radar, competitor intelligence pages
- [ ] Frontend: Sports & Movies category pages

### Phase 4 — Experience, Workshop & AI Layer (Week 7–8)
- [ ] Experiences & workshops entity model
- [ ] Eventbrite + Meetup integration
- [ ] Event success predictor (M8) — full ensemble
- [ ] Recommendation engine (M6) — hybrid
- [ ] Gemini API: Executive Dashboard AI (M9) auto-briefings
- [ ] AI Copilot (M10) — RAG pipeline + pgvector
- [ ] Frontend: Executive dashboard, AI chat interface

### Phase 5 — Polish, Auth & Deploy (Week 9–10)
- [ ] Auth system (JWT + Google OAuth)
- [ ] Multi-tenant support (different client views)
- [ ] Full Docker Compose production setup
- [ ] GitHub Actions CI/CD
- [ ] Deploy: Railway (backend) + Vercel (frontend)
- [ ] Demo data seeding script
- [ ] PDF export for AI reports
- [ ] Mobile responsive pass

---

## Summary: What We're Building

> A single intelligence platform that monitors **every category** Zomato District operates across — Music, Movies, Sports, Comedy, Theatre, Experiences, Workshops, Dining, and Nightlife — and gives any decision-maker answers to the question: **"What should we bet on next, where, and at what price?"**

### Tech Decisions Locked In:
- ✅ **Python scripts** for: entity scoring v1, city ranking, competitor pattern counting
- ✅ **ML (XGBoost/Prophet/NLP)** for: trend prediction, pricing optimization, sentiment analysis, event success prediction
- ✅ **LLM (Gemini)** for: executive narrative, AI copilot chat
- ✅ **ApexCharts + Nivo** for: primary charts and specialty viz
- ✅ **D3.js** for: custom bespoke charts only (elasticity curves, wave charts)
- ✅ **Mapbox GL** for: geographic heatmaps
- ✅ **Framer Motion** for: UI animations and counter effects
- ✅ **Dark mode glassmorphism** with the color system above

### Open Questions Before Building:
> [!IMPORTANT]
> **Start point**: 
> - Option A: Full backend data pipeline (real data from day 1)  
> - Option B: Beautiful frontend with mock data (impress instantly, wire real data later)
> - Option C: One complete vertical — Artist Intelligence Score, fully working end-to-end

> [!NOTE]
> **API Keys in hand?** Spotify + Gemini + Ticketmaster are the critical three. Everything else has free fallbacks or can be scraped.

> [!NOTE]
> **Project name?** I'll use "LiveIQ" throughout unless you pick something else.
