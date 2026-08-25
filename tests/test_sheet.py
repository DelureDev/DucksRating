import datetime

import pytest

from src.models import HistoryRow
from src.sheet import (HISTORY_HEADER, history_to_values, values_to_history,
                       overall_to_values, monthly_to_values)


def row(msg_id, place=1, player="A"):
    return HistoryRow(msg_id=msg_id, date=datetime.date(2026, 8, 10),
                      tournament="CUP", place=place, raw_name=player,
                      player=player, stars=100, knockouts=2)


def test_history_roundtrip():
    rows = [row(101), row(102)]
    values = history_to_values(rows)
    assert values[0] == HISTORY_HEADER
    assert values_to_history(values) == [row(102), row(101)]  # newest first


def test_history_to_values_sorts_newest_first_then_place():
    values = history_to_values([row(101), row(102, place=2), row(102, place=1)])
    ids_places = [(v[0], v[3]) for v in values[1:]]
    assert ids_places == [(102, 1), (102, 2), (101, 1)]


def test_values_to_history_skips_blank_and_header():
    values = [HISTORY_HEADER,
              ["101", "2026-08-10", "CUP", "1", "A", "A", "100", "2"],
              ["", "", "", "", "", "", "", ""]]
    assert values_to_history(values) == [row(101)]


def test_overall_to_values():
    board = [{"rank": 1, "player": "B", "stars": 300, "knockouts": 1, "tournaments": 1}]
    values = overall_to_values(board)
    assert values == [["rank", "player", "stars ⭐️", "knockouts ♠️", "tournaments"],
                      [1, "B", 300, 1, 1]]


def test_monthly_to_values_sections():
    months = [("2026-08", [{"rank": 1, "player": "A", "stars": 20,
                            "knockouts": 0, "tournaments": 1}])]
    values = monthly_to_values(months)
    assert values[0] == ["2026-08"]
    assert values[1][0] == "rank"
    assert values[2] == [1, "A", 20, 0, 1]
    assert values[3] == []


def test_history_roundtrip_with_transfer_columns():
    r = HistoryRow(msg_id=101, date=datetime.date(2026, 8, 10),
                   tournament="CUP", place=2, raw_name="Nasty",
                   player="Nasty", stars=228, knockouts=0,
                   transferred_to="Кes", transfer_player="Kes")
    values = history_to_values([r])
    assert values[1][8:] == ["Кes", "Kes"]
    assert values_to_history(values) == [r]


def test_values_to_history_pads_old_8col_rows():
    values = [["101", "2026-08-10", "CUP", "1", "A", "A", "100", "2"]]
    r = values_to_history(values)[0]
    assert (r.transferred_to, r.transfer_player) == ("", "")


def test_values_to_history_short_row_raises_with_row_context():
    values = [HISTORY_HEADER, ["101", "2026-08-10", "CUP"]]
    with pytest.raises(ValueError) as ei:
        values_to_history(values)
    assert "row 2" in str(ei.value)


def test_values_to_history_bad_date_raises_with_row_context():
    values = [["101", "not-a-date", "CUP", "1", "A", "A", "100", "2"]]
    with pytest.raises(ValueError) as ei:
        values_to_history(values)
    assert "row 1" in str(ei.value)
