import datetime

from src.models import HistoryRow
from src.leaderboard import overall, monthly


def row(player, stars, knockouts=0, month=8, day=1, msg_id=1, transfer=""):
    return HistoryRow(msg_id=msg_id, date=datetime.date(2026, month, day),
                      tournament="T", place=1, raw_name=player,
                      player=player, stars=stars, knockouts=knockouts,
                      transferred_to=transfer, transfer_player=transfer)


def test_overall_totals_and_order():
    rows = [row("A", 100, 2), row("B", 300, 1), row("A", 50, 3)]
    board = overall(rows)
    assert [b["player"] for b in board] == ["B", "A"]
    a = board[1]
    assert (a["stars"], a["knockouts"], a["tournaments"]) == (150, 5, 2)


def test_overall_tie_ranks_skip():
    board = overall([row("A", 100), row("B", 100), row("C", 50)])
    assert [b["rank"] for b in board] == [1, 1, 3]


def test_monthly_groups_and_orders_desc():
    rows = [row("A", 10, month=7), row("A", 20, month=8), row("B", 5, month=8)]
    months = monthly(rows)
    assert [m for m, _ in months] == ["2026-08", "2026-07"]
    aug = dict((b["player"], b["stars"]) for b in months[0][1])
    assert aug == {"A": 20, "B": 5}


def stars_by_player(board):
    return {b["player"]: b["stars"] for b in board}


def test_transferrer_gets_receivers_stars_ignoring_printed():
    # club rule: same points as the partner, printed own points ignored
    board = overall([row("Kes", 1140), row("Nasty", 228, transfer="Kes")])
    assert stars_by_player(board)["Nasty"] == 1140


def test_transfer_chain_all_get_final_stars():
    board = overall([row("Sailormoon", 532),
                     row("ambiv8lence", 304, transfer="Sailormoon"),
                     row("Хи-хи", 0, transfer="ambiv8lence")])
    d = stars_by_player(board)
    assert (d["ambiv8lence"], d["Хи-хи"]) == (532, 532)


def test_transfer_fan_in_all_get_same():
    board = overall([row("All_in_a", 472),
                     row("Dotadagestan", 0, transfer="All_in_a"),
                     row("Лера", 0, transfer="All_in_a")])
    d = stars_by_player(board)
    assert (d["Dotadagestan"], d["Лера"]) == (472, 472)


def test_transfer_resolves_within_same_tournament_only():
    # X scored 100 in msg 1; Y's transfer in msg 2 must use X's msg-2 result
    board = overall([row("X", 100, msg_id=1), row("X", 999, msg_id=2),
                     row("Y", 0, msg_id=2, transfer="X")])
    assert stars_by_player(board)["Y"] == 999


def test_transfer_target_missing_keeps_own_stars():
    board = overall([row("A", 100), row("B", 228, transfer="Ghost")])
    assert stars_by_player(board)["B"] == 228


def test_transfer_cycle_keeps_own_stars():
    board = overall([row("A", 100, transfer="B"), row("B", 200, transfer="A")])
    d = stars_by_player(board)
    assert (d["A"], d["B"]) == (100, 200)


def test_knockouts_not_transferred():
    board = overall([row("Kes", 1140, knockouts=10),
                     row("Nasty", 0, knockouts=2, transfer="Kes")])
    by = {b["player"]: b for b in board}
    assert by["Nasty"]["knockouts"] == 2


def test_monthly_applies_transfer_stars():
    months = monthly([row("Kes", 1140), row("Nasty", 0, transfer="Kes")])
    aug = stars_by_player(months[0][1])
    assert aug["Nasty"] == 1140
