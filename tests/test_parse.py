import datetime
import pytest

from src.models import RawPost
from src.parse import is_results_post, parse_post, PostParseError
from tests.sample_posts import SPY_007, ANNOUNCEMENT

DATE = datetime.date(2026, 8, 10)


def make_post(text, msg_id=100):
    return RawPost(msg_id=msg_id, date=DATE, text=text)


def test_is_results_post():
    assert is_results_post(SPY_007)
    assert is_results_post("итоги daily cup\n🥇 A — ⭐️ 1")  # case-insensitive
    assert is_results_post("🔥 ИТОГИ CUP 🔥\n...")  # marker not at char 0
    assert not is_results_post(ANNOUNCEMENT)
    assert not is_results_post("")


def test_parse_spy007_full():
    tr = parse_post(make_post(SPY_007, msg_id=555))
    assert tr.msg_id == 555
    assert tr.date == DATE
    assert tr.tournament == "SPY 007 TOURNAMENT"
    assert len(tr.lines) == 11
    first = tr.lines[0]
    assert (first.place, first.raw_name, first.stars, first.spades) == (1, "Демид", 2080, 23)
    vii = tr.lines[4]
    assert (vii.place, vii.raw_name, vii.stars, vii.spades) == (5, "Vii", 248, 0)
    last = tr.lines[10]
    assert (last.place, last.raw_name, last.stars, last.spades) == (11, "Sailor Moon", 300, 6)


def test_parse_format_variants():
    text = ("ИТОГИ MINI\n"
            "ТОП-3 игроков вечера\n"
            "🥇 Ali-Baba — ⭐️ 1 000 | 2 ♠️\n"   # hyphen in name, space in number
            "2) Vii - ⭐ 50\n"                    # paren place, plain hyphen, no VS16 star
            "3. Sailor Moon – ⭐️ 25")            # en dash
    tr = parse_post(make_post(text))
    assert [(l.place, l.raw_name, l.stars, l.spades) for l in tr.lines] == [
        (1, "Ali-Baba", 1000, 2), (2, "Vii", 50, 0), (3, "Sailor Moon", 25, 0)]


def test_broken_result_line_rejects_whole_post():
    text = SPY_007.replace("8. Delureking — ⭐️ 124", "8. Delureking — 124")  # star missing
    with pytest.raises(PostParseError) as ei:
        parse_post(make_post(text, msg_id=7))
    assert ei.value.msg_id == 7
    assert "8. Delureking" in ei.value.reason


def test_top_n_count_mismatch_rejects():
    text = SPY_007.replace("5. Vii — ⭐️ 248\n", "")  # says ТОП-11, has 10 lines
    with pytest.raises(PostParseError) as ei:
        parse_post(make_post(text))
    assert "11" in ei.value.reason


def test_non_sequential_places_reject():
    text = ("ИТОГИ X\n🥇 A — ⭐️ 10\n🥉 B — ⭐️ 5")  # place 2 missing, no ТОП-N line
    with pytest.raises(PostParseError):
        parse_post(make_post(text))


def test_no_result_lines_rejects():
    with pytest.raises(PostParseError):
        parse_post(make_post("ИТОГИ X\nбыло весело!"))


def test_chatter_lines_ignored():
    text = "ИТОГИ X\nТОП-1 игроков вечера\n🥇 A — ⭐️ 10\nСбор завтра в 19.00!"
    tr = parse_post(make_post(text))
    assert len(tr.lines) == 1


def test_missing_space_after_place_marker_rejects():
    text = "ИТОГИ MINI\n1. A — ⭐️ 10\n2. B — ⭐️ 5\n3.C — ⭐️ 1"
    with pytest.raises(PostParseError) as ei:
        parse_post(make_post(text))
    assert "3.C" in ei.value.reason


def test_time_like_chatter_line_still_ignored():
    text = "ИТОГИ X\nТОП-1 игроков вечера\n🥇 A — ⭐️ 10\n19.00 — сбор завтра"
    tr = parse_post(make_post(text))
    assert len(tr.lines) == 1
