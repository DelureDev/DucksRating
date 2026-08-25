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
    assert (first.place, first.raw_name, first.stars, first.knockouts) == (1, "Демид", 2080, 23)
    vii = tr.lines[4]
    assert (vii.place, vii.raw_name, vii.stars, vii.knockouts) == (5, "Vii", 248, 0)
    last = tr.lines[10]
    assert (last.place, last.raw_name, last.stars, last.knockouts) == (11, "Sailor Moon", 300, 6)


def test_parse_format_variants():
    text = ("ИТОГИ MINI\n"
            "ТОП-3 игроков вечера\n"
            "🥇 Ali-Baba — ⭐️ 1 000 | 2 ♠️\n"   # hyphen in name, space in number
            "2) Vii - ⭐ 50\n"                    # paren place, plain hyphen, no VS16 star
            "3. Sailor Moon – ⭐️ 25")            # en dash
    tr = parse_post(make_post(text))
    assert [(l.place, l.raw_name, l.stars, l.knockouts) for l in tr.lines] == [
        (1, "Ali-Baba", 1000, 2), (2, "Vii", 50, 0), (3, "Sailor Moon", 25, 0)]


def test_broken_result_line_rejects_whole_post():
    text = SPY_007.replace("8. Delureking — ⭐️ 124", "8. Delureking — ⭐️")  # number missing
    with pytest.raises(PostParseError) as ei:
        parse_post(make_post(text, msg_id=7))
    assert ei.value.msg_id == 7
    assert "8. Delureking" in ei.value.reason


def test_skipped_place_number_accepted():
    # real msg 374: header says ТОП-23 but the admin's numbering jumps 13 → 15;
    # the skipped number is the channel's problem, the post still counts
    text = ("ИТОГИ BIG FREE-ROLL BOUNTY\n"
            "ТОП-4 игроков вечера\n"
            "🥇 Rena — ⭐️ 3170 | 11 ♠️\n"
            "2. Sanatolievich — ⭐️ 690\n"
            "4. Kradushiy_")
    tr = parse_post(make_post(text))
    assert [(l.place, l.raw_name) for l in tr.lines] == [
        (1, "Rena"), (2, "Sanatolievich"), (4, "Kradushiy_")]


def test_top_n_truncated_post_rejects():
    # says ТОП-11 but the post ends at place 9: neither the line count nor the
    # last place explains the header, so the post is cut short
    text = SPY_007.split("10. Chivas")[0]
    with pytest.raises(PostParseError) as ei:
        parse_post(make_post(text))
    assert "11" in ei.value.reason


def test_out_of_order_places_reject():
    text = "ИТОГИ X\n🥇 A — ⭐️ 10\n3. B — ⭐️ 5\n2. C — ⭐️ 1"
    with pytest.raises(PostParseError):
        parse_post(make_post(text))


def test_duplicate_places_reject():
    text = "ИТОГИ X\n🥇 A — ⭐️ 10\n2. B — ⭐️ 5\n2. C — ⭐️ 1"
    with pytest.raises(PostParseError):
        parse_post(make_post(text))


def test_places_not_starting_at_one_reject():
    text = "ИТОГИ X\n2. B — ⭐️ 5\n3. C — ⭐️ 1"  # top of the list missing
    with pytest.raises(PostParseError):
        parse_post(make_post(text))


def test_no_result_lines_rejects():
    with pytest.raises(PostParseError):
        parse_post(make_post("ИТОГИ X\nбыло весело!"))


def test_chatter_lines_ignored():
    text = "ИТОГИ X\nТОП-1 игроков вечера\n🥇 A — ⭐️ 10\nСбор завтра в 19.00!"
    tr = parse_post(make_post(text))
    assert len(tr.lines) == 1


def test_missing_space_after_place_marker_parses():
    # real posts contain lines like "7.Илья —  ⭐️ 594" — no space after the dot
    text = "ИТОГИ MINI\n1. A — ⭐️ 10\n2. B — ⭐️ 5\n3.C — ⭐️ 1"
    tr = parse_post(make_post(text))
    assert (tr.lines[2].place, tr.lines[2].raw_name, tr.lines[2].stars) == (3, "C", 1)


def test_time_like_chatter_line_still_ignored():
    text = "ИТОГИ X\nТОП-1 игроков вечера\n🥇 A — ⭐️ 10\n19.00 — сбор завтра"
    tr = parse_post(make_post(text))
    assert len(tr.lines) == 1


def test_bare_participant_lines_parse_as_zero_stars():
    text = ("ИТОГИ NIGHT CUP\n"
            "ТОП-4 игроков вечера\n"
            "🥇 Демид — ⭐️ 500 | 5 ♠️\n"
            "2. Vii — ⭐️ 100\n"
            "3. Sailormoon\n"
            "4. Mr. BB")
    tr = parse_post(make_post(text))
    assert [(l.place, l.raw_name, l.stars, l.knockouts) for l in tr.lines] == [
        (1, "Демид", 500, 5), (2, "Vii", 100, 0),
        (3, "Sailormoon", 0, 0), (4, "Mr. BB", 0, 0)]


def test_dash_number_line_without_star_parses_as_stars():
    text = "ИТОГИ X\n🥇 A — ⭐️ 10\n2. B — 124"
    tr = parse_post(make_post(text))
    assert (tr.lines[1].raw_name, tr.lines[1].stars) == ("B", 124)


def _post_with_variant_line(line, place):
    filler = [f"{i}. Filler{i} — ⭐️ 10" for i in range(1, place)]
    return make_post("ИТОГИ VARIANT CUP\n" + "\n".join(filler + [line]))


@pytest.mark.parametrize("line,place,name,stars,knockouts", [
    ("🥇 Ден — ⭐️ 500 | ⭐️ 7", 1, "Ден", 500, 7),          # msg 59: star emoji in knockouts slot
    ("🥇 Ула — ⭐️ 4470 | ⭐️ 12", 1, "Ула", 4470, 12),      # msg 82: same
    ("4. ОляЛя — 1 104 очка", 4, "ОляЛя", 1104, 0),         # msg 91: no star, trailing word
    ("🥈 StBard — ⭐️ 380|3 ♥️", 2, "StBard", 380, 3),       # msg 158: no spaces, heart emoji
    ("🥈Alamroom —  ⭐️ 1 370", 2, "Alamroom", 1370, 0),     # msg 202: no space after medal
    ("11. Stepanov stepan —  200", 11, "Stepanov stepan", 200, 0),  # msg 209: starless points
    ("11. m0nakhov —  200", 11, "m0nakhov", 200, 0),        # msg 215: same
    ("5. Вованчик — ⭐️ 120 |", 5, "Вованчик", 120, 0),      # msg 59: dangling pipe
    ("13. Пиханина — ⭐️ 350 |", 13, "Пиханина", 350, 0),    # msg 82: same
    ("7.Илья —  ⭐️ 594", 7, "Илья", 594, 0),                # msg 91: no space after number
    ("🥇Mr.ВB ⭐️635 | ♠️10", 1, "Mr.ВB", 635, 10),          # msg 394: no dash before stars
    ("🥈StepanovStepan ⭐️1390|♠️26", 2, "StepanovStepan", 1390, 26),  # msg 394: same, no spaces
])
def test_real_world_format_variants(line, place, name, stars, knockouts):
    tr = parse_post(_post_with_variant_line(line, place))
    last = tr.lines[-1]
    assert (last.place, last.raw_name, last.stars, last.knockouts) == (
        place, name, stars, knockouts)


def test_backslashes_stripped_from_names():
    text = "ИТОГИ X\n🥇 Kradushiy\\_ — ⭐️ 10\n2. A\\_Cheptsov"
    tr = parse_post(make_post(text))
    assert [l.raw_name for l in tr.lines] == ["Kradushiy_", "A_Cheptsov"]


def test_dash_beats_starless_boundary_when_both_present():
    # with both a star-number and a later dash-number on one line, the dash
    # stays the separator: the star-number segment belongs to the name
    text = "ИТОГИ X\n🥇 Name ⭐️100 — 200"
    tr = parse_post(make_post(text))
    assert (tr.lines[0].raw_name, tr.lines[0].stars) == ("Name ⭐️100", 200)


def test_hyphen_digit_name_is_bare_participant():
    # "Anna-2" is a name, not "Anna scored 2": glued hyphens belong to names
    text = "ИТОГИ X\n🥇 A — ⭐️ 10\n2. Anna-2"
    tr = parse_post(make_post(text))
    assert (tr.lines[1].place, tr.lines[1].raw_name,
            tr.lines[1].stars) == (2, "Anna-2", 0)


def test_hyphen_digit_name_with_points_segment():
    text = "ИТОГИ X\n🥇 Anna-2 — ⭐️ 100"
    tr = parse_post(make_post(text))
    assert (tr.lines[0].raw_name, tr.lines[0].stars) == ("Anna-2", 100)


def test_malformed_dash_line_still_rejects():
    text = "ИТОГИ X\n🥇 A — ⭐️ 10\n2. Xx — 100 zz"
    with pytest.raises(PostParseError):
        parse_post(make_post(text))
