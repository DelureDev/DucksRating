import dataclasses
import sys

from . import fetch, leaderboard, parse
from .models import HistoryRow
from .names import NameMatcher


def full_fetch(known_ids: set[int]) -> list:
    """Walk the entire channel, returning posts missing from History.

    The normal incremental fetch stops at the first already-known post, so it
    never revisits older ones. This walk lets quarantined posts re-enter after
    a parser fix or an admin edit; dedup in run() keeps it safe.
    """
    return [p for p in fetch.fetch_posts_until(set())
            if p.msg_id not in known_ids]


def run(sheet, fetch_posts=None) -> dict:
    fetch_posts = fetch_posts or fetch.fetch_posts_until
    history = sheet.read_history()
    aliases = sheet.read_aliases()
    seen_review = sheet.read_review_keys()
    seen_automerged = sheet.read_automerged_keys()

    posts = fetch_posts({r.msg_id for r in history})
    review: list[tuple[str, str]] = []
    new_rows: list[HistoryRow] = []
    for post in posts:
        if not parse.is_results_post(post.text):
            continue
        try:
            tr = parse.parse_post(post)
        except parse.PostParseError as e:
            review.append(("unparsed_post", str(e)))
            continue
        for line in tr.lines:
            new_rows.append(HistoryRow(
                msg_id=tr.msg_id, date=tr.date, tournament=tr.tournament,
                place=line.place, raw_name=line.raw_name, player="",
                stars=line.stars, knockouts=line.knockouts))

    existing = {(r.msg_id, r.raw_name) for r in history}
    seen = set(existing)
    added: list[HistoryRow] = []
    for r in new_rows:
        key = (r.msg_id, r.raw_name)
        if key in seen:
            continue  # already in History, or a duplicate within this batch
        seen.add(key)
        added.append(r)
    merged = sorted(history + added, key=lambda r: (r.msg_id, r.place))

    matcher = NameMatcher(aliases)
    canonical_rows: list[HistoryRow] = []
    automerged: list[str] = []
    for r in merged:
        res = matcher.resolve(r.raw_name)
        if res.kind == "auto_merged":
            automerged.append(f"«{r.raw_name}» → «{res.canonical}» "
                              f"(score {res.score:.0f})")
        elif res.kind == "new_review":
            review.append(("possible_match",
                           f"«{r.raw_name}» looks similar to «{res.similar_to}» "
                           f"(score {res.score:.0f}) — same player? "
                           f"If yes, add a row to the Aliases tab."))
        canonical_rows.append(dataclasses.replace(r, player=res.canonical))

    sheet.write_history(canonical_rows)
    sheet.write_leaderboards(leaderboard.overall(canonical_rows),
                             leaderboard.monthly(canonical_rows))
    fresh_review = []
    for item in review:
        if item not in seen_review and item not in fresh_review:
            fresh_review.append(item)
    sheet.append_review(fresh_review)
    fresh_automerged = []
    for note in automerged:
        if note not in seen_automerged and note not in fresh_automerged:
            fresh_automerged.append(note)
    sheet.append_automerged(fresh_automerged)

    return {"fetched_posts": len(posts), "new_rows": len(added),
            "review_items": len(fresh_review),
            "auto_merged": len(fresh_automerged)}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from .sheet import Sheet
    fetcher = full_fetch if "--full" in sys.argv[1:] else None
    summary = run(Sheet(), fetch_posts=fetcher)
    print(f"posts fetched: {summary['fetched_posts']}, "
          f"history rows added: {summary['new_rows']}, "
          f"new review items: {summary['review_items']}, "
          f"auto-merge notes: {summary['auto_merged']}")


if __name__ == "__main__":
    main()
