from collections import defaultdict

from .models import HistoryRow


def _effective_stars(r: HistoryRow, by_msg: dict[int, dict[str, HistoryRow]]) -> int:
    """Stars credited to this row: a stack transferrer gets the same stars as
    the player who received the stack (club rule), following chains to the
    final holder. A broken chain (unknown target, or a cycle) falls back to
    the row's own printed stars. Knockouts are never transferred."""
    seen = {r.player}
    cur = r
    while cur.transfer_player:
        nxt = by_msg[r.msg_id].get(cur.transfer_player)
        if nxt is None or nxt.player in seen:
            return r.stars
        seen.add(nxt.player)
        cur = nxt
    return cur.stars


def _aggregate(rows: list[HistoryRow]) -> list[dict]:
    by_msg: dict[int, dict[str, HistoryRow]] = {}
    for r in rows:
        by_msg.setdefault(r.msg_id, {}).setdefault(r.player, r)
    agg: dict[str, dict] = {}
    for r in rows:
        a = agg.setdefault(r.player, {"player": r.player, "stars": 0,
                                      "knockouts": 0, "tournaments": 0})
        a["stars"] += _effective_stars(r, by_msg)
        a["knockouts"] += r.knockouts
        a["tournaments"] += 1
    ordered = sorted(agg.values(),
                     key=lambda a: (-a["stars"], -a["knockouts"], a["player"].lower()))
    ranked, prev_stars, prev_rank = [], None, 0
    for i, a in enumerate(ordered, start=1):
        rank = prev_rank if a["stars"] == prev_stars else i
        ranked.append({**a, "rank": rank})
        prev_stars, prev_rank = a["stars"], rank
    return ranked


def overall(rows: list[HistoryRow]) -> list[dict]:
    return _aggregate(rows)


def monthly(rows: list[HistoryRow]) -> list[tuple[str, list[dict]]]:
    by_month: dict[str, list[HistoryRow]] = defaultdict(list)
    for r in rows:
        by_month[r.date.strftime("%Y-%m")].append(r)
    return [(m, _aggregate(by_month[m])) for m in sorted(by_month, reverse=True)]
