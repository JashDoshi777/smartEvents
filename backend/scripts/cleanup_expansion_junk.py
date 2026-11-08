"""
Mark non-entity rows produced by the league-membership SPARQL (match finals, seasons, individual players,
duplicate/defunct franchises) as status='inactive' with a logged reason in data_provenance.cleanup.
Never deletes. Idempotent. Criteria are Wikidata instance-of labels (cached) + a short explicit list.

Usage: python scripts/cleanup_expansion_junk.py [--dry-run]
"""
import json
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "scripts")
import _wd
from sqlalchemy import create_engine, text
from app.core.config import settings

BAD_P31 = ("final", "season", "edition", "human", "tournament")
EXPLICIT = {
    "Deccan Chargers": "defunct IPL franchise (Wikidata: former cricket franchise)",
    "Gujarat Lions": "defunct IPL franchise (2016-17)",
    "Kochi Tuskers Kerala": "defunct IPL franchise (2011)",
    "Pune Warriors India": "defunct IPL franchise (2011-13)",
    "Rising Pune Supergiant": "defunct IPL franchise (2016-17)",
    "Royal Challengers Bangalore": "duplicate: women's team item; men's franchise is 'Royal Challengers Bengaluru'",
    "Chennayin FC": "duplicate/typo of 'Chennaiyin FC'",
}


def main():
    dry = "--dry-run" in sys.argv
    eng = create_engine(settings.POSTGRES_SYNC_URL)
    with eng.connect() as c:
        rows = c.execute(text("select id,name,entity_type,external_ids->>'wikidata_qid' q,data_provenance from entities "
                              "where status='active' and external_ids ? 'wikidata_qid' and entity_type in ('sports_team','attraction')")).all()
    ents = _wd.get_entities([r[3] for r in rows])
    lab = _wd.labels(sorted({x for v in ents.values() for x in v["claims"].get("P31", [])}))
    todo = []
    for id_, name, et, q, prov in rows:
        p31 = " ".join((lab.get(x) or "").lower() for x in (ents.get(q) or {"claims": {}})["claims"].get("P31", []))
        reason = None
        if name in EXPLICIT:
            reason = EXPLICIT[name]
        elif any(b in p31 for b in BAD_P31):
            reason = f"not a team/festival entity (Wikidata instance-of: {p31})"
        if reason and name != "PV Sindhu":
            todo.append((id_, name, reason, prov or {}))
    print("to deactivate:", len(todo))
    for t in todo:
        print(" ", t[1], "-", t[2][:80])
    if dry:
        return
    with eng.begin() as c:
        for id_, name, reason, prov in todo:
            prov = dict(prov); prov["cleanup"] = {"status": "inactive", "reason": reason, "date": _wd.TODAY}
            c.execute(text("update entities set status='inactive', data_provenance=CAST(:p AS jsonb), updated_at=now() where id=:i"),
                      {"p": json.dumps(prov), "i": id_})
    print("done")


if __name__ == "__main__":
    main()
