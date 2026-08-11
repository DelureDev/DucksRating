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
        self.overall = None
        self.months = None

    def read_history(self):
        return list(self.history)

    def read_aliases(self):
        return dict(self.aliases)

    def read_review_keys(self):
        return {(t, d) for t, d in self.review_rows}

    def write_history(self, rows):
        self.history = list(rows)

    def write_leaderboards(self, overall_board, months):
        self.overall = overall_board
        self.months = months

    def append_review(self, items):
        self.review_rows.extend(items)


BROKEN = "ИТОГИ BROKEN CUP\n🥇 Кто-то — 500"  # no star emoji


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
    assert ("unparsed_post", "msg 12: unparseable result line: '🥇 Кто-то — 500'"
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


def test_typo_across_posts_auto_merges():
    typo_post = RawPost(13, DATE, "ИТОГИ NEXT CUP\n🥇 Delurking — ⭐️ 40")
    sheet = FakeSheet()
    run(sheet, make_fetcher(POSTS + [typo_post]))
    typo_rows = [r for r in sheet.history if r.raw_name == "Delurking"]
    assert typo_rows[0].player == "Delureking"
    assert any(t == "auto_merged" for t, _ in sheet.review_rows)
