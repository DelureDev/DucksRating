import datetime
import pathlib

from src import fetch, parse
from src.models import RawPost
from src.parse import parse_post

FIXTURE = (pathlib.Path(__file__).parent / "fixtures" / "channel_page.html"
           ).read_text(encoding="utf-8")


def test_parse_page_extracts_posts():
    posts = fetch.parse_page(FIXTURE)
    assert [p.msg_id for p in posts] == [101, 103]  # photo-only 102 skipped
    assert posts[0].date == datetime.date(2026, 8, 10)
    lines = posts[0].text.splitlines()
    assert lines[0] == "ИТОГИ TEST CUP"
    assert lines[1] == "ТОП-2 игроков вечера"


def test_parse_page_output_feeds_parser():
    posts = fetch.parse_page(FIXTURE)
    tr = parse_post(posts[0])
    assert [(l.raw_name, l.stars, l.spades) for l in tr.lines] == [
        ("Демид", 100, 2), ("Vii", 50, 0)]


def _fake_pages(monkeypatch, pages):
    """pages: dict url-suffix -> html. '' is the first page."""
    calls = []

    def fake_get(url):
        suffix = url.split("DUCKS_POKER")[-1]
        calls.append(suffix)
        return pages.get(suffix, "<html></html>")

    monkeypatch.setattr(fetch, "_get", fake_get)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    return calls


def _page(*msgs):
    body = "".join(
        f'<div class="tgme_widget_message" data-post="DUCKS_POKER/{i}">'
        f'<div class="tgme_widget_message_text">post {i}</div>'
        f'<time datetime="2026-08-01T00:00:00+00:00"></time></div>'
        for i in msgs)
    return f"<html><body>{body}</body></html>"


def test_fetch_stops_at_known_ids(monkeypatch):
    _fake_pages(monkeypatch, {"": _page(103, 104)})
    posts = fetch.fetch_posts_until(known_ids={103})
    assert [p.msg_id for p in posts] == [104]  # stops, does not request ?before


def test_fetch_backfills_to_channel_start(monkeypatch):
    calls = _fake_pages(monkeypatch, {
        "": _page(103, 104),
        "?before=103": _page(101, 102),
        "?before=101": "<html></html>",
    })
    posts = fetch.fetch_posts_until(known_ids=set())
    assert [p.msg_id for p in posts] == [101, 102, 103, 104]
    assert calls == ["", "?before=103", "?before=101"]


def test_photo_only_page_does_not_stop_backfill(monkeypatch):
    photo_page = ('<html><body><div class="tgme_widget_message" data-post="DUCKS_POKER/102">'
                  '<time datetime="2026-08-01T00:00:00+00:00"></time></div></body></html>')
    calls = _fake_pages(monkeypatch, {
        "": _page(103, 104),
        "?before=103": photo_page,
        "?before=102": _page(101),
        "?before=101": "<html></html>",
    })
    posts = fetch.fetch_posts_until(known_ids=set())
    assert [p.msg_id for p in posts] == [101, 103, 104]
    assert calls == ["", "?before=103", "?before=102", "?before=101"]


def test_live_snapshot_smoke():
    html = (pathlib.Path(__file__).parent / "fixtures" / "live_snapshot.html"
            ).read_text(encoding="utf-8")
    posts = fetch.parse_page(html)
    assert len(posts) >= 1          # structure still recognized
    assert all(p.msg_id > 0 for p in posts)
    assert all(p.text.strip() for p in posts)


def test_live_snapshot_results_posts_all_parse():
    html = (pathlib.Path(__file__).parent / "fixtures" / "live_snapshot.html"
            ).read_text(encoding="utf-8")
    results = [p for p in fetch.parse_page(html) if parse.is_results_post(p.text)]
    assert len(results) >= 3
    for post in results:
        tr = parse.parse_post(post)   # must not raise
        assert tr.lines
