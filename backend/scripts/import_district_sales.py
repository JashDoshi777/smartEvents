"""
Import District ticket-sales actuals (CSV) into `events`: tickets_sold, total_capacity, fill_rate, gross_revenue,
ticket prices, city, venue_id, entity_id. Template: backend/data_templates/district_sales_template.csv
(columns documented in DATA_DICTIONARY.md). DRY-RUN by default; pass --apply to write.

  * every row is strictly validated (types, ranges, dates, fill <= 1.05, price/revenue consistency); invalid rows are
    rejected and listed with reasons - nothing is "fixed" silently. EXAMPLE rows are always refused.
  * artist -> entities and venue -> venues (same city) fuzzy matching; only high-confidence matches are linked.
    Ambiguous / low-confidence candidates go to the review-queue CSV (<csv>.review.csv) and the FK stays NULL.
  * idempotent upsert keyed on external_id = source_event_id (source 'district_sales'; if the id equals the
    external_id of an already-scraped 'district' event that row is updated instead). Re-running changes nothing.
  * never deletes rows.

Usage: python scripts/import_district_sales.py sales.csv [--apply] [--review-out PATH] [--report-out PATH]
"""
import argparse, csv, json, sys, uuid
from datetime import datetime, timezone

sys.path.insert(0, ".")
from sqlalchemy import create_engine, text
from app.core.config import settings
from app.services.ingestion import district_sales_import as imp


def load_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        missing = [c for c in imp.REQUIRED if c not in (rd.fieldnames or [])]
        if missing:
            raise SystemExit(f"CSV is missing required columns: {missing}")
        return list(rd)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--apply", action="store_true", help="write to the DB (default: dry-run)")
    ap.add_argument("--review-out")
    ap.add_argument("--report-out")
    a = ap.parse_args(argv)
    rows = load_csv(a.csv)
    eng = create_engine(settings.POSTGRES_SYNC_URL, pool_pre_ping=True)
    with eng.connect() as c:
        cities = [r[0] for r in c.execute(text("select name from cities"))]
        ents = [(str(r[0]), [r[1]] + list(r[2] or [])) for r in c.execute(text("select id, name, name_aliases from entities where status='active'"))]
        venues = {}
        for r in c.execute(text("select id, name, city from venues where is_active is not false")):
            venues.setdefault(imp.norm(r[2]), []).append((str(r[0]), [r[1]]))
        existing = {}
        for r in c.execute(text("select id, source, external_id from events where source in ('district_sales','district') and external_id is not null")):
            existing.setdefault(r[2], []).append((r[0], r[1]))
    valid, rejected, review = [], [], []
    seen_ids = set()
    for i, raw in enumerate(rows, start=2):  # line 1 = header
        clean, errs = imp.validate_row(raw, cities)
        if clean is None:
            rejected.append({"line": i, "title": raw.get("event_title"), "errors": "; ".join(errs)})
            continue
        if clean["source_event_id"] in seen_ids:
            rejected.append({"line": i, "title": clean["event_title"], "errors": "duplicate source_event_id in file"})
            continue
        seen_ids.add(clean["source_event_id"])
        am = imp.fuzzy_match(clean["artist_name"], ents) if clean["artist_name"] else imp.Match("none")
        vm = imp.fuzzy_match(clean["venue_name"], venues.get(imp.norm(clean["city"]), [])) if clean["venue_name"] else imp.Match("none")
        clean["entity_id"] = am.id if am.status == "linked" else None
        clean["venue_id"] = vm.id if vm.status == "linked" else None
        for kind, q, m in (("artist", clean["artist_name"], am), ("venue", clean["venue_name"], vm)):
            if m.status != "linked" and q:
                review.append({"line": i, "kind": kind, "query": q, "city": clean["city"], "status": m.status, "best_score": m.score,
                               "candidates": " | ".join(f"{n} ({s}) [{cid}]" for cid, n, s in m.candidates)})
        clean["_am"], clean["_vm"] = am.status, vm.status
        valid.append(clean)

    inserts = updates = 0
    now = datetime.now(timezone.utc)
    if a.apply and valid:
        with eng.begin() as c:
            for v in valid:
                hit = existing.get(v["source_event_id"])
                status = "completed" if v["event_date"].date() < now.date() else "upcoming"
                params = dict(t=v["event_title"], d=v["event_date"].replace(tzinfo=timezone.utc), cat=v["category"], city=v["city"],
                              vn=v["venue_name"] or None, cap=v["capacity"], sold=v["tickets_sold"], fr=v["fill_rate"], gr=v["gross_revenue"],
                              pmin=v["ticket_price_min"], pmax=v["ticket_price_max"], eid=v["entity_id"], vid=v["venue_id"], st=status, ext=v["source_event_id"])
                if hit:
                    c.execute(text("""update events set total_capacity=:cap, tickets_sold=:sold, fill_rate=:fr, gross_revenue=:gr,
                        ticket_price_min=:pmin, ticket_price_max=:pmax, city=coalesce(city,:city), venue_name_raw=coalesce(venue_name_raw,:vn),
                        venue_id=coalesce(venue_id,cast(:vid as uuid)), entity_id=coalesce(entity_id,cast(:eid as uuid)), updated_at=now()
                        where id=:id"""), {**params, "id": hit[0][0]})
                    updates += 1
                else:
                    c.execute(text("""insert into events (id, external_id, source, title, category, event_date, status, city, venue_name_raw,
                        total_capacity, tickets_sold, fill_rate, gross_revenue, ticket_price_min, ticket_price_max, entity_id, venue_id, created_at, updated_at)
                        values (:id, :ext, 'district_sales', :t, :cat, :d, :st, :city, :vn, :cap, :sold, :fr, :gr, :pmin, :pmax,
                        cast(:eid as uuid), cast(:vid as uuid), now(), now())"""), {**params, "id": uuid.uuid4()})
                    inserts += 1
    summary = {"mode": "apply" if a.apply else "dry-run", "rows_in_file": len(rows), "valid": len(valid), "rejected": len(rejected),
               "artist_linked": sum(1 for v in valid if v["_am"] == "linked"), "venue_linked": sum(1 for v in valid if v["_vm"] == "linked"),
               "review_items": len(review), "would_insert" if not a.apply else "inserted": (sum(1 for v in valid if v["source_event_id"] not in existing) if not a.apply else inserts),
               "would_update" if not a.apply else "updated": (sum(1 for v in valid if v["source_event_id"] in existing) if not a.apply else updates)}
    review_path = a.review_out or a.csv + ".review.csv"
    if review:
        with open(review_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(review[0])); w.writeheader(); w.writerows(review)
        summary["review_csv"] = review_path
    if rejected:
        print("REJECTED ROWS:")
        for r in rejected[:50]:
            print(f"  line {r['line']}: {r['title']!r}: {r['errors']}")
    print(json.dumps(summary, indent=2))
    if a.report_out:
        json.dump({"summary": summary, "rejected": rejected}, open(a.report_out, "w"), indent=1)
    return summary


if __name__ == "__main__":
    main()
