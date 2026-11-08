"""
Phase E — LiveIQ data quality report.

Prints null rates per table/column, duplicates, referential integrity, staleness, coverage and
plausibility checks. Exit code 1 if any CRITICAL check fails (so CI / cron can alert).

Usage: python scripts/data_quality_report.py [--json]
Library use: `from data_quality_report import run_checks` returns list of dicts
{name, severity ('critical'|'warn'|'info'), ok, detail}.
"""
import json
import sys

sys.path.insert(0, ".")
from sqlalchemy import create_engine, text
from app.core.config import settings

# India incl. Andaman/Nicobar & Lakshadweep envelope
LAT_MIN, LAT_MAX, LNG_MIN, LNG_MAX = 6.0, 37.5, 68.0, 97.5
TABLES = ["entities", "entity_metrics", "cities", "venues", "events", "restaurants", "competitor_listings", "entity_predictions"]


def q1(c, sql):
    return c.execute(text(sql)).scalar()


def run_checks(c):
    out = []

    def add(name, sev, ok, detail=""):
        out.append({"name": name, "severity": sev, "ok": bool(ok), "detail": str(detail)})

    def cnt(name, sev, sql, desc=""):
        n = q1(c, sql)
        add(name, sev, n == 0, f"{n} offending rows {desc}")

    # ---- referential integrity
    cnt("events.venue_id -> venues", "critical", "select count(*) from events e left join venues v on v.id=e.venue_id where e.venue_id is not null and v.id is null")
    cnt("events.entity_id -> entities", "critical", "select count(*) from events e left join entities x on x.id=e.entity_id where e.entity_id is not null and x.id is null")
    cnt("entity_metrics.entity_id -> entities", "critical", "select count(*) from entity_metrics m left join entities x on x.id=m.entity_id where x.id is null")
    cnt("venues.city -> cities.name", "warn", "select count(*) from venues v left join cities c on c.name=v.city where c.id is null", "(venue city not a tracked city)")
    # ---- duplicates
    cnt("duplicate entity names (normalised)", "critical",
        "select count(*) from (select lower(regexp_replace(name,'[^a-zA-Z0-9]','','g')) n, entity_type from entities where status='active' group by 1,2 having count(*)>1) t")
    cnt("duplicate wikidata_qid across entities", "critical",
        "select count(*) from (select external_ids->>'wikidata_qid' q from entities where external_ids ? 'wikidata_qid' group by 1 having count(*)>1) t")
    cnt("duplicate city names", "critical", "select count(*) from (select lower(name) from cities group by 1 having count(*)>1) t")
    cnt("duplicate venues (same city + name)", "warn",
        "select count(*) from (select city, lower(name) from venues group by 1,2 having count(*)>1) t")
    cnt("duplicate venue source ids", "critical",
        "select count(*) from (select data_provenance->>'source_id' s from venues where data_provenance ? 'source_id' group by 1 having count(*)>1) t")
    # ---- impossible values
    cnt("negative ticket prices", "critical", "select count(*) from events where ticket_price_min<0 or ticket_price_max<0")
    cnt("ticket_price_min > ticket_price_max", "critical", "select count(*) from events where ticket_price_min>ticket_price_max")
    cnt("fill_rate outside [0,1]", "critical", "select count(*) from events where fill_rate<0 or fill_rate>1")
    cnt("venues.avg_fill_rate outside [0,1]", "critical", "select count(*) from venues where avg_fill_rate<0 or avg_fill_rate>1")
    cnt("negative venue capacity", "critical", "select count(*) from venues where total_capacity<0")
    cnt("event_end before event_date", "warn", "select count(*) from events where event_end_date<event_date")
    cnt("composite_score outside [0,100]", "critical", "select count(*) from entity_metrics where composite_score<0 or composite_score>100")
    cnt("data_completeness outside [0,1]", "critical", "select count(*) from entity_metrics where data_completeness<0 or data_completeness>1")
    cnt("booking price min > max", "critical", "select count(*) from entities where booking_price_range_min>booking_price_range_max")
    # ---- plausibility
    cnt("venue capacity > 150,000", "warn", "select count(*) from venues where total_capacity>150000", "(largest stadium in India ~132k)")
    cnt("venue capacity 1..49 (suspicious)", "warn", "select count(*) from venues where total_capacity between 1 and 49")
    cnt("city population out of range (<10k or >30M)", "critical", "select count(*) from cities where population<10000 or population>30000000")
    cnt("metro_population < population", "warn", "select count(*) from cities where metro_population<population")
    cnt("youth_population_pct outside [0,100]", "critical", "select count(*) from cities where youth_population_pct<0 or youth_population_pct>100")
    cnt("city lat/lng outside India", "critical", f"select count(*) from cities where country='India' and lat is not null and (lat not between {LAT_MIN} and {LAT_MAX} or lng not between {LNG_MIN} and {LNG_MAX})")
    cnt("venue lat/lng outside India", "critical", f"select count(*) from venues where country='India' and lat is not null and (lat not between {LAT_MIN} and {LAT_MAX} or lng not between {LNG_MIN} and {LNG_MAX})")
    cnt("venue > 60 km from its city centre", "warn",
        "select count(*) from venues v join cities c on c.name=v.city where v.lat is not null and c.lat is not null and "
        "6371*2*asin(sqrt(power(sin(radians(v.lat-c.lat)/2),2)+cos(radians(c.lat))*cos(radians(v.lat))*power(sin(radians(v.lng-c.lng)/2),2)))>60")
    cnt("domestic entities with is_international and primary_market India", "warn",
        "select count(*) from entities e where status='active' and is_international and primary_market='India' and external_ids ? 'wikidata_qid' and country='India'", "(Indian-citizen flagged international)")
    # ---- provenance / enrichment coverage (info, thresholds as warn)
    pct = lambda sql: q1(c, sql) or 0
    ent_total = q1(c, "select count(*) from entities where status='active'") or 1
    qid = q1(c, "select count(*) from entities where status='active' and external_ids ? 'wikidata_qid'")
    add("entities with wikidata_qid", "info", True, f"{qid}/{ent_total} = {100*qid/ent_total:.0f}%")
    vprov = q1(c, "select count(*) from venues where data_provenance is not null")
    add("venues with provenance", "info", True, f"{vprov}/{q1(c,'select count(*) from venues')}")
    # ---- staleness
    age = q1(c, "select extract(epoch from now()-max(time))/3600 from entity_metrics")
    add("entity_metrics newest row age (h)", "warn", age is not None and age < 72, f"{age:.1f}h" if age is not None else "no rows")
    stale = q1(c, "select count(*) from entities e where status='active' and not exists (select 1 from entity_metrics m where m.entity_id=e.id and m.time>now()-interval '14 days')")
    add("active entities w/o metrics in 14d", "info", True, f"{stale}/{ent_total}")
    # ---- events
    ev = q1(c, "select count(*) from events") or 1
    nov = q1(c, "select count(*) from events where venue_id is null")
    add("events without venue", "info", True, f"{nov}/{ev}")
    return out


def null_rates(c):
    rows = []
    for t in TABLES:
        cols = [r[0] for r in c.execute(text("select column_name from information_schema.columns where table_schema='public' and table_name=:t order by ordinal_position"), {"t": t})]
        if not cols:
            continue
        sel = ", ".join(f'count("{col}")' for col in cols)
        n = q1(c, f"select count(*) from {t}")
        vals = c.execute(text(f"select {sel} from {t}")).fetchone()
        rows.append((t, n, [(col, (100.0 * (n - v) / n) if n else None) for col, v in zip(cols, vals)]))
    return rows


def coverage(c):
    res = {}
    res["venues_by_city"] = c.execute(text("select city,count(*),count(total_capacity) from venues group by 1 order by 2 desc limit 60")).all()
    res["entities_by_type"] = c.execute(text("select entity_type,count(*),count(*) filter (where external_ids ? 'wikidata_qid') from entities where status='active' group by 1 order by 2 desc")).all()
    res["events_by_source"] = c.execute(text("select source,count(*),count(venue_id) from events group by 1")).all()
    return res


def main():
    eng = create_engine(settings.POSTGRES_SYNC_URL)
    with eng.connect() as c:
        checks = run_checks(c)
        nr = null_rates(c)
        cov = coverage(c)
    if "--json" in sys.argv:
        print(json.dumps({"checks": checks}, indent=1)); sys.exit(1 if any(not k["ok"] and k["severity"] == "critical" for k in checks) else 0)
    print("=== ROW COUNTS & NULL RATES (columns >50% null shown) ===")
    for t, n, cols in nr:
        bad = [(c_, r) for c_, r in cols if r is not None and r > 50]
        print(f"{t}: {n} rows; {len(cols)} cols; >50% null: " + (", ".join(f"{c_} {r:.0f}%" for c_, r in bad) or "none"))
    print("\n=== COVERAGE ===")
    for k, v in cov.items():
        print(k + ":", [tuple(x) for x in v][:40])
    print("\n=== CHECKS ===")
    crit = 0
    for k in checks:
        flag = "OK  " if k["ok"] else ("FAIL" if k["severity"] == "critical" else "WARN")
        if not k["ok"] and k["severity"] == "critical":
            crit += 1
        print(f"[{flag}] ({k['severity']}) {k['name']}: {k['detail']}")
    print(f"\ncritical failures: {crit}")
    sys.exit(1 if crit else 0)


if __name__ == "__main__":
    main()
