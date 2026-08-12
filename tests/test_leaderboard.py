import datetime

from src.models import HistoryRow
from src.leaderboard import overall, monthly


def row(player, stars, knockouts=0, month=8, day=1, msg_id=1):
    return HistoryRow(msg_id=msg_id, date=datetime.date(2026, month, day),
                      tournament="T", place=1, raw_name=player,
                      player=player, stars=stars, knockouts=knockouts)


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
