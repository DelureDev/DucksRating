import datetime

from src.main import run
from src.models import RawPost
from tests.sample_posts import SPY_007, ANNOUNCEMENT

DATE = datetime.date(2026, 8, 10)


class FakeSheet:
    def __init__(self, aliases=None):
        self.history = []
        self.aliases = aliases or {}
        self.review_rows = []
        self.automerged = []
        self.overall = None
        self.months = None

    def read_history(self):
        return list(self.history)

    def read_aliases(self):
        return dict(self.aliases)

    def read_review_keys(self):
        return {(t, d) for t, d in self.review_rows}

    def read_automerged_keys(self):
        return set(self.automerged)

    def write_history(self, rows):
        self.history = list(rows)

    def write_leaderboards(self, overall_board, months):
        self.overall = overall_board
        self.months = months

    def append_review(self, items):
        self.review_rows.extend(items)

    def append_automerged(self, items):
        self.automerged.extend(items)


BROKEN = "ИТОГИ BROKEN CUP\n🥇 Кто-то — ⭐️"  # star but no number


def make_fetcher(posts):
    def fetch_posts(known_ids):
        return [p for p in posts if p.msg_id not in known_ids]
    return fetch_posts


POSTS = [
    RawPost(10, DATE, ANNOUNCEMENT),            # ignored
    RawPost(11, DATE, SPY_007),                 # 11 rows
    RawPost(12, DATE, BROKEN),                  # -> review
]


def test_run_writes_history_and_boards():
    sheet = FakeSheet()
    summary = run(sheet, make_fetcher(POSTS))
    assert summary["new_rows"] == 11
    assert len(sheet.history) == 11
    assert all(r.player for r in sheet.history)          # canonical filled
    assert sheet.overall[0]["player"] == "Демид"         # 2080 stars tops
    assert sheet.months[0][0] == "2026-08"
    assert ("unparsed_post", "msg 12: unparseable result line: '🥇 Кто-то — ⭐️'"
            ) in sheet.review_rows


def test_run_is_idempotent():
    sheet = FakeSheet()
    run(sheet, make_fetcher(POSTS))
    summary2 = run(sheet, make_fetcher(POSTS))
    assert summary2["new_rows"] == 0
    assert len(sheet.history) == 11
    unparsed = [r for r in sheet.review_rows if r[0] == "unparsed_post"]
    assert len(unparsed) == 1                            # not re-added


def test_alias_edit_retroactively_renames():
    sheet = FakeSheet()
    run(sheet, make_fetcher(POSTS))
    sheet.aliases = {"Пиханина": "Pihanina"}
    run(sheet, make_fetcher(POSTS))
    players = {r.raw_name: r.player for r in sheet.history}
    assert players["Пиханина"] == "Pihanina"


def test_duplicate_fetched_posts_do_not_double_count():
    sheet = FakeSheet()
    dup = POSTS + POSTS  # simulates a misbehaving server repeating pages
    summary = run(sheet, make_fetcher(dup))
    assert summary["new_rows"] == 11
    assert len(sheet.history) == 11


def test_typo_across_posts_auto_merges():
    typo_post = RawPost(13, DATE, "ИТОГИ NEXT CUP\n🥇 Delurking — ⭐️ 40")
    sheet = FakeSheet()
    run(sheet, make_fetcher(POSTS + [typo_post]))
    typo_rows = [r for r in sheet.history if r.raw_name == "Delurking"]
    assert typo_rows[0].player == "Delureking"
    # audit notes go to their own tab, never to the actionable review list
    assert any("Delurking" in d for d in sheet.automerged)
    assert not any(t == "auto_merged" for t, _ in sheet.review_rows)


def test_automerged_notes_deduped_across_runs():
    typo_post = RawPost(13, DATE, "ИТОГИ NEXT CUP\n🥇 Delurking — ⭐️ 40")
    sheet = FakeSheet()
    run(sheet, make_fetcher(POSTS + [typo_post]))
    run(sheet, make_fetcher(POSTS + [typo_post]))
    assert len(sheet.automerged) == 1


BROTHERS = ("ИТОГИ GOOD BROTHERS TIMES\n"
            "🥇 Kes — ⭐️ 1140\n"
            "2. Nasty (передал стек Kes) — ⭐️ 228\n"
            "3. Хи-хи — передала стек Nasty")


def test_run_resolves_transfers_and_credits_receiver_stars():
    sheet = FakeSheet()
    run(sheet, make_fetcher([RawPost(20, DATE, BROTHERS)]))
    by_raw = {r.raw_name: r for r in sheet.history}
    assert by_raw["Nasty"].transfer_player == "Kes"
    assert by_raw["Хи-хи"].transfer_player == "Nasty"
    board = {b["player"]: b["stars"] for b in sheet.overall}
    assert board["Nasty"] == 1140
    assert board["Хи-хи"] == 1140          # chain follows to the final holder


def test_run_resolves_transfer_target_via_alias():
    post = RawPost(21, DATE, ("ИТОГИ GOOD BROTHERS TIMES\n"
                              "🥇 T.VI — ⭐️ 500\n"
                              "2. Gavr — передал стек T. VI"))
    sheet = FakeSheet(aliases={"T. VI": "T.VI", "T.VI": "T.VI"})
    run(sheet, make_fetcher([post]))
    by_raw = {r.raw_name: r for r in sheet.history}
    assert by_raw["Gavr"].transfer_player == "T.VI"
    board = {b["player"]: b["stars"] for b in sheet.overall}
    assert board["Gavr"] == 500


def test_run_flags_missing_transfer_target():
    post = RawPost(22, DATE, ("ИТОГИ GOOD BROTHERS TIMES\n"
                              "🥇 A — ⭐️ 100\n"
                              "2. B — передал стек Ghost"))
    sheet = FakeSheet()
    run(sheet, make_fetcher([post]))
    assert any(t == "transfer_target" and "Ghost" in d
               for t, d in sheet.review_rows)


def test_full_fetch_walks_everything_but_respects_known(monkeypatch):
    from src import fetch, main

    calls = []

    def fake_walk(known_ids):
        calls.append(set(known_ids))
        return [RawPost(10, DATE, "a"), RawPost(11, DATE, "b"),
                RawPost(12, DATE, "c")]

    monkeypatch.setattr(fetch, "fetch_posts_until", fake_walk)
    posts = main.full_fetch({11})
    assert calls == [set()]                      # walked the whole channel
    assert [p.msg_id for p in posts] == [10, 12]  # known post filtered out
