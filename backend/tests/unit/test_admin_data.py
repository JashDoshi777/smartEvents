"""Admin data-gap PATCH validation + provenance, and city scores_basis."""
import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from app.api.routes import admin_data as ad
from app.api.routes.cities import scores_basis


def test_unknown_and_invalid_fields_rejected():
    with pytest.raises(HTTPException) as e:
        ad.validate_patch({"name": "x"}, ad.ENTITY_FIELDS)
    assert e.value.status_code == 422
    with pytest.raises(HTTPException):
        ad.validate_patch({"total_capacity": -5}, ad.VENUE_FIELDS)
    with pytest.raises(HTTPException):
        ad.validate_patch({"lat": 91}, ad.VENUE_FIELDS)
    with pytest.raises(HTTPException):
        ad.validate_patch({"image_url": "javascript:alert(1)"}, ad.ENTITY_FIELDS)
    with pytest.raises(HTTPException):
        ad.validate_patch({"venue_type": "spaceship"}, ad.VENUE_FIELDS)
    with pytest.raises(HTTPException):
        ad.validate_patch({"language": None}, ad.ENTITY_FIELDS)
    with pytest.raises(HTTPException):
        ad.validate_patch({}, ad.ENTITY_FIELDS)
    assert ad.validate_patch({"total_capacity": 1200.0, "venue_type": "arena"}, ad.VENUE_FIELDS) == {"total_capacity": 1200, "venue_type": "arena"}
    assert ad.validate_patch({"language": "  Hindi "}, ad.ENTITY_FIELDS) == {"language": "Hindi"}


def test_apply_manual_edit_records_provenance():
    from app.models.entity import Entity
    obj = Entity(name="X", entity_type="artist", language=None, genre="Pop", data_provenance={"source": "wikidata"})
    ch = ad.apply_manual_edit(obj, {"language": "Hindi", "genre": "Pop"}, "analyst@x.com")
    assert list(ch) == ["language"] and obj.language == "Hindi"
    mf = obj.data_provenance["manual_fields"]["language"]
    assert mf["source"] == "manual" and mf["by"] == "analyst@x.com" and mf["at"]
    assert obj.data_provenance["source"] == "wikidata"                      # existing provenance kept
    assert obj.data_provenance["manual_audit"][0]["old"] is None


def test_scores_basis_labels():
    c = lambda prov, **s: SimpleNamespace(data_provenance=prov, nightlife_score=s.get("n"), sports_affinity_score=None,
                                          arts_culture_score=None, comedy_market_size=None, music_market_size=None)
    assert scores_basis(c({"scores_basis": "derived"}, n=40.0)) == "derived"
    assert scores_basis(c(None, n=80.0)) == "editorial"
    assert scores_basis(c({"source": "wikidata"})) is None


async def test_admin_routes_require_auth(client):
    for method, path in (("get", "/admin/data-gaps?kind=entities"), ("get", "/admin/jobs"), ("post", "/admin/jobs/entity_metrics/run"),
                         ("patch", "/admin/entities/00000000-0000-0000-0000-000000000000")):
        r = await getattr(client, method)(path)
        assert r.status_code in (401, 403), (path, r.status_code)
