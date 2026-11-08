"""
Train the fill-rate (+ price) models from REAL events (tickets_sold & total_capacity present). Refuses to train with
fewer than 150 real rows and never uses synthetic data. 5-fold cross-validated MAE / R2 are reported. Artifacts are
versioned under backend/ml_models/district/vN/ (+ metadata.json: rows, date, metrics, data hash). The running
pricing engine only switches to a model when you pass --promote (writes ml_models/promoted.json); the API then reports
model_provenance = 'district-trained vN' instead of 'synthetic-baseline'.

Usage: python scripts/retrain_fill_model.py [--promote] [--dry-run] [--min-rows 150]
"""
import argparse, bisect, math, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, ".")
from sqlalchemy import create_engine, text
from app.core.config import settings
from app.services.ml import district_training as dt
from app.services.ml import pricing_engine as pe


def load_rows(eng):
    q = """select e.id, e.source, e.category, e.city, e.event_date, e.total_capacity, e.tickets_sold, e.fill_rate, e.gross_revenue,
                  e.ticket_price_min, e.predicthq_rank, e.entity_id, en.is_international,
                  (select composite_score from entity_metrics m where m.entity_id = e.entity_id and m.composite_score is not null order by time desc limit 1) as comp,
                  c.music_market_size
           from events e left join entities en on en.id = e.entity_id left join cities c on c.name = e.city
           where e.tickets_sold is not null and e.total_capacity is not null"""
    with eng.connect() as c:
        rows = [dict(r) for r in c.execute(text(q)).mappings()]
        allev = [(r[0], r[1]) for r in c.execute(text("select city, event_date from events where city is not null"))]
    return rows, allev


def build(rows, allev):
    by_city = defaultdict(list)
    for city, d in allev:
        by_city[city].append(d)
    for v in by_city.values():
        v.sort()
    X, yf, yp, imputed = [], [], [], defaultdict(int)
    for r in rows:
        cat = r["category"] if r["category"] in pe._CATEGORY_LIST else "music"
        cat_enc = float(pe._CATEGORY_LIST_SORTED.index(cat)) if hasattr(pe, "_CATEGORY_LIST_SORTED") else float(sorted(pe._CATEGORY_LIST).index(cat))
        comp = r["comp"]; mus = r["music_market_size"]
        if comp is None: imputed["composite_score"] += 1
        if mus is None: imputed["city_music_score"] += 1
        d = r["event_date"]; dates = by_city.get(r["city"], [])
        i = bisect.bisect_left(dates, d)
        prev = dates[i - 1] if i > 0 else None
        days_since = (d - prev).days if prev is not None else pe.DEFAULT_DAYS_SINCE_LAST_EVENT
        if prev is None: imputed["days_since_last_event"] += 1
        comp_n = sum(1 for x in dates if abs((x - d).days) <= 3) - 1
        if r["predicthq_rank"] is None: imputed["phq_avg_rank"] += 1
        imputed["lead_days"] += 1  # booking lead time is not in the export: constant 60
        X.append([float(comp if comp is not None else 50.0), float(mus if mus is not None else 70.0),
                  math.log1p(max(1, int(r["total_capacity"]) - 1000)), cat_enc, float(bool(r["is_international"])), 60.0,
                  float(days_since), float(max(0, comp_n)), float(r["predicthq_rank"] if r["predicthq_rank"] is not None else pe.DEFAULT_PHQ_AVG_RANK)])
        yf.append(min(1.0, r["tickets_sold"] / r["total_capacity"]))
        gr = r["gross_revenue"]
        yp.append(float(gr) / r["tickets_sold"] if gr and r["tickets_sold"] else (float(r["ticket_price_min"]) if r["ticket_price_min"] else None))
    return X, yf, yp, dict(imputed)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--promote", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="only report row counts / eligibility")
    ap.add_argument("--min-rows", type=int, default=dt.MIN_REAL_ROWS)
    a = ap.parse_args(argv)
    eng = create_engine(settings.POSTGRES_SYNC_URL, pool_pre_ping=True)
    rows, allev = load_rows(eng)
    rows = [r for r in rows if dt.eligible(r)]
    print(f"real events with tickets_sold & capacity: {len(rows)} (minimum {a.min_rows})")
    try:
        dt.require_enough(rows, a.min_rows)
    except dt.InsufficientData as e:
        print(str(e)); sys.exit(2)
    if a.dry_run:
        return
    X, yf, yp, imputed = build(rows, allev)
    root = pe.ML_DIR / "district"
    meta = dt.train_and_save(X, yf, yp, root, notes={"imputed_feature_counts": imputed})
    print("trained", meta["version"], "rows", meta["training_rows"], "metrics", meta["metrics"], "hash", meta["data_hash"])
    if a.promote:
        dt.promote(root, meta["version"], pe.ML_DIR)
        print("promoted", meta["version"], "-> ml_models/promoted.json (restart the API to load it)")
    else:
        print("not promoted (use --promote)")


if __name__ == "__main__":
    main()
