"""Title filter against homonyms (fixtures, no network)."""
from app.services.news_filter import disambiguator_of, filter_titles, is_generic_name, title_passes, context_terms

KING_TITLES = [
    "Burger King launches new menu in India",
    "Lion King re-release breaks box office records",
    "King of the jungle: lion spotted in Gir",
    "Stephen King's new novel hits stands",
    "King announces new album and concert tour in Mumbai",
    "King concert in Pune sells out - Hindustan Times",
    "The king of pop music remembered",
]


def test_king_homonyms_rejected():
    r = filter_titles(KING_TITLES, "King", "artist", "Indian Pop")
    assert r.confidence == "generic_filtered"
    assert r.count == 2
    assert all("Burger" not in t and "jungle" not in t for t in r.sample_titles)


def test_king_all_noise_is_ambiguous_skipped_null():
    r = filter_titles(KING_TITLES[:4] + KING_TITLES[6:], "King", "artist")
    assert r.count is None and r.confidence == "ambiguous_skipped"


def test_jawan_film_counts_hindi_word_does_not():
    r = filter_titles(["Jawan box office collection crosses 1000 crore", "Jawan killed in encounter in Kashmir",
                       "Shah Rukh Khan Jawan film trailer breaks records", "Army jawan rescues children from flood",
                       "Jawan's party held in Delhi"], "Jawan", "movie", None, disambiguator_of("Jawan (film)"))
    assert r.count == 2 and r.confidence == "generic_filtered"
    assert "killed" not in " ".join(r.sample_titles)


def test_non_generic_name_needs_word_boundary_and_context():
    assert title_passes("Arijit Singh concert tickets go live", "Arijit Singh", context_terms("artist", None), False)
    assert title_passes("arijit singh announces new song", "Arijit Singh", context_terms("artist", None), False)
    assert not title_passes("Arijit Singh visits temple", "Arijit Singh", context_terms("artist", None), False)   # no context term
    assert not title_passes("Pritamvir wins election, singer congratulates", "Pritam", context_terms("artist", None), False)  # not a whole word
    assert not title_passes("Singer Arijit receives award", "Arijit Singh", context_terms("artist", None), False)  # full name required


def test_confidence_labels_and_dedupe_and_publisher_suffix():
    r = filter_titles(["Pritam new song out - Mint", "Pritam new song out - Times of India", "Pritam goes fishing"], "Pritam", "artist")
    assert r.confidence == "strict" and r.count == 1 and r.sample_titles == ["Pritam new song out"]
    z = filter_titles(["Pritam goes fishing"], "Pritam", "artist")
    assert z.count == 0 and z.confidence == "strict"          # a real zero for a non-generic name, not NULL


def test_generic_detection_and_disambiguator():
    assert is_generic_name("King") and is_generic_name("Pathaan") and not is_generic_name("Arijit Singh")
    assert disambiguator_of("Jawan (film)") == "film" and disambiguator_of("Arijit Singh") is None


# ── aliases ──────────────────────────────────────────────────────────────────
def test_alias_short_form_headline_counts():
    from app.services.news_filter import filter_titles
    titles = ["Honey Singh announces India tour dates", "Weather today in Delhi", "Honey Singh new album teaser out"]
    assert filter_titles(titles, "Yo Yo Honey Singh", "artist", "Music").count == 0
    r = filter_titles(titles, "Yo Yo Honey Singh", "artist", "Music", aliases=["Honey Singh", "Hirdesh Singh"])
    assert r.count == 2 and r.confidence == "strict"


def test_alias_still_needs_context_and_word_boundary():
    from app.services.news_filter import filter_titles
    r = filter_titles(["Honey Singhania wins award", "Honey Singh spotted at cafe"], "Yo Yo Honey Singh", "artist", None,
                      aliases=["Honey Singh"])
    assert r.count == 0


def test_usable_aliases_drops_generic_and_short():
    from app.services.news_filter import usable_aliases
    out = usable_aliases("Arijit Singh", ["Arijit Singh", "arijit  singh", "King", "Sun", "Singh Saab", "Arijit", "Indian singer"])
    assert "King" not in out and "Sun" not in out
    assert "Singh Saab" in out
    assert out.count("Arijit Singh") == 0       # equal to the name


def test_generic_entity_alias_keeps_strictness():
    from app.services.news_filter import filter_titles
    r = filter_titles(["king of the jungle roars", "Shah Rukh Khan King film trailer out"], "King", "movie", None, aliases=["King (2026 film)"])
    assert r.count == 1
