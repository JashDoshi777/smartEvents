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


# ── identity ids (youtube_channel_id / musicbrainz_id / wikidata_qid) ────────
def test_identity_validation_accepts_and_rejects():
    import pytest
    from fastapi import HTTPException
    from app.api.routes.admin_data import validate_identity
    ok = validate_identity({"youtube_channel_id": "UCtFOW7jJXChfFNoucRFqRmw", "wikidata_qid": " Q123 ",
                            "musicbrainz_id": "A1B2C3D4-0000-4000-8000-0123456789AB"})
    assert ok["wikidata_qid"] == "Q123" and ok["musicbrainz_id"].islower()
    for bad in ({"youtube_channel_id": "@arijit"}, {"youtube_channel_id": "UCshort"}, {"wikidata_qid": "123"},
                {"wikidata_qid": "Q0"}, {"musicbrainz_id": "not-a-uuid"}, {"wikidata_qid": 5}, {"wikidata_qid": ""}):
        with pytest.raises(HTTPException) as e:
            validate_identity(bad)
        assert e.value.status_code == 422


def test_apply_identity_edit_provenance_and_idempotence():
    from app.api.routes.admin_data import apply_identity_edit
    ext, ch = apply_identity_edit({"imdb_id": "x"}, {"wikidata_qid": "Q5"}, "a@b.c", "2026-01-01T00:00:00Z")
    assert ext["wikidata_qid"] == "Q5" and ext["imdb_id"] == "x" and ch["wikidata_qid"] == {"old": None, "new": "Q5"}
    assert ext["identity_manual"]["wikidata_qid"]["source"] == "manual" and ext["identity_manual"]["wikidata_qid"]["by"] == "a@b.c"
    ext2, ch2 = apply_identity_edit(ext, {"wikidata_qid": "Q5"}, "a@b.c")
    assert ch2 == {} and ext2 == ext
    ext3, ch3 = apply_identity_edit(ext, {"wikidata_qid": "Q6"}, "z@b.c")
    assert ext3["identity_manual"]["wikidata_qid"]["previous"] == "Q5" and ch3["wikidata_qid"]["new"] == "Q6"


def test_identity_fields_not_in_regular_whitelist_but_patch_route_exists():
    from app.api.routes.admin_data import ENTITY_FIELDS, IDENTITY_FIELDS
    assert not set(IDENTITY_FIELDS) & set(ENTITY_FIELDS)
    assert set(IDENTITY_FIELDS) == {"youtube_channel_id", "musicbrainz_id", "wikidata_qid"}
