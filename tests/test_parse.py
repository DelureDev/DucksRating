import datetime
import pytest

from src.models import RawPost
from src.parse import is_results_post, parse_post, PostParseError
from tests.sample_posts import (SPY_007, ANNOUNCEMENT, BROTHERS_407,
                                MYSTERY_428, GUEST_434)

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
    ("7. Alullla - 330 ⭐️", 7, "Alullla", 330, 0),          # msg 434: guest ⭐️ after the points
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


def test_transfer_in_parens_with_points():
    # real msg 232: annotation sits between name and points, stray inner spaces
    text = ("ИТОГИ GOOD BROTHERS TIMES\n"
            "🥇 Sailor Moon — ⭐️ 756\n"
            "2. Mr. BB (передал стек Sailor Moon ) — ⭐️ 432")
    tr = parse_post(make_post(text))
    assert tr.lines[0].transferred_to == ""
    line = tr.lines[1]
    assert (line.raw_name, line.stars, line.transferred_to) == (
        "Mr. BB", 432, "Sailor Moon")


def test_transfer_after_dash_without_points():
    # real msg 356: annotation replaces the points segment entirely
    text = ("ИТОГИ GOOD BROTHERS TIMES\n"
            "🥇 DelurKing — ⭐️ 500\n"
            "2. Calimocho — передал стек DelurKing")
    tr = parse_post(make_post(text))
    line = tr.lines[1]
    assert (line.raw_name, line.stars, line.transferred_to) == (
        "Calimocho", 0, "DelurKing")


def test_transfer_feminine_in_parens_bare():
    # real msg 275: «передала», no points at all
    text = ("ИТОГИ GOOD BROTHERS TIMES\n"
            "🥇 ambiv8lence — ⭐️ 304\n"
            "2. Хи-хи (передала стек ambiv8lence)")
    tr = parse_post(make_post(text))
    line = tr.lines[1]
    assert (line.raw_name, line.stars, line.transferred_to) == (
        "Хи-хи", 0, "ambiv8lence")


def test_transfer_target_backslashes_stripped():
    text = ("ИТОГИ GOOD BROTHERS TIMES\n"
            "🥇 T\\_Vi — ⭐️ 270\n"
            "2. Gavr (передал стек T\\_Vi) — ⭐️ 100")
    tr = parse_post(make_post(text))
    assert tr.lines[1].transferred_to == "T_Vi"


# --- New dialect since msg 407 (2026-08-26): the admin dropped medals and
# stars.  Top-3 lines carry a ♠️ prefix, points are glued to the name with a
# plain hyphen or separated by spaces only, knockouts trail as "13 ♠️".


def test_new_dialect_spade_prefix_and_glued_points():
    text = ("ИТОГИ GOOD BROTHERS TIME\n"
            "ТОП-4 игрока вечера\n"
            "♠️1. T.VI-4230\n"
            "♠️2. Dotadagestan-2820\n"
            "♠️3. СтальИньЯнь-1974\n"
            "4. All_in_a-1410")
    tr = parse_post(make_post(text))
    assert [(l.place, l.raw_name, l.stars) for l in tr.lines] == [
        (1, "T.VI", 4230), (2, "Dotadagestan", 2820),
        (3, "СтальИньЯнь", 1974), (4, "All_in_a", 1410)]


def test_new_dialect_space_separated_points():
    # real msg 413: no dash at all between name and points
    text = ("ИТОГИ GIPER BOUNTY\n"
            "ТОП-5 игрока вечера\n"
            "♠️1. TG_User_170050624   3270\n"
            "♠️2. All_in_a   2180\n"
            "♠️3. Gavr   1526\n"
            "4. Kastiel  1090\n"
            "5. Kai Angel")
    tr = parse_post(make_post(text))
    assert [(l.place, l.raw_name, l.stars) for l in tr.lines] == [
        (1, "TG_User_170050624", 3270), (2, "All_in_a", 2180),
        (3, "Gavr", 1526), (4, "Kastiel", 1090), (5, "Kai Angel", 0)]


def test_new_dialect_trailing_knockouts():
    # real msg 423: knockouts as a bare "13 ♠️" tail, one subscript minus
    text = ("ИТОГИ TH. FREE-ROLL BOUNTY TOURNAMENT\n"
            "ТОП-6 игрока вечера\n"
            "♠️1. Хайзенберг-1930 13 ♠️\n"
            "♠️2. Kinguruwa33-620 2 ♠️\n"
            "♠️3. Dotadagestan-1294 10 ♠️\n"
            "4. Андрей-410 2 ♠️\n"
            "5. Gavr-126\n"
            "6. Kradushiy₋500 5 ♠️")
    tr = parse_post(make_post(text))
    assert [(l.place, l.raw_name, l.stars, l.knockouts) for l in tr.lines] == [
        (1, "Хайзенберг", 1930, 13), (2, "Kinguruwa33", 620, 2),
        (3, "Dotadagestan", 1294, 10), (4, "Андрей", 410, 2),
        (5, "Gavr", 126, 0), (6, "Kradushiy", 500, 5)]


def test_new_dialect_bare_names_with_digits_stay_bare():
    # digits glued straight to the name (no hyphen, no space) are not points
    text = ("ИТОГИ X\n"
            "♠️1. T.VI-4230\n"
            "2. Biba_Egik\n"
            "3. gg3\n"
            "4. Duck_0451")
    tr = parse_post(make_post(text))
    assert [(l.raw_name, l.stars) for l in tr.lines] == [
        ("T.VI", 4230), ("Biba_Egik", 0), ("gg3", 0), ("Duck_0451", 0)]


def test_new_dialect_present_tense_transfer():
    text = ("ИТОГИ GOOD BROTHERS TIME\n"
            "♠️1. Dotadagestan-2820\n"
            "2. Mvsnika-564 (передает стек Dotadagestan)")
    tr = parse_post(make_post(text))
    line = tr.lines[1]
    assert (line.raw_name, line.stars, line.transferred_to) == (
        "Mvsnika", 564, "Dotadagestan")


def test_glued_digits_are_points_only_in_new_dialect():
    # the same "Anna-2" that stays a bare name in old posts (see
    # test_hyphen_digit_name_is_bare_participant) is points here
    text = "ИТОГИ X\n♠️1. T.VI-4230\n2. Anna-2"
    tr = parse_post(make_post(text))
    assert (tr.lines[1].raw_name, tr.lines[1].stars) == ("Anna", 2)


def test_new_dialect_malformed_glued_line_rejects():
    text = "ИТОГИ X\n♠️1. T.VI-4230\n2. Xx-100 zz"
    with pytest.raises(PostParseError) as ei:
        parse_post(make_post(text))
    assert "Xx-100 zz" in ei.value.reason


def test_new_dialect_suit_tail_after_points():
    # real msg 428: the points carry a decorative ♠️, usually glued, sometimes
    # after a space; it never means knockouts (no count follows it)
    text = ("ИТОГИ MYSTERY DUCK\n"
            "ТОП-5 игрока вечера\n"
            "♠️1. Ула 2950♠️\n"
            "♠️2. cold_iemens13 1700♠️\n"
            "♠️3. amenappanema 1140♠️\n"
            "4. Amourrrr_6 300 ♠️\n"
            "5. dmitriy 1180")
    tr = parse_post(make_post(text))
    assert [(l.place, l.raw_name, l.stars, l.knockouts) for l in tr.lines] == [
        (1, "Ула", 2950, 0), (2, "cold_iemens13", 1700, 0),
        (3, "amenappanema", 1140, 0), (4, "Amourrrr_6", 300, 0),
        (5, "dmitriy", 1180, 0)]


def test_new_dialect_knockout_tail_still_wins_over_suit_tail():
    # the msg 423 form "points knockouts ♠️" must keep parsing as knockouts
    text = ("ИТОГИ X\n"
            "♠️1. Хайзенберг-1930 13 ♠️\n"
            "2. Ула 2950♠️")
    tr = parse_post(make_post(text))
    assert [(l.raw_name, l.stars, l.knockouts) for l in tr.lines] == [
        ("Хайзенберг", 1930, 13), ("Ула", 2950, 0)]


def test_new_dialect_suit_glued_to_bare_name_stripped():
    # real msg 428, place 21: a suit stuck to a name with no points at all
    text = ("ИТОГИ X\n"
            "♠️1. Ула 2950♠️\n"
            "2. missJuliya1679♠️\n"
            "3. robbie_robson")
    tr = parse_post(make_post(text))
    assert [(l.raw_name, l.stars) for l in tr.lines] == [
        ("Ула", 2950), ("missJuliya1679", 0), ("robbie_robson", 0)]


def test_tournament_name_on_line_below_bare_header():
    # since msg 428 the header is a bare «ИТОГИ» and the name sits underneath
    text = ("🗣ИТОГИ \nMYSTERY DUCK EVENT\n\n"
            "ТОП-1 игрока вечера\n\n♠️1. Ула 2950♠️")
    tr = parse_post(make_post(text))
    assert tr.tournament == "MYSTERY DUCK EVENT"


def test_bare_header_without_name_line_keeps_empty_tournament():
    text = "ИТОГИ\nТОП-1 игроков вечера\n🥇 A — ⭐️ 10"
    tr = parse_post(make_post(text))
    assert tr.tournament == ""


def test_parse_mystery_428_full():
    tr = parse_post(make_post(MYSTERY_428, msg_id=428))
    assert tr.tournament == "MYSTERY DUCK EVENT"
    assert len(tr.lines) == 32
    assert [l.place for l in tr.lines] == list(range(1, 33))
    assert all(l.knockouts == 0 for l in tr.lines)
    assert (tr.lines[0].raw_name, tr.lines[0].stars) == ("Ула", 2950)
    assert (tr.lines[4].raw_name, tr.lines[4].stars) == ("dmitriy", 1180)
    assert (tr.lines[6].raw_name, tr.lines[6].stars) == ("Amourrrr_6", 300)
    assert (tr.lines[9].raw_name, tr.lines[9].stars) == ("kinguruwa33", 2880)
    assert (tr.lines[20].raw_name, tr.lines[20].stars) == ("missJuliya1679", 0)
    assert (tr.lines[31].raw_name, tr.lines[31].stars) == ("Vrotan_Zasoev", 0)


def test_parse_guest_434_full():
    tr = parse_post(make_post(GUEST_434, msg_id=434))
    assert tr.tournament == "X GUEST EVENT ⭐️AIUIIIA"
    assert len(tr.lines) == 49
    assert [l.place for l in tr.lines] == list(range(1, 50))
    assert (tr.lines[0].raw_name, tr.lines[0].stars) == ("Vikki", 1980)
    assert (tr.lines[6].raw_name, tr.lines[6].stars) == ("Alullla", 330)
    assert (tr.lines[8].raw_name, tr.lines[8].stars) == ("Gavr", 198)
    assert (tr.lines[9].raw_name, tr.lines[9].stars) == ("Kirill", 0)
    assert (tr.lines[43].raw_name, tr.lines[43].stars) == ("Anna30₁0", 0)
    assert (tr.lines[48].raw_name, tr.lines[48].stars) == ("Skripov_Ivan", 0)


def test_parse_brothers_407_full():
    tr = parse_post(make_post(BROTHERS_407, msg_id=407))
    assert tr.tournament == "GOOD BROTHERS TIME TOURNAMENT"
    assert len(tr.lines) == 33
    assert [l.place for l in tr.lines] == list(range(1, 34))
    first = tr.lines[0]
    assert (first.place, first.raw_name, first.stars) == (1, "T.VI", 4230)
    mvsnika = tr.lines[7]
    assert (mvsnika.raw_name, mvsnika.stars, mvsnika.transferred_to) == (
        "Mvsnika", 564, "Dotadagestan")
    ula = tr.lines[10]
    assert (ula.raw_name, ula.stars, ula.transferred_to) == (
        "Ула", 0, "all_in_a")
    pereliv = tr.lines[14]
    assert (pereliv.raw_name, pereliv.stars, pereliv.transferred_to) == (
        "pereliv", 4230, "T_Vi")
    ivan = tr.lines[29]
    assert (ivan.raw_name, ivan.stars) == ("Иван Васильев", 0)
    last = tr.lines[32]
    assert (last.place, last.raw_name, last.stars) == (33, "Duck_1716", 0)
