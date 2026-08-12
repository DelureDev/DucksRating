import datetime
import json
import os

import gspread

from .models import HistoryRow

HISTORY_HEADER = ["msg_id", "date", "tournament", "place",
                  "raw_name", "player", "stars", "knockouts"]
BOARD_HEADER = ["rank", "player", "stars ⭐️", "knockouts ♠️", "tournaments"]
REVIEW_HEADER = ["date added", "type", "details"]
AUTOMERGED_HEADER = ["date added", "details"]
ALIASES_HEADER = ["written as", "real player"]
TAB_ROWS = {"History": HISTORY_HEADER, "Overall": BOARD_HEADER,
            "Monthly": [], "Aliases": ALIASES_HEADER,
            "Needs review": REVIEW_HEADER,
            "Auto-merged": AUTOMERGED_HEADER}


def history_to_values(rows: list[HistoryRow]) -> list[list]:
    ordered = sorted(rows, key=lambda r: (-r.msg_id, r.place))
    return [HISTORY_HEADER] + [
        [r.msg_id, r.date.isoformat(), r.tournament, r.place,
         r.raw_name, r.player, r.stars, r.knockouts] for r in ordered]


def values_to_history(values: list[list]) -> list[HistoryRow]:
    rows = []
    for i, v in enumerate(values, start=1):
        v = list(v) + [""] * (8 - len(v))
        if v[0] in ("", "msg_id"):
            continue
        try:
            rows.append(HistoryRow(
                msg_id=int(v[0]), date=datetime.date.fromisoformat(str(v[1])),
                tournament=str(v[2]), place=int(v[3]), raw_name=str(v[4]),
                player=str(v[5]), stars=int(v[6] or 0), knockouts=int(v[7] or 0)))
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"History row {i} cannot be parsed: {v!r} — fix this row in the Sheet"
            ) from exc
    return rows


def overall_to_values(board: list[dict]) -> list[list]:
    return [BOARD_HEADER] + [
        [b["rank"], b["player"], b["stars"], b["knockouts"], b["tournaments"]]
        for b in board]


def monthly_to_values(months: list[tuple[str, list[dict]]]) -> list[list]:
    values: list[list] = []
    for month, board in months:
        values.append([month])
        values.extend(overall_to_values(board))
        values.append([])
    return values


def _credentials() -> dict:
    raw = os.environ.get("GOOGLE_CREDENTIALS")
    if raw:
        return json.loads(raw)
    path = os.environ.get("GOOGLE_CREDENTIALS_FILE", "service_account.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Sheet:
    def __init__(self):
        gc = gspread.service_account_from_dict(_credentials())
        self._sh = gc.open_by_key(os.environ["SHEET_ID"])
        existing = {ws.title for ws in self._sh.worksheets()}
        for title, header in TAB_ROWS.items():
            if title not in existing:
                ws = self._sh.add_worksheet(title=title, rows=1000, cols=10)
                if header:
                    ws.update(values=[header], range_name="A1")

    def _ws(self, title: str):
        return self._sh.worksheet(title)

    def read_history(self) -> list[HistoryRow]:
        return values_to_history(self._ws("History").get_all_values())

    def read_aliases(self) -> dict[str, str]:
        aliases = {}
        for v in self._ws("Aliases").get_all_values():
            if len(v) >= 2 and v[0] and v[1] and v[0] != "written as":
                aliases[v[0]] = v[1]
        return aliases

    def read_review_keys(self) -> set[tuple[str, str]]:
        keys = set()
        for v in self._ws("Needs review").get_all_values():
            if len(v) >= 3 and v[1] and v[1] != "type":
                keys.add((v[1], v[2]))
        return keys

    def _write_all(self, ws, values: list[list]) -> None:
        # resize (grow or truncate) then overwrite in place — never clear()
        # first, so a crash mid-write can't leave the sheet empty.
        ws.resize(rows=max(len(values), 1))
        ws.update(values=values, range_name="A1")

    def write_history(self, rows: list[HistoryRow]) -> None:
        self._write_all(self._ws("History"), history_to_values(rows))

    def write_leaderboards(self, overall_board, months) -> None:
        self._write_all(self._ws("Overall"), overall_to_values(overall_board))
        values = monthly_to_values(months)
        if not values:
            values = [[""]]
        self._write_all(self._ws("Monthly"), values)

    def append_review(self, items: list[tuple[str, str]]) -> None:
        if items:
            today = datetime.date.today().isoformat()
            self._ws("Needs review").append_rows(
                [[today, t, d] for t, d in items])

    def read_automerged_keys(self) -> set[str]:
        keys = set()
        for v in self._ws("Auto-merged").get_all_values():
            if len(v) >= 2 and v[1] and v[1] != "details":
                keys.add(v[1])
        return keys

    def append_automerged(self, items: list[str]) -> None:
        if items:
            today = datetime.date.today().isoformat()
            self._ws("Auto-merged").append_rows([[today, d] for d in items])
