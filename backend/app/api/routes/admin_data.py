"""Data-gap review + manual correction endpoints (analyst / executive). Shapes documented in docs/ADMIN_API.md.

  GET   /admin/data-gaps?kind=entities|venues|cities[&type=][&market=][&city=][&missing=f1&missing=f2][&q=][&page=][&page_size=]
  PATCH /admin/entities/{id}   PATCH /admin/venues/{id}   PATCH /admin/cities/{id}
Only whitelisted fields can be set; values are validated; each change is recorded in data_provenance
(manual_fields + capped manual_audit) as {source:'manual', by:<email>, at:<ts>} and the response cache is cleared.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, Text, and_, case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.api.deps import require_roles
from app.core.database import get_db
from app.core.response_cache import invalidate_all
from app.models.city import City
from app.models.entity import Entity, EntityType
from app.models.metrics import EntityMetric
from app.models.user import User, UserRole
from app.models.venue import Venue, VenueType
from app.services.market_scope import market_clause

router = APIRouter()
logger = structlog.get_logger()
_ROLES = (UserRole.EXECUTIVE, UserRole.ANALYST)


# ── field specs ───────────────────────────────────────────────────────────────
def S(max_len=255):          return {"type": "str", "max": max_len}
def I(lo, hi):               return {"type": "int", "min": lo, "max": hi}
def F(lo, hi):               return {"type": "float", "min": lo, "max": hi}
def B():                     return {"type": "bool"}
def E(values):               return {"type": "enum", "values": sorted(values)}

ENTITY_FIELDS: Dict[str, dict] = {
    "language": S(50), "home_city": S(100), "home_state": S(100), "country": S(50), "genre": S(100),
    "category": S(100), "description": S(4000), "image_url": {**S(500), "url": True},
    "booking_price_range_min": F(0, 1e9), "booking_price_range_max": F(0, 1e9),
    "typical_venue_capacity_min": I(1, 500000), "typical_venue_capacity_max": I(1, 500000), "is_international": B(),
}
# Identity ids live in entities.external_ids (JSONB), not columns: validated by regex, stored with provenance 'manual'.
IDENTITY_FIELDS: Dict[str, re.Pattern] = {
    "youtube_channel_id": re.compile(r"^UC[0-9A-Za-z_-]{22}$"),
    "musicbrainz_id": re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
    "wikidata_qid": re.compile(r"^Q[1-9][0-9]{0,12}$"),
}


def validate_identity(fields: Dict[str, Any]) -> Dict[str, str]:
    """Clean + validate identity ids (pure). Raises HTTPException(422) like validate_patch."""
    errors, clean = {}, {}
    for k, v in fields.items():
        if not isinstance(v, str) or not v.strip():
            errors[k] = "must be a non-empty string"
            continue
        v = v.strip()
        if k == "musicbrainz_id":
            v = v.lower()
        if not IDENTITY_FIELDS[k].match(v):
            errors[k] = {"youtube_channel_id": "must look like UC + 22 chars (channel id, not a @handle)",
                         "musicbrainz_id": "must be a MusicBrainz artist MBID (uuid)",
                         "wikidata_qid": "must look like Q12345"}[k]
            continue
        clean[k] = v
    if errors:
        raise HTTPException(422, {"error": "invalid values", "fields": errors})
    return clean


def apply_identity_edit(external_ids: Optional[Dict[str, Any]], clean: Dict[str, str], email: str, now: Optional[str] = None):
    """Pure. Returns (new_external_ids, changed{field:{old,new}}); provenance in external_ids.identity_manual."""
    now = now or datetime.now(timezone.utc).isoformat()
    ext = dict(external_ids or {})
    man = dict(ext.get("identity_manual") or {})
    changed = {}
    for k, v in clean.items():
        old = ext.get(k)
        if old == v:
            continue
        ext[k] = v
        man[k] = {"source": "manual", "by": email, "at": now, "previous": old}
        changed[k] = {"old": old, "new": v}
    if changed:
        ext["identity_manual"] = man
    return ext, changed


VENUE_FIELDS: Dict[str, dict] = {
    "total_capacity": I(1, 500000), "standing_capacity": I(0, 500000), "seated_capacity": I(0, 500000), "vip_capacity": I(0, 100000),
    "venue_type": E(v.value for v in VenueType), "address": S(1000), "pincode": S(10), "state": S(100),
    "lat": F(6, 38), "lng": F(68, 98), "is_indoor": B(), "has_parking": B(), "is_alcohol_permitted": B(),
}
CITY_FIELDS: Dict[str, dict] = {
    "population": I(1, 100_000_000), "metro_population": I(1, 100_000_000), "avg_monthly_income": F(0, 10_000_000),
    "youth_population_pct": F(0, 100), "tier": I(1, 4), "lat": F(6, 38), "lng": F(68, 98), "google_trends_geo_code": S(20),
    "nightlife_score": F(0, 100), "sports_affinity_score": F(0, 100), "arts_culture_score": F(0, 100),
    "comedy_market_size": F(0, 100), "music_market_size": F(0, 100),
}
CITY_SCORE_FIELDS = {"nightlife_score", "sports_affinity_score", "arts_culture_score", "comedy_market_size", "music_market_size"}

KINDS = {
    "entities": (Entity, ENTITY_FIELDS, ["language", "home_city", "home_state", "country", "genre", "description", "image_url",
                                         "booking_price_range_min", "booking_price_range_max", "typical_venue_capacity_min", "typical_venue_capacity_max"]),
    "venues": (Venue, VENUE_FIELDS, ["total_capacity", "venue_type", "address", "pincode", "state", "lat", "lng"]),
    "cities": (City, CITY_FIELDS, ["population", "avg_monthly_income", "youth_population_pct", "tier", "lat", "lng",
                                   "google_trends_geo_code", "nightlife_score", "sports_affinity_score", "arts_culture_score",
                                   "comedy_market_size", "music_market_size"]),
}


def _missing(col):
    if isinstance(col.type, (String, Text)):
        return or_(col.is_(None), func.btrim(col) == "")
    return col.is_(None)


def validate_value(field: str, spec: dict, value: Any) -> Any:
    """Return the cleaned value or raise ValueError(message). null clears nothing: use a real value."""
    t = spec["type"]
    if value is None:
        raise ValueError("null is not allowed (fields can only be set, not cleared)")
    if t == "str":
        if not isinstance(value, str):
            raise ValueError("must be a string")
        v = value.strip()
        if not v:
            raise ValueError("must not be empty")
        if len(v) > spec["max"]:
            raise ValueError(f"max length {spec['max']}")
        if spec.get("url") and not v.lower().startswith(("http://", "https://")):
            raise ValueError("must be an http(s) URL")
        return v
    if t == "bool":
        if not isinstance(value, bool):
            raise ValueError("must be true/false")
        return value
    if t == "enum":
        if value not in spec["values"]:
            raise ValueError(f"must be one of {spec['values']}")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("must be a number")
    if t == "int":
        if value != int(value):
            raise ValueError("must be a whole number")
        value = int(value)
    else:
        value = float(value)
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("must be finite")
    if not (spec["min"] <= value <= spec["max"]):
        raise ValueError(f"must be between {spec['min']} and {spec['max']}")
    return value


def validate_patch(fields: Dict[str, Any], allowed: Dict[str, dict]) -> Dict[str, Any]:
    if not isinstance(fields, dict) or not fields:
        raise HTTPException(422, "Body must be a non-empty JSON object of field: value")
    unknown = sorted(set(fields) - set(allowed))
    if unknown:
        raise HTTPException(422, {"error": "fields not editable", "fields": unknown, "editable": sorted(allowed)})
    clean, errors = {}, {}
    for k, v in fields.items():
        try:
            clean[k] = validate_value(k, allowed[k], v)
        except ValueError as exc:
            errors[k] = str(exc)
    if errors:
        raise HTTPException(422, {"error": "invalid values", "fields": errors})
    return clean


def apply_manual_edit(obj, clean: Dict[str, Any], email: str, extra_prov: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Set the fields and record provenance. Returns {field: {old, new}} for fields that actually changed."""
    now = datetime.now(timezone.utc).isoformat()
    prov = dict(obj.data_provenance or {})
    mf, audit, changed = dict(prov.get("manual_fields") or {}), list(prov.get("manual_audit") or []), {}
    for k, v in clean.items():
        old = getattr(obj, k)
        if old == v:
            continue
        setattr(obj, k, v)
        changed[k] = {"old": old, "new": v}
        mf[k] = {"source": "manual", "by": email, "at": now}
        audit.append({"field": k, "old": old, "new": v, "by": email, "at": now})
    if changed:
        prov["manual_fields"] = mf
        prov["manual_audit"] = audit[-50:]
        prov.update(extra_prov or {})
        obj.data_provenance = prov
        flag_modified(obj, "data_provenance")
    return changed


# ── GET /admin/data-gaps ──────────────────────────────────────────────────────
@router.get("/data-gaps", summary="Missing-field review lists (analyst/executive)")
async def data_gaps(
    kind: str = Query(..., pattern="^(entities|venues|cities)$"),
    type: Optional[str] = Query(None, description="entity_type (entities) or venue_type (venues)"),
    market: str = Query("all", pattern="^(all|india|global)$", description="entities only: india|global|all"),
    city: Optional[str] = Query(None, description="entities: home_city; venues: city; cities: name (case-insensitive)"),
    missing: List[str] = Query(default=[], description="repeatable; only rows missing ALL of these fields"),
    q: Optional[str] = Query(None, max_length=100, description="name contains"),
    signal: Optional[str] = Query(None, pattern="^(youtube|lastfm):[a-z_]{3,40}$",
                                  description="entities only: latest signal_validity verdict, e.g. youtube:unresolved, lastfm:wrong_type"),
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(*_ROLES)),
):
    model, _, tracked = KINDS[kind]
    bad = sorted(set(missing) - set(tracked))
    if bad:
        raise HTTPException(422, {"error": "unknown missing field", "fields": bad, "tracked": tracked})
    conds = []
    if kind == "entities":
        if type:
            conds.append(Entity.entity_type == type)
        conds.append(market_clause(market))
        if city:
            conds.append(func.lower(Entity.home_city) == city.lower())
        conds.append(Entity.status == "active")
    elif kind == "venues":
        if type:
            conds.append(Venue.venue_type == type)
        if city:
            conds.append(func.lower(Venue.city) == city.lower())
        conds.append(Venue.is_active.is_not(False))
    else:
        if city:
            conds.append(func.lower(City.name) == city.lower())
    if signal and kind == "entities":
        sig_key, sig_verdict = signal.split(":", 1)
        lat = (select(EntityMetric.entity_id.label("entity_id"), EntityMetric.signal_validity.label("sv"))
               .where(EntityMetric.signal_validity.isnot(None))
               .distinct(EntityMetric.entity_id).order_by(EntityMetric.entity_id, EntityMetric.time.desc()).subquery())
        conds.append(Entity.id.in_(select(lat.c.entity_id).where(lat.c.sv[sig_key].astext == sig_verdict)))
    if q:
        conds.append(model.name.ilike(f"%{q.replace('%', '').replace('_', '')}%"))
    base = and_(*conds) if conds else True
    for f in missing:
        base = and_(base, _missing(getattr(model, f)))

    # per-field missing counts over the filtered set (before the `missing` filter is NOT applied: counts describe the scope)
    scope = and_(*conds) if conds else True
    summary_q = select(func.count(), *[func.coalesce(func.sum(case((_missing(getattr(model, f)), 1), else_=0)), 0) for f in tracked]).where(scope)
    srow = (await db.execute(summary_q)).one()
    total_scope = srow[0]
    summary = {f: int(srow[i + 1]) for i, f in enumerate(tracked)}

    total = (await db.execute(select(func.count()).select_from(model).where(base))).scalar() or 0
    cols = [model.id, model.name] + [getattr(model, f) for f in tracked]
    extra = {"entities": [Entity.entity_type, Entity.home_city], "venues": [Venue.venue_type, Venue.city], "cities": [City.state]}[kind]
    stmt = select(*cols, *extra).where(base).order_by(model.name).limit(page_size).offset((page - 1) * page_size)
    rows = (await db.execute(stmt)).all()
    verdicts = {}
    if kind == "entities" and rows:
        ids = [r[0] for r in rows]
        lat2 = (select(EntityMetric.entity_id, EntityMetric.signal_validity).where(EntityMetric.entity_id.in_(ids), EntityMetric.signal_validity.isnot(None))
                .distinct(EntityMetric.entity_id).order_by(EntityMetric.entity_id, EntityMetric.time.desc()))
        verdicts = {str(e): {"youtube": (sv or {}).get("youtube"), "lastfm": (sv or {}).get("lastfm")} for e, sv in (await db.execute(lat2)).all()}
    items = []
    for r in rows:
        vals = dict(zip(["id", "name"] + tracked, r[: 2 + len(tracked)]))
        miss = [f for f in tracked if vals[f] is None or (isinstance(vals[f], str) and not vals[f].strip())]
        item = {"id": str(vals["id"]), "name": vals["name"], "missing": miss, "missing_count": len(miss)}
        ex = r[2 + len(tracked):]
        if kind == "entities":
            item.update(entity_type=ex[0], home_city=ex[1], signals=verdicts.get(item["id"]))
        elif kind == "venues":
            item.update(venue_type=ex[0], city=ex[1])
        else:
            item.update(state=ex[0])
        items.append(item)
    return {"kind": kind, "tracked_fields": tracked, "editable_fields": sorted(KINDS[kind][1]) + (sorted(IDENTITY_FIELDS) if kind == "entities" else []),
            "scope_total": total_scope, "summary_missing_counts": summary,
            "total": total, "page": page, "page_size": page_size, "items": items}


# ── PATCH ─────────────────────────────────────────────────────────────────────
async def _patch(db: AsyncSession, model, allowed, obj_id: UUID, body: Dict[str, Any], user: User, kind: str):
    clean = validate_patch(body, allowed)
    obj = (await db.execute(select(model).where(model.id == obj_id))).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, f"{kind[:-1]} not found")
    extra = {"scores_basis": "editorial"} if kind == "cities" and CITY_SCORE_FIELDS & set(clean) else None
    changed = apply_manual_edit(obj, clean, user.email, extra)
    if changed:
        await db.commit()
        cleared = invalidate_all()
        logger.info("manual data edit", kind=kind, id=str(obj_id), by=user.email, fields=sorted(changed), cache_cleared=cleared)
    return {"id": str(obj_id), "kind": kind, "changed": changed, "unchanged": sorted(set(clean) - set(changed)),
            "provenance": {k: (obj.data_provenance or {}).get("manual_fields", {}).get(k) for k in clean}}


@router.patch("/entities/{entity_id}", summary="Manually set missing entity fields")
async def patch_entity(entity_id: UUID, body: Dict[str, Any], db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(*_ROLES))):
    ident = {k: v for k, v in (body or {}).items() if k in IDENTITY_FIELDS} if isinstance(body, dict) else {}
    if not ident:
        return await _patch(db, Entity, ENTITY_FIELDS, entity_id, body, user, "entities")
    rest = {k: v for k, v in body.items() if k not in IDENTITY_FIELDS}
    clean_ident = validate_identity(ident)
    clean_rest = validate_patch(rest, ENTITY_FIELDS) if rest else {}
    obj = (await db.execute(select(Entity).where(Entity.id == entity_id))).scalar_one_or_none()
    if obj is None:
        raise HTTPException(404, "entity not found")
    changed = apply_manual_edit(obj, clean_rest, user.email) if clean_rest else {}
    ext, ich = apply_identity_edit(obj.external_ids, clean_ident, user.email)
    if ich:
        obj.external_ids = ext
        flag_modified(obj, "external_ids")
        prov = dict(obj.data_provenance or {})
        mf = dict(prov.get("manual_fields") or {})
        now = datetime.now(timezone.utc).isoformat()
        for k in ich:
            mf[k] = {"source": "manual", "by": user.email, "at": now}
        prov["manual_fields"] = mf
        obj.data_provenance = prov
        flag_modified(obj, "data_provenance")
        changed.update(ich)
        if "youtube_channel_id" in ich:
            # a human vouches for the channel: mark it verified (manual) on the newest metric row. The stored subscriber
            # count may belong to a different channel, so it is cleared (old value kept in signal_provenance) and refreshed
            # by the next collection, which uses youtube_detail.channel_id.
            await db.execute(text("""
                update entity_metrics m set youtube_subscribers = null,
                  signal_validity = coalesce(m.signal_validity,'{}'::jsonb) || jsonb_build_object('youtube','verified_manual',
                      'youtube_detail', jsonb_build_object('verdict','verified_manual','channel_id', cast(:cid as text),'id_source','manual:'||cast(:by as text))),
                  signal_provenance = coalesce(m.signal_provenance,'{}'::jsonb) || jsonb_build_object('youtube_subscribers_prev',
                      jsonb_build_object('value', m.youtube_subscribers, 'note','cleared when channel id was set manually'))
                where m.entity_id = :e and m.time = (select max(time) from entity_metrics where entity_id = :e)"""),
                {"cid": ich["youtube_channel_id"]["new"], "by": user.email, "e": entity_id})
    if changed:
        await db.commit()
        logger.info("manual data edit", kind="entities", id=str(entity_id), by=user.email, fields=sorted(changed), cache_cleared=invalidate_all())
    return {"id": str(entity_id), "kind": "entities", "changed": changed,
            "unchanged": sorted(set(clean_rest) | set(clean_ident) - set(changed)),
            "provenance": {k: ({"source": "manual", "by": user.email} if k in ich else (obj.data_provenance or {}).get("manual_fields", {}).get(k))
                           for k in {**clean_rest, **clean_ident}},
            "note": "Run scripts/recompute_v3.py --apply to refresh stored scores." if ich else None}


@router.patch("/venues/{venue_id}", summary="Manually set missing venue fields")
async def patch_venue(venue_id: UUID, body: Dict[str, Any], db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(*_ROLES))):
    return await _patch(db, Venue, VENUE_FIELDS, venue_id, body, user, "venues")


@router.patch("/cities/{city_id}", summary="Manually set missing city fields")
async def patch_city(city_id: UUID, body: Dict[str, Any], db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(*_ROLES))):
    return await _patch(db, City, CITY_FIELDS, city_id, body, user, "cities")
