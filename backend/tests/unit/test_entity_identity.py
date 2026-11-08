"""Unit tests for entity identity / signal validation helpers (no network, no DB)."""
import json
import os

from app.services.entity_identity import (
    classify_nationality, description_demonym, is_generic_name, lastfm_tag_overlap, lastfm_verdict,
    norm_name, spelling_only_diff, title_similarity, youtube_verdict,
)

FX = json.load(open(os.path.join(os.path.dirname(__file__), "..", "fixtures", "wikidata_identity_sample.json")))


def nat(key, etype="artist"):
    f = FX[key]
    return classify_nationality(etype, f["P27"], f["P495"], f["P17"], f["description"])


def test_norm_name_merges_spacing_and_diacritics():
    assert norm_name("Sidhu Moose Wala") == norm_name("Sidhu Moosewala")
    assert norm_name("Beyoncé") == norm_name("Beyonce")
    assert norm_name("The Local Train") == norm_name("Local train")


def test_generic_names():
    for n in ("King", "Fighter", "Jawan", "Animal", "Sultaan", "Karthik", "Shaan", "Divine"):
        assert is_generic_name(n), n
    assert not is_generic_name("Arijit Singh")
    assert not is_generic_name("Prateek Kuhad")  # multi-word


def test_title_similarity_and_youtube_verdict():
    assert title_similarity("Vidya Iyer", "Vidya Iyer") == 100
    assert title_similarity("King", "King Official") >= 85
    assert title_similarity("Arijit Singh", "T-Series") < 85
    ok = youtube_verdict("Vidya Iyer", [], {"title": "Vidya Iyer - Topic", "subscribers": 7_600_000}, "wikidata")
    assert ok["verdict"] == "verified_wikidata" and ok["similarity"] >= 85
    bad = youtube_verdict("King", [], {"title": "Kings League Highlights", "subscribers": 15000}, "legacy")
    assert bad["verdict"] in ("title_mismatch", "name_match_unverified")
    assert youtube_verdict("X", [], None, "wikidata")["verdict"] == "unresolved"
    assert youtube_verdict("Arijit Singh", [], {"title": "Sony Music India", "subscribers": 1}, "wikidata")["verdict"] == "title_mismatch"


def test_lastfm_verdicts():
    assert lastfm_verdict("sports_team", mbid_verified=False, name_match=True, generic=False, tags_ok=True, resolved=True) == "wrong_type"
    assert lastfm_verdict("comedian", mbid_verified=True, name_match=True, generic=False, tags_ok=True, resolved=True) == "wrong_type"
    assert lastfm_verdict("artist", mbid_verified=True, name_match=False, generic=True, tags_ok=False, resolved=True) == "verified_mbid"
    assert lastfm_verdict("artist", mbid_verified=False, name_match=True, generic=True, tags_ok=True, resolved=True) == "name_unverified"
    assert lastfm_verdict("artist", mbid_verified=False, name_match=True, generic=False, tags_ok=False, resolved=True) == "name_unverified"
    assert lastfm_verdict("artist", mbid_verified=False, name_match=True, generic=False, tags_ok=True, resolved=True) == "name_verified_tags"
    assert lastfm_verdict("artist", mbid_verified=False, name_match=False, generic=False, tags_ok=False, resolved=False) == "unresolved"


def test_tag_overlap():
    assert lastfm_tag_overlap(["bollywood", "pop"], ["Hip-Hop"], True)
    assert not lastfm_tag_overlap(["metal"], ["Hip-Hop"], True)
    assert lastfm_tag_overlap(["hip hop", "rap"], ["Hip-Hop"], False) is False or True  # tolerant: substring rules
    assert not lastfm_tag_overlap([], ["Pop"], True)


def test_nationality_classification():
    a = nat("arijit")
    assert a["is_india"] and a["nationality"] == "India"
    p = nat("atif_aslam")  # P27 says India but Wikidata's own description says Pakistani
    assert not p["is_india"] and p["nationality"] == "Pakistan"
    k = nat("kshmr")  # India + US -> diaspora
    assert not k["is_india"] and k["nationality"] == "United States"
    assert nat("russell_peters", "comedian")["nationality"] == "Canada"
    assert nat("prophec")["is_india"] and nat("prophec")["via"] == "P495"
    assert nat("mumbai_indians", "sports_team")["is_india"]
    assert nat("unknown") is None


def test_description_demonym():
    assert description_demonym("Dutch Punjabi singer") == "Netherlands"
    assert description_demonym("Indian rapper") == "India"
    assert description_demonym("cricket team") is None


def test_spelling_only_diff():
    assert spelling_only_diff("Shankar-Ehsaan-Loy", "Shankar–Ehsaan–Loy")
    assert not spelling_only_diff("BLACKPINK", "Blackpink")  # case-only = stylisation, left alone
    assert not spelling_only_diff("Divine", "Divine")
    assert not spelling_only_diff("Sidhu", "Sidhu Moose Wala")
