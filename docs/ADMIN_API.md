# Admin API (analyst / executive)

All routes need `Authorization: Bearer <access token>`. Roles: `executive` and `analyst` unless noted. Responses are never cached.

## GET /admin/data-gaps
Query: `kind` (required: `entities|venues|cities`), `type` (entity_type / venue_type), `market` (`all|india|global`, entities only),
`city` (entities: home_city, venues: city, cities: name; case-insensitive), `missing` (repeatable; rows missing ALL listed fields),
`q` (name contains), `page` (1..), `page_size` (1..100, default 50).

Response:
```json
{ "kind": "entities",
  "tracked_fields": ["language","home_city", "..."],
  "editable_fields": ["booking_price_range_max", "..."],
  "scope_total": 525,                       // rows in scope (type/market/city/q filters, before `missing`)
  "summary_missing_counts": {"language": 310, "home_city": 190, "...": 0},   // per tracked field, over scope_total
  "total": 120, "page": 1, "page_size": 50, // total = rows matching incl. `missing` filter
  "items": [{"id": "uuid", "name": "...", "missing": ["language","genre"], "missing_count": 2,
             "entity_type": "artist", "home_city": null}] }   // venues: venue_type, city; cities: state
```
Tracked fields — entities: language, home_city, home_state, country, genre, description, image_url, booking_price_range_min/max,
typical_venue_capacity_min/max. venues: total_capacity, venue_type, address, pincode, state, lat, lng.
cities: population, avg_monthly_income, youth_population_pct, tier, lat, lng, google_trends_geo_code, nightlife_score,
sports_affinity_score, arts_culture_score, comedy_market_size, music_market_size. Unknown `missing` value -> 422.

## PATCH /admin/entities/{id} , /admin/venues/{id} , /admin/cities/{id}
Body: a flat JSON object of `field: value` (only whitelisted fields; fields can be set, never cleared / set to null).
Editable — entities: tracked entity fields + category, is_international. venues: total_capacity, standing/seated/vip_capacity,
venue_type (enum), address, pincode, state, lat (6..38), lng (68..98), is_indoor, has_parking, is_alcohol_permitted.
cities: tracked city fields (scores 0..100, youth 0..100, tier 1..4). Strings are trimmed, length-limited; `image_url` must be http(s).

Success 200:
```json
{ "id": "uuid", "kind": "venues",
  "changed": {"total_capacity": {"old": null, "new": 1200}}, "unchanged": [],
  "provenance": {"total_capacity": {"source": "manual", "by": "analyst@zomato.com", "at": "2026-11-08T12:00:00+00:00"}} }
```
Errors: 401/403 (auth/role), 404 (id), 422 `{"detail": {"error": "fields not editable", "fields": [...], "editable": [...]}}` or
`{"detail": {"error": "invalid values", "fields": {"lat": "must be between 6 and 38"}}}`.

Audit: `data_provenance.manual_fields[field] = {source:'manual', by, at}` (latest) and `data_provenance.manual_audit` (last 50
`{field, old, new, by, at}`). Setting any city score marks the city `scores_basis = 'editorial'`. The response cache is cleared.

## Scheduler
* `GET /admin/jobs` (executive/analyst): `{scheduler:{enabled_in_this_process, env_enabled}, jobs:[{name, description, cron_ist, next_run, last_run}], runs:[{id, job, status, trigger, started_at, finished_at, rows_affected, error, detail}]}`; `?limit=1..200`.
  `status`: `running|success|partial|error`. `/health` also carries `jobs` (last run per job) and `scheduler`.
* `POST /admin/jobs/{name}/run` (executive only) -> 202; runs in the background under the same lease lock (a concurrent scheduled run is skipped). Unknown job -> 404.
  Names: entity_metrics, free_signals, district_events, social_listening, wikidata_enrichment, news_backfill.

## Model provenance
Pricing/modeler responses carry `model_provenance`: `synthetic-baseline`, `rule-based`, or `district-trained vN`
(`/pricing/*` top level, `/events/*` `prediction.model_provenance`, `/recommend/*` top level).
