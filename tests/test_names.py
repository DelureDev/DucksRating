from src.names import normalize, transliterate, NameMatcher


def test_normalize_case_and_spaces():
    assert normalize("  DelureKing ") == normalize("delureking")
    assert normalize("Sailor  Moon") == normalize("sailor moon")


def test_normalize_homoglyphs():
    # Real case: admin typed APOM4T_XPEHA in Latin lookalikes of Cyrillic АРОМ4Т_ХРЕНА
    assert normalize("APOM4T_XPEHA") == normalize("АРОМ4Т_ХРЕНА")
    assert normalize("Ёлка") == normalize("елка")


def test_exact_after_normalization_merges():
    m = NameMatcher(aliases={})
    assert m.resolve("Delureking").kind == "new"
    r = m.resolve("DelureKing")
    assert r.kind == "exact"
    assert r.canonical == "Delureking"  # first-seen spelling wins


def test_alias_wins_over_everything():
    m = NameMatcher(aliases={"Pihanina": "Пиханина"})
    r = m.resolve("Pihanina")
    assert r.kind == "alias"
    assert r.canonical == "Пиханина"
    # canonical from alias is now a known player
    assert m.resolve("Пиханина").kind == "exact"


def test_typo_auto_merges_at_90():
    m = NameMatcher(aliases={})
    m.resolve("Delureking")
    r = m.resolve("Delurking")  # one letter dropped -> score ≥ 90
    assert r.kind == "auto_merged"
    assert r.canonical == "Delureking"
    assert r.score >= 90


def test_borderline_becomes_new_with_review():
    m = NameMatcher(aliases={})
    m.resolve("Delureking")
    r = m.resolve("Delurek")  # ~82 similarity -> review, NOT merged
    assert r.kind == "new_review"
    assert r.canonical == "Delurek"
    assert r.similar_to == "Delureking"
    assert 70 <= r.score < 90


def test_distinct_name_is_silently_new():
    m = NameMatcher(aliases={})
    m.resolve("Демид")
    r = m.resolve("Гавр")
    assert r.kind == "new"
    assert r.canonical == "Гавр"


def test_resolution_is_stable_within_run():
    m = NameMatcher(aliases={})
    m.resolve("Delureking")
    assert m.resolve("Delurking").canonical == "Delureking"
    assert m.resolve("Delurking").canonical == "Delureking"  # second time too


def test_transliterate_basic():
    assert transliterate("Арчи") == "archi"
    assert transliterate("Демид") == "demid"
    assert transliterate("Доджер") == "dodzher"
    assert transliterate("Dodger") == "dodger"  # Latin passes through


def test_cyrillic_latin_same_nickname_auto_merges():
    # «Арчи» transliterates exactly to "archi" -> same player, no human needed
    m = NameMatcher(aliases={})
    m.resolve("Archi")
    r = m.resolve("Арчи")
    assert r.kind == "auto_merged"
    assert r.canonical == "Archi"
    assert r.score >= 90


def test_cyrillic_latin_close_nickname_suggests_review():
    # "dodzher" vs "dodger" is close but not exact -> review suggestion
    m = NameMatcher(aliases={})
    m.resolve("Dodger")
    r = m.resolve("Доджер")
    assert r.kind == "new_review"
    assert r.similar_to == "Dodger"
    assert 70 <= r.score < 90


def test_cyrillic_latin_unrelated_names_stay_separate():
    m = NameMatcher(aliases={})
    m.resolve("Demid")
    r = m.resolve("Гавр")
    assert r.kind == "new"
