# LiveIQ Data Dictionary

Principles: **no fabrication** (a value is either fetched from a named source or NULL), **provenance on every
enriched row** (`data_provenance` JSONB + QIDs in `entities.external_ids`), **idempotent + dry-run scripts**,
**additive migrations only**. Run everything from `backend/` with `.venv/bin/python scripts/<x>.py`.
Logging: ingestion clients and `main.py` run every log line through `app/core/log_redaction.py` (query params `key=`/`apiKey=`/`token=` are replaced by REDACTED, including httpx error messages).
Public APIs are polled politely (descriptive User-Agent, <= 3 req/s, on-disk cache in the scratchpad `cache/` dir;
set `LIVEIQ_CACHE` to change it). Health check: `python scripts/data_quality_report.py` (exit 1 on critical failure) and
`pytest tests/integration/test_data_quality.py`.

## Pipelines (run order for a fresh rebuild)

| # | Step | Command | Source | Cadence |
|---|------|---------|--------|---------|
| 0 | Migrations | `alembic upgrade head` | – | on deploy |
| 1 | Seed cities / venues / entities (legacy, editorial) | `scripts/seed_cities.py`, `seed_venues.py`, `seed_entities.py`, `seed_india_expansion.py` | hand-curated (see "Known gaps") | once |
| 2 | Cities from Wikidata (+ audit of seeded 12) | `scripts/expand_cities_wikidata.py [--dry-run] [--fix-existing]` | Wikidata (Census of India 2011 statements) | yearly |
| 3 | Venues from Wikidata (+ OSM) | `scripts/seed_venues_wikidata_osm.py [--dry-run] [--osm]` | Wikidata P1083/P625; OSM Overpass (ODbL) | quarterly |
| 4 | Entity expansion | `scripts/expand_entities_wikidata.py [--dry-run] [--min-sl N ...]` | Wikidata SPARQL | quarterly |
| 5 | Entity enrichment | `scripts/enrich_entities_wikidata.py [--dry-run] [--new-only]` | Wikidata + Wikipedia REST (CC BY-SA text) + Commons (image URLs) | quarterly / after step 4 |
| 6 | Real metrics for entities lacking any | `scripts/collect_metrics_missing.py [--retry-incomplete]` | Last.fm, YouTube, Google Trends, NewsAPI | after step 4; the Celery `entity_metrics` worker refreshes every ~6 h |
| 7 | Events | Celery `event_sync` (Ticketmaster), `predicthq_sync`, District scraper; `scripts/backfill_event_locations.py` | Ticketmaster, PredictHQ (needs `PREDICTHQ_API_KEY`), district.in | hourly-daily |
| 8 | Restaurants | Celery `restaurant_sync` | OSM Overpass + Foursquare (needs key) | weekly |
| 6b | Free attention signals (all entities with a QID) | `scripts/collect_free_signals.py [--steps wiki,social,youtube] [--dry-run]` | Wikimedia REST pageviews (en+hi), Wikidata dated follower statements, YouTube Data API channel stats | monthly (pageviews are trailing-30-day) |
| 7b | District events for tracked + new cities | `scripts/sync_district_events.py [--cities ...]` (Playwright: run `python -m playwright install chromium` once) | district.in public listings | daily |
| 8b | Venues via Overpass (alternate endpoints, per-city, 3 small query groups) | `scripts/seed_venues_wikidata_osm.py --osm` / `--osm-cached-only` | OSM (ODbL) | quarterly |
| 9 | Quality gate | `scripts/data_quality_report.py` | – | after every step / CI |

## Provenance conventions
* `entities.external_ids` (JSONB): `wikidata_qid`, `wikipedia_title`, `spotify_id` (Wikidata P1902), `youtube_channel_id` (P2397; read by the metrics collector), `instagram_handle` (P2003), `musicbrainz_id` (P434), `imdb_id`, `twitter_handle`, `website`, plus legacy `lastfm_mbid`, `lastfm_name`, `tmdb_name`.
* `entities.data_provenance`: `{source, wikidata_qid, retrieved (date), match_confidence, method, fields: [columns filled], wikipedia_license}`. Rows created by step 4 have `source = "wikidata-sparql"` + `sitelinks`; after step 5 they are overwritten with `"wikidata+wikipedia"`.
* Match confidence: 0.99 = Wikidata MusicBrainz ID equals our Last.fm MBID; 0.95 = single name+type(+India) match; 0.85 = best of several, >= 3x sitelinks of runner-up. Ambiguous / no match = left untouched (see `cache/entity_enrichment_report.json`).
* `cities.data_provenance`: `{source, wikidata_qid, retrieved, population_year, population_basis, notes}`; seeded 12 carry `curated_unverified_fields` + `population_correction {old,new,source,date}` when corrected.
* `venues.data_provenance`: `{source: wikidata|openstreetmap, source_id (QID or osm node/way id), retrieved, capacity_source, license}`.

## Tables

### cities
| Column | Source | Notes / known gaps |
|---|---|---|
| name, state, country, tier | seed / Wikidata P131 chain | New-city tier rule: pop >= 2M -> 2, >= 0.5M -> 3, else 4, NULL if no population. Seeded tiers are editorial (e.g. Chennai/Kolkata tier 2). |
| population | Census of India 2011 via Wikidata P1082 | Year in `data_provenance.population_year`. Seeded rows follow the municipal-corporation definition; Wikidata differs for Delhi (NCT 16.8M vs MCD 11.0M), Indore (UA vs MC), and carries *provisional* 2011 counts for Hyderabad/Pune (DB holds final). Only Kolkata was corrected (4,486,679 -> 4,496,694). |
| metro_population, avg_monthly_income, youth_population_pct | seed (12) / derived | Seeded values unverified. Other cities: see "City demographics and scores" (youth = Census 2011 C-13 district-urban; income = state per-capita GSDP proxy). metro_population still NULL. |
| lat, lng | Wikidata P625 | Audited: seeded 12 are within 6 km of Wikidata. |
| google_trends_geo_code | state ISO 3166-2 (Wikidata P300) | |
| nightlife/sports/arts/comedy/music scores, top_categories, festival_months, monsoon_months, avg_temperature_jun_sep | seed (editorial) | **No data source**; NULL for new cities. API treats NULL composite as "unscored" (`/cities/gaps` -> `unscored_cities`; `/cities/top` -> `scored:false`). |
| active_venues_count | derived: count of active venues | refreshed by step 3 |
| active_on_district, district_events_count | manual flag / counter | all False for new cities until District coverage is verified |
| mapbox_bbox | – | not populated (0%). |

### venues
Wikidata/OSM venues are attached to the nearest tracked city within 30 km (haversine), deduped against existing rows (same city + normalised name, or < 250 m).
| Column | Source | Notes |
|---|---|---|
| name, venue_type, lat, lng, city, state | Wikidata / OSM | `venue_type` mapped from instance-of / OSM tags |
| total_capacity | Wikidata P1083 / OSM `capacity` tag | NULL when untagged (most rows) |
| address, pincode | OSM `addr:*` | sparse |
| is_indoor, has_parking, is_alcohol_permitted, avg_fill_rate, avg_ticket_price, avg_rating, standing/seated/vip capacity, suitable_categories | seed rows only | **The 33 seeded venues carry hand-entered fill rate / price / rating that have no cited source**; new rows keep these NULL. |
| google_place_id, foursquare_id, bookmyshow_venue_id | – | unpopulated; needs API keys / partnership |

### entities
| Column | Source | Notes |
|---|---|---|
| name, entity_type, category, genre | seed / Wikidata | Category for step-4 rows is coarse: `Music`, `Indian Hip-Hop`, `Indian EDM`, `Stand-Up Comedy`, sport name, `Festival`. |
| description | Wikipedia REST summary (CC BY-SA 4.0; fallback Wikidata description) | |
| image_url | Wikimedia Commons `Special:FilePath/<P18>?width=480` | Only entities with a P18 image |
| home_city / home_state | Wikidata P19/P740/P159 walked up to a city-like item; state via P131 | Seeded values are never overwritten |
| language, country, genres | Wikidata P1412/P103/P407, P27/P495/P17, P136 | |
| is_international | seed / Wikidata | Only True->False corrected, when P27 = India (Diljit, Karan Aujla, Prateek Kuhad, AP Dhillon, Zakir Hussain...). Pakistani/Nepali Bollywood acts (Atif Aslam, Udit Narayan) are kept domestic. |
| booking_price_range_*, typical_venue_capacity_* | – | no data source (92% NULL). Needs agent/promoter data. |
| external_ids | see Provenance | |

### entity_metrics (time series, one row per entity per collection)
**Free signals (added by `collect_free_signals.py`, migration `c3f8b2d1e7a4`)**
* `wikipedia_views_30d` / `wikipedia_views_7d`: sum of Wikimedia *user* pageviews (all-access) over the trailing 30/7 complete UTC days for the entity's en.wikipedia and hi.wikipedia articles (from Wikidata sitelinks). NULL when no article exists.
* `instagram_followers` / `twitter_followers`: newest Wikidata dated follower statement (P8687 with platform qualifier, or P3744 on P2003/P2002) **only if dated within 3 years**; the as-of date is in `signal_provenance`. Not live counts (~25 entities).
* `youtube_subscribers`: refreshed from the YouTube Data API for entities that have `external_ids.youtube_channel_id`.
* `signal_provenance` JSONB: per-signal `{source, retrieved, as_of, articles|channel_id|wikidata_qid}`.
* Existing rows are UPDATED in place (composite_score untouched); entities without any row get a `collection_source='free_signals'` row.
* `composite.py` accepts two supplementary inputs, `spotify_popularity` and `wikipedia_views_30d` (weight 0.10 each, renormalised like the others, excluded from `data_completeness`). Stored composites are NOT changed until the owner runs `python -m app.services.scoring.recompute --apply`.
* **Spotify popularity/followers are blocked**: the configured Spotify app now receives artist objects without `popularity`, `followers` or `genres`, so `spotify_popularity`/`spotify_followers` stay NULL (spotify_id comes from Wikidata only).

Core sources: Last.fm (listeners/plays), YouTube Data API (subs/views), Google Trends (pytrends), NewsAPI (mentions). `data_completeness` = fraction of the 4 sources that answered. Spotify popularity/listeners and Instagram/Twitter/Reddit columns are **not collected** (0%): Spotify API gives followers/popularity only for the configured app scope; Instagram has no free API. Refresh: Celery worker every ~6 h; `collect_metrics_missing.py` for backfills.

### events
| Column | Notes |
|---|---|
| source in (district, predicthq, ticketmaster) | Ticketmaster returns 0 events for country IN at the time of writing. PredictHQ needs `PREDICTHQ_API_KEY` (not configured). |
| city, venue_name_raw (new) | Raw location evidence persisted by the District scraper / Ticketmaster sync; `scripts/backfill_event_locations.py` fills legacy rows only from title / booking-URL evidence. |
| venue_id | Linked only when exactly one venue in the city matches the scraped venue name. Most events remain NULL (source gives no venue). |
| District coverage caveat | District lists only ~12 cities; for other cities it silently shows a neighbouring listing. `sync_district_events.py` keeps such events only if their own text names the city, and `scripts/reconcile_event_cities.py` repairs city/venue links by text evidence (else NULL). |
| fill_rate, tickets_sold, actual_* | not provided by any source (NULL) |

### restaurants (7.2k rows) — OSM (+ Foursquare when keyed). No ratings (never fabricated).
### competitor_listings, entity_predictions — empty (BookMyShow/Insider scraping and the prediction batch are not scheduled).
### users, watchlist, notification_reads, social_posts, trend_signals, exec_briefings, ai_* — application tables, not master data.

## Scheduler (in-process APScheduler; Celery/Redis are not required)
`app/services/scheduler/` is started from `main.py`'s lifespan (`SCHEDULER_ENABLED=false` disables it; it is also off under pytest).
Every run goes through `runner.run_job`: lease lock row in `job_locks` (atomic upsert, works through the Neon pooler; two uvicorn
workers never run the same job), a `job_runs` row (job_name, started_at, finished_at, status, rows_affected, error, trigger, detail),
structured logging, errors captured never raised, and `invalidate_all()` of the response cache after a successful run
(per-process cache: other workers expire by TTL). APScheduler: `max_instances=1, coalesce=True`, start jitter, tz Asia/Kolkata.
| job | schedule (IST) | what |
|---|---|---|
| entity_metrics | daily 02:30 | `collect_entity_metrics_batch`: the 60 entities with the OLDEST `last_enriched_at` (never-collected first) -> Last.fm, YouTube, Google Trends, news; semaphore 3, chunks of 6, exponential back-off on 429 and early stop; one new `entity_metrics` row each (builds forecast history) |
| free_signals | daily 04:00 | `scripts/collect_free_signals.py --steps wiki,youtube` (subprocess) |
| news_backfill | daily 03:30 | keyless news mentions for entities whose newest metrics row has NULL `news_mentions_7d` (30/run) |
| district_events | daily 05:00 | `scripts/sync_district_events.py` (Playwright, supported cities) |
| social_listening | hourly :20 | `_collect_all_social(limit=10)` - the 10 least-recently-listened entities |
| wikidata_enrichment | weekly Sun 03:00 | `scripts/enrich_entities_wikidata.py --new-only` |
Read: `GET /admin/jobs`, `/health` (`jobs`, `scheduler`). Trigger: `POST /admin/jobs/{name}/run` (executive). Env knobs: `JOB_ENTITY_METRICS_BATCH`, `JOB_SOCIAL_BATCH`, `JOB_NEWS_BATCH`. The Celery wrappers still work and call the same functions.

## Keyless news signal (`app/services/ingestion/news_free_client.py`)
`entity_metrics.news_mentions_7d` falls back from NewsAPI (429 / unconfigured / empty) to GDELT 2.0 DOC (`mode=ArtList`, 7d, `sourcecountry:IN` for domestic entities, <= 1 req/5.5 s, 15-min cool-down after any failure) and then Google News RSS (`hl=en-IN&gl=IN`, `when:7d`). Query = exact quoted name AND context words by entity_type/category (e.g. `"Jawan" (film OR movie OR Bollywood ...)`) to avoid homonyms. Value = distinct (title-normalised) articles in the window; GDELT caps at 250, RSS ~100 (`capped` recorded). NULL when no source answered, 0 only for a genuine empty result. Provenance per row: `entity_metrics.signal_provenance.news_mentions_7d = {source, query, retrieved, window_days, capped}`. 6 h on-disk cache (`backend/.cache/news_free`, `LIVEIQ_NEWS_CACHE`). Note: these counts are NOT comparable with NewsAPI `totalResults` (which counts any text match of the bare name).

## City demographics and scores (`scripts/derive_city_scores.py`, DRY-RUN by default, `--apply`)
Never overwrites the 12 hand-set (editorial) cities; their derived values are kept only in `data_provenance.scores_derived_for_comparison`.
API (`/cities*`): `scores_basis` = `editorial` | `derived` | null, `youth_basis`, `income_basis`.
* `youth_population_pct` = Census of India 2011 table C-13 (single-year age returns, district level, **urban** column): sum(ages 18..35) / all ages, for the district(s) containing the city (e.g. Prayagraj = Allahabad, Goa = North+South Goa). `data_provenance.youth = {source:'census2011_c13_district_urban', districts, ages:'18-35'}`. This is district-urban, not municipal-limits.
* `avg_monthly_income` = **state-level proxy**: state per-capita GSDP 2024-25 / 12 (INR per person per month; Wikipedia list citing PRS India state budget analysis). `data_provenance.income = {source:'state_proxy', basis:'per_capita_gsdp_2024_25/12', state}`. It is per capita product, NOT household income; do not compare with the editorial figures of the 12 seeded cities.
* nightlife / music / comedy / sports / arts scores (0-100): `score = mean_c PR_c`, `PR_c = (#cities with a strictly smaller count) / (N-1) * 100` across all 53 cities (ties share the lowest rank; zero counts stay 0). Components: nightlife = OSM bar|pub|nightclub in a +-10 km bbox around the centre (Overpass, ODbL); music = OSM nightclub|music_venue|concert_hall + live_music=yes in the box, DB music events by city, DB artist entities by home_city; comedy = DB comedy events, comedian entities by home_city, venues with 'comedy' in suitable_categories (sparse: most cities 0 = no recorded activity, not "bad"); sports = OSM stadium|sports_hall, DB sports events, sports_team entities by home_city; arts = OSM theatre|arts_centre|gallery|museum + DB theatre/art_gallery venues. Components and counts are in `data_provenance.scores_derived`; `data_provenance.scores_basis = 'derived'`. UI should label these "derived".

## District sales import + model retraining
`scripts/import_district_sales.py <csv> [--apply]` (default dry-run). Template: `backend/data_templates/district_sales_template.csv` (its two `EXAMPLE—` rows are always rejected).
Columns (header required): `event_title, event_date (YYYY-MM-DD), city (tracked city), venue_name, artist_name, category (music|comedy|sports|theatre|movie|experience|workshop|dining|nightlife), capacity (int >0), tickets_sold (int >=0, tickets_sold/capacity <= 1.05), gross_revenue_inr (>=0), ticket_price_min, ticket_price_max (min<=max; gross/tickets_sold must lie in 0.3*min..1.5*max)`, optional `source_event_id` (stable key; else a hash of title|date|city|venue).
Matching (rapidfuzz): artist -> active entities (name+aliases), venue -> venues of the same city. Auto-link only when score >= 92 and ahead of the runner-up by >= 6 (or a unique exact name); everything else is written to `<csv>.review.csv` and the FK stays NULL. Upsert: `events.external_id = source_event_id`, `source='district_sales'` (an existing scraped `district` event with that external_id is updated instead); sets total_capacity, tickets_sold, fill_rate (capped 1.0), gross_revenue, prices, city, venue_id, entity_id; status completed/upcoming by date. Idempotent; never deletes.
`scripts/retrain_fill_model.py [--promote] [--dry-run] [--min-rows 150]`: trains from events with tickets_sold & total_capacity only; **exit 2 and refuses below 150 real rows**; features = the engine's 9 (composite, city music score, log capacity, category, is_international, constant lead_days=60 because the export has no booking lead time, days since last event in city, competitor events within +-3 days, PHQ rank; imputation counts recorded in metadata). 5-fold CV MAE/R2 for fill rate (and price = realised avg price when >=150 priced rows, else the baseline price model is reused and recorded). Artifacts: `ml_models/district/vN/{pricing_gbr,fillrate_gbr,pricing_encoders}.joblib + metadata.json` (rows, date, metrics, data hash). `--promote` writes `ml_models/promoted.json`; after an API restart the engine loads it and responses show `model_provenance = 'district-trained vN'` (otherwise `synthetic-baseline`, or `rule-based` without sklearn).

## Admin data-gap / manual edit
See `docs/ADMIN_API.md`. Manual values carry `data_provenance.manual_fields[field] = {source:'manual', by:<email>, at}` and an audit trail.

## Known gaps and recommended sources
* City scores/income/youth share: RBI/NSSO household data, Census 2011 age tables (C-13), TRAI/ookla for digital, District/BMS internal sales by city.
* Venue capacity for most venues: venue managers, BookMyShow/District inventory feeds, Google Places (key needed), OSM contributions.
* Event supply/competitors: BookMyShow, Insider, Paytm feeds (scrapers exist but unscheduled), PredictHQ key, District internal API.
* Artist booking prices: promoter/agent partnerships; Spotify for Artists; Songkick/Bandsintown APIs.
* Instagram/Twitter metrics: Wikidata P8687 (dated follower counts) is available for some entities but is not time-aligned; Meta Graph API for owned data.
