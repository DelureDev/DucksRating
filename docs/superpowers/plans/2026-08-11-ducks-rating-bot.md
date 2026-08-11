# DUCKS Poker Rating Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Python bot that parses «ИТОГИ» tournament-result posts from the public Telegram channel t.me/DUCKS_POKER and maintains a Google Sheet with full points history plus Monthly and Overall leaderboards, run daily by GitHub Actions.

**Architecture:** Four stages — fetch (scrape `t.me/s/DUCKS_POKER` web preview) → parse (regex over post text) → match names (normalization + aliases + fuzzy) → write (Google Sheets is the only database). Every run is idempotent: dedup by `(msg_id, raw_name)`, the `player` column and both leaderboard tabs are recomputed from History on every run.

**Tech Stack:** Python 3.12, requests, beautifulsoup4, gspread, rapidfuzz, pytest. GitHub Actions cron.

**Spec:** `docs/superpowers/specs/2026-08-11-ducks-rating-bot-design.md` — read it before starting.

## Global Constraints

- Python 3.12. Dependencies ONLY: `requests`, `beautifulsoup4`, `gspread`, `rapidfuzz`, `pytest`.
- Tests never touch the network. Fixtures are committed files / inline strings.
- Fuzzy thresholds: auto-merge at score ≥ 90, review suggestion at 70–89, silent new player < 70.
- Channel: `DUCKS_POKER`. Cron: `0 8 * * *` UTC. Env vars: `GOOGLE_CREDENTIALS` (JSON string) or `GOOGLE_CREDENTIALS_FILE` (path, local runs), `SHEET_ID`.
- All file I/O uses `encoding="utf-8"` explicitly (Windows default codepage is not UTF-8).
- Source files contain Cyrillic and emoji — always save as UTF-8.
- The script must never write partial/guessed data: parse failures go to the "Needs review" tab, fetch/Sheets failures exit non-zero having written nothing.
- Run tests with `python -m pytest -v` (works on Windows PowerShell and Linux CI).
- Commit after every task; messages in imperative mood, e.g. `feat: add post parser`.

---

### Task 1: Scaffolding, models, and the post parser

**Files:**
- Create: `requirements.txt`, `.gitignore`, `src/__init__.py`, `src/models.py`, `src/parse.py`
- Create: `tests/__init__.py`, `tests/sample_posts.py`, `tests/test_parse.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `src/models.py`: dataclasses `RawPost(msg_id: int, date: datetime.date, text: str)`, `ResultLine(place: int, raw_name: str, stars: int, spades: int)`, `TournamentResult(msg_id: int, date: datetime.date, tournament: str, lines: tuple[ResultLine, ...])`, `HistoryRow(msg_id: int, date: datetime.date, tournament: str, place: int, raw_name: str, player: str, stars: int, spades: int)` — all `@dataclass(frozen=True)`.
  - `src/parse.py`: `is_results_post(text: str) -> bool`, `parse_post(post: RawPost) -> TournamentResult`, exception `PostParseError(Exception)` with attributes `msg_id: int` and `reason: str`, `str(e)` formatted as `"msg {msg_id}: {reason}"`.

- [ ] **Step 1: Create scaffolding files**

`requirements.txt`:
```
requests>=2.31
beautifulsoup4>=4.12
gspread>=6.0
rapidfuzz>=3.6
pytest>=8.0
```

`.gitignore`:
```
__pycache__/
.pytest_cache/
.venv/
venv/
service_account.json
.env
```

`src/__init__.py` and `tests/__init__.py`: empty files.

`src/models.py`:
```python
from dataclasses import dataclass
import datetime


@dataclass(frozen=True)
class RawPost:
    msg_id: int
    date: datetime.date
    text: str


@dataclass(frozen=True)
class ResultLine:
    place: int
    raw_name: str
    stars: int
    spades: int


@dataclass(frozen=True)
class TournamentResult:
    msg_id: int
    date: datetime.date
    tournament: str
    lines: tuple[ResultLine, ...]


@dataclass(frozen=True)
class HistoryRow:
    msg_id: int
    date: datetime.date
    tournament: str
    place: int
    raw_name: str
    player: str
    stars: int
    spades: int
```

- [ ] **Step 2: Create shared sample post fixture**

`tests/sample_posts.py` (real post from the channel, 2026-08-10 — keep verbatim):
```python
SPY_007 = """ИТОГИ SPY 007 TOURNAMENT

ТОП-11 игроков вечера

🥇 Демид — ⭐️ 2080 | 23 ♠️
🥈 Пиханина — ⭐️ 1570 | 19 ♠️
🥉 Rinatovna — ⭐️ 1034 | 12 ♠️
4. APOM4T_XPEHA — ⭐️ 610 | 6 ♠️
5. Vii — ⭐️ 248
6. Гавр — ⭐️ 1536 | 27 ♠️
7. Rena — ⭐️ 1905 | 35 ♠️
8. Delureking — ⭐️ 124
9. Zhenyaluchshiy — ⭐️ 93
10. Chivas — ⭐️ 450 | 9 ♠️
11. Sailor Moon — ⭐️ 300 | 6 ♠️"""

ANNOUNCEMENT = """BIG FREE-ROLL BOUNTY — ОХОТА НАЧИНАЕТСЯ СЕГОДНЯ! 🔥
ПЕРВЫЙ ВХОД СВОБОДНЫЙ!
START стэк 100.000
Сбор 19.00"""
```

- [ ] **Step 3: Write the failing parser tests**

`tests/test_parse.py`:
```python
import datetime
import pytest

from src.models import RawPost
from src.parse import is_results_post, parse_post, PostParseError
from tests.sample_posts import SPY_007, ANNOUNCEMENT

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
    assert (first.place, first.raw_name, first.stars, first.spades) == (1, "Демид", 2080, 23)
    vii = tr.lines[4]
    assert (vii.place, vii.raw_name, vii.stars, vii.spades) == (5, "Vii", 248, 0)
    last = tr.lines[10]
    assert (last.place, last.raw_name, last.stars, last.spades) == (11, "Sailor Moon", 300, 6)


def test_parse_format_variants():
    text = ("ИТОГИ MINI\n"
            "ТОП-3 игроков вечера\n"
            "🥇 Ali-Baba — ⭐️ 1 000 | 2 ♠️\n"   # hyphen in name, space in number
            "2) Vii - ⭐ 50\n"                    # paren place, plain hyphen, no VS16 star
            "3. Sailor Moon – ⭐️ 25")            # en dash
    tr = parse_post(make_post(text))
    assert [(l.place, l.raw_name, l.stars, l.spades) for l in tr.lines] == [
        (1, "Ali-Baba", 1000, 2), (2, "Vii", 50, 0), (3, "Sailor Moon", 25, 0)]


def test_broken_result_line_rejects_whole_post():
    text = SPY_007.replace("8. Delureking — ⭐️ 124", "8. Delureking — 124")  # star missing
    with pytest.raises(PostParseError) as ei:
        parse_post(make_post(text, msg_id=7))
    assert ei.value.msg_id == 7
    assert "8. Delureking" in ei.value.reason


def test_top_n_count_mismatch_rejects():
    text = SPY_007.replace("5. Vii — ⭐️ 248\n", "")  # says ТОП-11, has 10 lines
    with pytest.raises(PostParseError) as ei:
        parse_post(make_post(text))
    assert "11" in ei.value.reason


def test_non_sequential_places_reject():
    text = ("ИТОГИ X\n🥇 A — ⭐️ 10\n🥉 B — ⭐️ 5")  # place 2 missing, no ТОП-N line
    with pytest.raises(PostParseError):
        parse_post(make_post(text))


def test_no_result_lines_rejects():
    with pytest.raises(PostParseError):
        parse_post(make_post("ИТОГИ X\nбыло весело!"))


def test_chatter_lines_ignored():
    text = "ИТОГИ X\nТОП-1 игроков вечера\n🥇 A — ⭐️ 10\nСбор завтра в 19.00!"
    tr = parse_post(make_post(text))
    assert len(tr.lines) == 1
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `python -m pytest tests/test_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.parse'` (install deps first: `pip install -r requirements.txt`).

- [ ] **Step 5: Implement the parser**

`src/parse.py`:
```python
import re

from .models import RawPost, ResultLine, TournamentResult

RESULTS_MARKER = "ИТОГИ"
_MEDALS = {"\U0001F947": 1, "\U0001F948": 2, "\U0001F949": 3}

# Full result line: place marker, name, dash, stars, optional "| N ♠"
_LINE_RE = re.compile(
    r"^\s*(?:(?P<medal>[\U0001F947-\U0001F949])|(?P<num>\d{1,3})[.)])\s+"
    r"(?P<name>.+?)\s*[—–-]\s*"
    r"⭐️?\s*(?P<stars>\d[\d\s.,]*?)\s*"
    r"(?:\|\s*(?P<spades>\d+)\s*♠️?)?\s*$"
)
# Looser marker: a line that CLAIMS to be a result line ("🥇 ..." / "8. ...")
_MARKER_RE = re.compile(r"^\s*(?:[\U0001F947-\U0001F949]|\d{1,3}[.)]\s)")
_TOP_N_RE = re.compile(r"ТОП[-\s]?(\d+)", re.IGNORECASE)


class PostParseError(Exception):
    def __init__(self, msg_id: int, reason: str):
        self.msg_id = msg_id
        self.reason = reason
        super().__init__(f"msg {msg_id}: {reason}")


def _find_header(text: str) -> tuple[int, str] | None:
    """Index and content of the «ИТОГИ» line, if it opens the post."""
    for i, line in enumerate(text.splitlines()):
        if RESULTS_MARKER in line.upper():
            return i, line
        if line.strip():
            return None  # first non-empty line decides
    return None


def is_results_post(text: str) -> bool:
    return _find_header(text) is not None


def _digits(s: str) -> int:
    return int(re.sub(r"\D", "", s))


def parse_post(post: RawPost) -> TournamentResult:
    found = _find_header(post.text)
    if found is None:
        raise PostParseError(post.msg_id, "not a results post")
    header_idx, header = found
    idx = header.upper().index(RESULTS_MARKER)
    # strip set includes U+FE0F (invisible emoji variation selector)
    tournament = header[idx + len(RESULTS_MARKER):].strip(" :!️⭐♠🔥—–-")

    lines: list[ResultLine] = []
    for i, line in enumerate(post.text.splitlines()):
        if i == header_idx or not line.strip():
            continue
        m = _LINE_RE.match(line)
        if m:
            place = _MEDALS[m["medal"]] if m["medal"] else int(m["num"])
            lines.append(ResultLine(
                place=place,
                raw_name=m["name"].strip(),
                stars=_digits(m["stars"]),
                spades=int(m["spades"]) if m["spades"] else 0,
            ))
        elif _MARKER_RE.match(line):
            raise PostParseError(post.msg_id, f"unparseable result line: {line.strip()!r}")

    if not lines:
        raise PostParseError(post.msg_id, "no result lines found")

    top_n = _TOP_N_RE.search(post.text)
    if top_n and int(top_n.group(1)) != len(lines):
        raise PostParseError(
            post.msg_id,
            f"header says ТОП-{top_n.group(1)} but {len(lines)} lines parsed")

    places = [l.place for l in lines]
    if places != list(range(1, len(lines) + 1)):
        raise PostParseError(post.msg_id, f"places not sequential: {places}")

    return TournamentResult(post.msg_id, post.date, tournament, tuple(lines))
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_parse.py -v`
Expected: all PASS. If `test_parse_format_variants` fails on `1 000` → check `_digits`; if medal lines fail → the regex must use raw string with the exact `\U0001F947` escapes.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .gitignore src tests
git commit -m "feat: add models and ИТОГИ post parser"
```

---

### Task 2: Name normalization and matching

**Files:**
- Create: `src/names.py`
- Test: `tests/test_names.py`

**Interfaces:**
- Consumes: nothing from other tasks (pure module).
- Produces:
  - `normalize(name: str) -> str` — comparison key (lowercase, collapsed spaces, ё→е, Cyrillic homoglyphs mapped to Latin).
  - `Resolution(canonical: str, kind: str, similar_to: str = "", score: float = 0.0)` frozen dataclass; `kind` ∈ `"exact" | "alias" | "auto_merged" | "new" | "new_review"`.
  - `NameMatcher(aliases: dict[str, str])` with method `resolve(raw_name: str) -> Resolution`. Stateful: first-seen spelling becomes canonical; feed rows chronologically.
  - Constants `AUTO_MERGE_SCORE = 90`, `REVIEW_SCORE = 70`.

- [ ] **Step 1: Write the failing tests**

`tests/test_names.py`:
```python
from src.names import normalize, NameMatcher


def test_normalize_case_and_spaces():
    assert normalize("  DelureKing ") == normalize("delureking")
    assert normalize("Sailor  Moon") == normalize("sailor moon")


def test_normalize_homoglyphs():
    # Real case: admin typed APOM4T_XPEHA in Latin lookalikes of Cyrillic АРОМ4Т_ХРЕНА
    assert normalize("APOM4T_XPEHA") == normalize("АРОМ4Т_ХРЕНА")
    assert normalize("Ёлка") == normalize("елка")


def test_exact_after_normalization_merges():
    m = NameMatcher(aliases={})
    assert m.resolve("Delureking").kind == "new"
    r = m.resolve("DelureKing")
    assert r.kind == "exact"
    assert r.canonical == "Delureking"  # first-seen spelling wins


def test_alias_wins_over_everything():
    m = NameMatcher(aliases={"Pihanina": "Пиханина"})
    r = m.resolve("Pihanina")
    assert r.kind == "alias"
    assert r.canonical == "Пиханина"
    # canonical from alias is now a known player
    assert m.resolve("Пиханина").kind == "exact"


def test_typo_auto_merges_at_90():
    m = NameMatcher(aliases={})
    m.resolve("Delureking")
    r = m.resolve("Delurking")  # one letter dropped -> score ≥ 90
    assert r.kind == "auto_merged"
    assert r.canonical == "Delureking"
    assert r.score >= 90


def test_borderline_becomes_new_with_review():
    m = NameMatcher(aliases={})
    m.resolve("Delureking")
    r = m.resolve("Delurek")  # ~82 similarity -> review, NOT merged
    assert r.kind == "new_review"
    assert r.canonical == "Delurek"
    assert r.similar_to == "Delureking"
    assert 70 <= r.score < 90


def test_distinct_name_is_silently_new():
    m = NameMatcher(aliases={})
    m.resolve("Демид")
    r = m.resolve("Гавр")
    assert r.kind == "new"
    assert r.canonical == "Гавр"


def test_resolution_is_stable_within_run():
    m = NameMatcher(aliases={})
    m.resolve("Delureking")
    assert m.resolve("Delurking").canonical == "Delureking"
    assert m.resolve("Delurking").canonical == "Delureking"  # second time too
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_names.py -v`
Expected: FAIL — `No module named 'src.names'`.

- [ ] **Step 3: Implement**

`src/names.py`:
```python
from dataclasses import dataclass

from rapidfuzz import fuzz

AUTO_MERGE_SCORE = 90
REVIEW_SCORE = 70

# lowercase Cyrillic -> Latin lookalikes (comparison only, never for display)
_HOMOGLYPHS = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x",
    "у": "y", "к": "k", "м": "m", "т": "t", "н": "h", "в": "b",
})


def normalize(name: str) -> str:
    n = " ".join(name.lower().split())
    n = n.replace("ё", "е")
    return n.translate(_HOMOGLYPHS)


@dataclass(frozen=True)
class Resolution:
    canonical: str
    kind: str
    similar_to: str = ""
    score: float = 0.0


class NameMatcher:
    def __init__(self, aliases: dict[str, str]):
        self._aliases = {normalize(k): v for k, v in aliases.items()}
        self._players: dict[str, str] = {}  # normalized -> canonical display

    def resolve(self, raw_name: str) -> Resolution:
        norm = normalize(raw_name)
        if norm in self._aliases:
            canonical = self._aliases[norm]
            self._players.setdefault(normalize(canonical), canonical)
            return Resolution(canonical, "alias")
        if norm in self._players:
            return Resolution(self._players[norm], "exact")

        best_score, best_player = 0.0, ""
        for pnorm, canonical in self._players.items():
            score = fuzz.ratio(norm, pnorm)
            if score > best_score:
                best_score, best_player = score, canonical

        if best_score >= AUTO_MERGE_SCORE:
            return Resolution(best_player, "auto_merged",
                              similar_to=best_player, score=best_score)
        self._players[norm] = raw_name
        if best_score >= REVIEW_SCORE:
            return Resolution(raw_name, "new_review",
                              similar_to=best_player, score=best_score)
        return Resolution(raw_name, "new")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_names.py -v`
Expected: all PASS. If `test_typo_auto_merges_at_90` or `test_borderline_becomes_new_with_review` fails, print the actual `fuzz.ratio` values and adjust the TEST'S example words (not the thresholds) so they land in the intended bands — thresholds 90/70 are fixed by the spec.

- [ ] **Step 5: Commit**

```bash
git add src/names.py tests/test_names.py
git commit -m "feat: add name normalization and fuzzy matching"
```

---

### Task 3: Leaderboard computation

**Files:**
- Create: `src/leaderboard.py`
- Test: `tests/test_leaderboard.py`

**Interfaces:**
- Consumes: `HistoryRow` from `src/models.py`.
- Produces:
  - `overall(rows: list[HistoryRow]) -> list[dict]` — dicts with keys `rank, player, stars, spades, tournaments`, sorted by stars desc; ties share a rank (competition ranking: 1, 1, 3).
  - `monthly(rows: list[HistoryRow]) -> list[tuple[str, list[dict]]]` — `("YYYY-MM", same-shape dicts)`, newest month first.

- [ ] **Step 1: Write the failing tests**

`tests/test_leaderboard.py`:
```python
import datetime

from src.models import HistoryRow
from src.leaderboard import overall, monthly


def row(player, stars, spades=0, month=8, day=1, msg_id=1):
    return HistoryRow(msg_id=msg_id, date=datetime.date(2026, month, day),
                      tournament="T", place=1, raw_name=player,
                      player=player, stars=stars, spades=spades)


def test_overall_totals_and_order():
    rows = [row("A", 100, 2), row("B", 300, 1), row("A", 50, 3)]
    board = overall(rows)
    assert [b["player"] for b in board] == ["B", "A"]
    a = board[1]
    assert (a["stars"], a["spades"], a["tournaments"]) == (150, 5, 2)


def test_overall_tie_ranks_skip():
    board = overall([row("A", 100), row("B", 100), row("C", 50)])
    assert [b["rank"] for b in board] == [1, 1, 3]


def test_monthly_groups_and_orders_desc():
    rows = [row("A", 10, month=7), row("A", 20, month=8), row("B", 5, month=8)]
    months = monthly(rows)
    assert [m for m, _ in months] == ["2026-08", "2026-07"]
    aug = dict((b["player"], b["stars"]) for b in months[0][1])
    assert aug == {"A": 20, "B": 5}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_leaderboard.py -v`
Expected: FAIL — `No module named 'src.leaderboard'`.

- [ ] **Step 3: Implement**

`src/leaderboard.py`:
```python
from collections import defaultdict

from .models import HistoryRow


def _aggregate(rows: list[HistoryRow]) -> list[dict]:
    agg: dict[str, dict] = {}
    for r in rows:
        a = agg.setdefault(r.player, {"player": r.player, "stars": 0,
                                      "spades": 0, "tournaments": 0})
        a["stars"] += r.stars
        a["spades"] += r.spades
        a["tournaments"] += 1
    ordered = sorted(agg.values(),
                     key=lambda a: (-a["stars"], -a["spades"], a["player"].lower()))
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_leaderboard.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/leaderboard.py tests/test_leaderboard.py
git commit -m "feat: add overall and monthly leaderboard computation"
```

---

### Task 4: Telegram web-preview fetcher

**Files:**
- Create: `src/config.py`, `src/fetch.py`, `tests/fixtures/channel_page.html`
- Test: `tests/test_fetch.py`

**Interfaces:**
- Consumes: `RawPost` from `src/models.py`.
- Produces:
  - `src/config.py`: `CHANNEL = "DUCKS_POKER"`, `USER_AGENT` (a normal desktop-browser string), `FETCH_DELAY_SECONDS = 1.5`.
  - `src/fetch.py`: `parse_page(html: str) -> list[RawPost]` (pure), `fetch_posts_until(known_ids: set[int]) -> list[RawPost]` (network; returns NEW posts sorted oldest→newest; with empty `known_ids` walks the whole channel = backfill), exception `FetchError(Exception)`.

- [ ] **Step 1: Create the handcrafted HTML fixture**

`tests/fixtures/channel_page.html` — mimics the real t.me/s structure: message divs with `data-post`, text with `<br>` line breaks and emoji wrapped in `<i class="emoji"><b>…</b></i>`, a `<time datetime>` element, plus one photo-only message (no text div) that must be skipped:

```html
<html><body>
<section class="tgme_channel_history">
<div class="tgme_widget_message" data-post="DUCKS_POKER/101">
  <div class="tgme_widget_message_text js-message_text" dir="auto">ИТОГИ TEST CUP<br/>ТОП-2 игроков вечера<br/><br/><i class="emoji"><b>🥇</b></i> Демид — <i class="emoji"><b>⭐️</b></i> 100 | 2 <i class="emoji"><b>♠️</b></i><br/><i class="emoji"><b>🥈</b></i> Vii — <i class="emoji"><b>⭐️</b></i> 50</div>
  <a class="tgme_widget_message_date" href="https://t.me/DUCKS_POKER/101"><time datetime="2026-08-10T08:00:00+00:00"></time></a>
</div>
<div class="tgme_widget_message" data-post="DUCKS_POKER/102">
  <a class="tgme_widget_message_date" href="https://t.me/DUCKS_POKER/102"><time datetime="2026-08-10T09:00:00+00:00"></time></a>
</div>
<div class="tgme_widget_message" data-post="DUCKS_POKER/103">
  <div class="tgme_widget_message_text js-message_text" dir="auto">Сегодня играем снова!</div>
  <a class="tgme_widget_message_date" href="https://t.me/DUCKS_POKER/103"><time datetime="2026-08-11T10:00:00+00:00"></time></a>
</div>
</section>
</body></html>
```

- [ ] **Step 2: Write the failing tests**

`tests/test_fetch.py`:
```python
import datetime
import pathlib

from src import fetch
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_fetch.py -v`
Expected: FAIL — `No module named 'src.fetch'`.

- [ ] **Step 4: Implement**

`src/config.py`:
```python
CHANNEL = "DUCKS_POKER"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/126.0.0.0 Safari/537.36")
FETCH_DELAY_SECONDS = 1.5
```

`src/fetch.py`:
```python
import datetime
import time

import requests
from bs4 import BeautifulSoup

from .config import CHANNEL, FETCH_DELAY_SECONDS, USER_AGENT
from .models import RawPost

BASE_URL = f"https://t.me/s/{CHANNEL}"


class FetchError(Exception):
    pass


def _get(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    if resp.status_code != 200:
        raise FetchError(f"GET {url} -> HTTP {resp.status_code}")
    return resp.text


def parse_page(html: str) -> list[RawPost]:
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        text_div = msg.select_one("div.tgme_widget_message_text")
        time_el = msg.select_one("time[datetime]")
        if text_div is None or time_el is None:
            continue  # photo-only or service message
        for br in text_div.find_all("br"):
            br.replace_with("\n")
        posts.append(RawPost(
            msg_id=int(msg["data-post"].split("/")[-1]),
            date=datetime.datetime.fromisoformat(time_el["datetime"]).date(),
            text=text_div.get_text(),
        ))
    return posts


def fetch_posts_until(known_ids: set[int]) -> list[RawPost]:
    new_posts: list[RawPost] = []
    before: int | None = None
    while True:
        url = BASE_URL if before is None else f"{BASE_URL}?before={before}"
        page = parse_page(_get(url))
        if not page:
            break
        fresh = [p for p in page if p.msg_id not in known_ids]
        new_posts.extend(fresh)
        oldest = min(p.msg_id for p in page)
        if len(fresh) < len(page):
            break  # reached already-known posts
        if before is not None and oldest >= before:
            break  # no progress safeguard
        before = oldest
        time.sleep(FETCH_DELAY_SECONDS)
    return sorted(new_posts, key=lambda p: p.msg_id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_fetch.py -v`
Expected: all PASS. Most likely failure: `posts[0].text` has extra newlines around emoji — that means `get_text("\n")` was used instead of the `<br>`-replacement approach; keep `get_text()` with no separator.

- [ ] **Step 6: Snapshot the real page as a smoke fixture**

Run (network, one-time):
```bash
python -c "import requests; from src.config import USER_AGENT; open('tests/fixtures/live_snapshot.html','wb').write(requests.get('https://t.me/s/DUCKS_POKER', headers={'User-Agent': USER_AGENT}, timeout=30).content)"
```

Append to `tests/test_fetch.py`:
```python
def test_live_snapshot_smoke():
    html = (pathlib.Path(__file__).parent / "fixtures" / "live_snapshot.html"
            ).read_text(encoding="utf-8")
    posts = fetch.parse_page(html)
    assert len(posts) >= 1          # structure still recognized
    assert all(p.msg_id > 0 for p in posts)
    assert all(p.text.strip() for p in posts)
```

Run: `python -m pytest tests/test_fetch.py -v` — all PASS. If `parse_page` returns `[]` here, the real page structure differs from the selectors — inspect `live_snapshot.html` and adjust selectors, then re-run ALL fetch tests.

- [ ] **Step 7: Commit**

```bash
git add src/config.py src/fetch.py tests/fixtures tests/test_fetch.py
git commit -m "feat: add t.me web preview fetcher with backfill pagination"
```

---

### Task 5: Google Sheets client

**Files:**
- Create: `src/sheet.py`
- Test: `tests/test_sheet.py`

**Interfaces:**
- Consumes: `HistoryRow` from `src/models.py`; leaderboard dict shapes from Task 3.
- Produces (pure helpers, unit-tested):
  - `HISTORY_HEADER = ["msg_id", "date", "tournament", "place", "raw_name", "player", "stars", "spades"]`
  - `history_to_values(rows: list[HistoryRow]) -> list[list]` — header + rows sorted newest-first (`-msg_id`, then `place`); dates as `YYYY-MM-DD` strings.
  - `values_to_history(values: list[list]) -> list[HistoryRow]` — inverse, skips header and blank rows.
  - `overall_to_values(board: list[dict]) -> list[list]` — header `["rank", "player", "stars ⭐️", "spades ♠️", "tournaments"]` + rows.
  - `monthly_to_values(months: list[tuple[str, list[dict]]]) -> list[list]` — per month: `["YYYY-MM"]` title row, header row, data rows, one blank row.
- Produces (network, NOT unit-tested — exercised in the first real run):
  - `class Sheet` with `__init__(self)` (reads env `GOOGLE_CREDENTIALS` / `GOOGLE_CREDENTIALS_FILE` + `SHEET_ID`, opens spreadsheet, creates missing tabs `History, Overall, Monthly, Aliases, Needs review`), `read_history() -> list[HistoryRow]`, `read_aliases() -> dict[str, str]`, `read_review_keys() -> set[tuple[str, str]]`, `write_history(rows: list[HistoryRow]) -> None`, `write_leaderboards(overall_board: list[dict], months: list[tuple[str, list[dict]]]) -> None`, `append_review(items: list[tuple[str, str]]) -> None` (items are `(type, details)`; caller pre-filters duplicates).

- [ ] **Step 1: Write the failing tests for the pure helpers**

`tests/test_sheet.py`:
```python
import datetime

from src.models import HistoryRow
from src.sheet import (HISTORY_HEADER, history_to_values, values_to_history,
                       overall_to_values, monthly_to_values)


def row(msg_id, place=1, player="A"):
    return HistoryRow(msg_id=msg_id, date=datetime.date(2026, 8, 10),
                      tournament="CUP", place=place, raw_name=player,
                      player=player, stars=100, spades=2)


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
    board = [{"rank": 1, "player": "B", "stars": 300, "spades": 1, "tournaments": 1}]
    values = overall_to_values(board)
    assert values == [["rank", "player", "stars ⭐️", "spades ♠️", "tournaments"],
                      [1, "B", 300, 1, 1]]


def test_monthly_to_values_sections():
    months = [("2026-08", [{"rank": 1, "player": "A", "stars": 20,
                            "spades": 0, "tournaments": 1}])]
    values = monthly_to_values(months)
    assert values[0] == ["2026-08"]
    assert values[1][0] == "rank"
    assert values[2] == [1, "A", 20, 0, 1]
    assert values[3] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sheet.py -v`
Expected: FAIL — `No module named 'src.sheet'`.

- [ ] **Step 3: Implement**

`src/sheet.py`:
```python
import datetime
import json
import os

import gspread

from .models import HistoryRow

HISTORY_HEADER = ["msg_id", "date", "tournament", "place",
                  "raw_name", "player", "stars", "spades"]
BOARD_HEADER = ["rank", "player", "stars ⭐️", "spades ♠️", "tournaments"]
REVIEW_HEADER = ["date added", "type", "details"]
ALIASES_HEADER = ["written as", "real player"]
TAB_ROWS = {"History": HISTORY_HEADER, "Overall": BOARD_HEADER,
            "Monthly": [], "Aliases": ALIASES_HEADER,
            "Needs review": REVIEW_HEADER}


def history_to_values(rows: list[HistoryRow]) -> list[list]:
    ordered = sorted(rows, key=lambda r: (-r.msg_id, r.place))
    return [HISTORY_HEADER] + [
        [r.msg_id, r.date.isoformat(), r.tournament, r.place,
         r.raw_name, r.player, r.stars, r.spades] for r in ordered]


def values_to_history(values: list[list]) -> list[HistoryRow]:
    rows = []
    for v in values:
        v = list(v) + [""] * (8 - len(v))
        if v[0] in ("", "msg_id"):
            continue
        rows.append(HistoryRow(
            msg_id=int(v[0]), date=datetime.date.fromisoformat(str(v[1])),
            tournament=str(v[2]), place=int(v[3]), raw_name=str(v[4]),
            player=str(v[5]), stars=int(v[6] or 0), spades=int(v[7] or 0)))
    return rows


def overall_to_values(board: list[dict]) -> list[list]:
    return [BOARD_HEADER] + [
        [b["rank"], b["player"], b["stars"], b["spades"], b["tournaments"]]
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

    def write_history(self, rows: list[HistoryRow]) -> None:
        ws = self._ws("History")
        ws.clear()
        ws.update(values=history_to_values(rows), range_name="A1")

    def write_leaderboards(self, overall_board, months) -> None:
        ws = self._ws("Overall")
        ws.clear()
        ws.update(values=overall_to_values(overall_board), range_name="A1")
        ws = self._ws("Monthly")
        ws.clear()
        values = monthly_to_values(months)
        if values:
            ws.update(values=values, range_name="A1")

    def append_review(self, items: list[tuple[str, str]]) -> None:
        if items:
            today = datetime.date.today().isoformat()
            self._ws("Needs review").append_rows(
                [[today, t, d] for t, d in items])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_sheet.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sheet.py tests/test_sheet.py
git commit -m "feat: add Google Sheets client and value serialization"
```

---

### Task 6: Orchestration (main)

**Files:**
- Create: `src/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: everything from Tasks 1–5 (exact names as declared in their Interfaces blocks).
- Produces:
  - `run(sheet, fetch_posts=None) -> dict` — orchestrates one full update; `fetch_posts` defaults to `fetch.fetch_posts_until`; returns summary `{"fetched_posts": int, "new_rows": int, "review_items": int}`. `sheet` is any object with the `Sheet` methods from Task 5 (duck-typed for tests).
  - `python -m src.main` entry point: builds real `Sheet()`, calls `run`, prints summary, exits non-zero on any exception.

- [ ] **Step 1: Write the failing end-to-end tests (with fakes)**

`tests/test_main.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_main.py -v`
Expected: FAIL — `No module named 'src.main'`.

- [ ] **Step 3: Implement**

`src/main.py`:
```python
import dataclasses
import sys

from . import fetch, leaderboard, parse
from .models import HistoryRow
from .names import NameMatcher


def run(sheet, fetch_posts=None) -> dict:
    fetch_posts = fetch_posts or fetch.fetch_posts_until
    history = sheet.read_history()
    aliases = sheet.read_aliases()
    seen_review = sheet.read_review_keys()

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
                stars=line.stars, spades=line.spades))

    existing = {(r.msg_id, r.raw_name) for r in history}
    added = [r for r in new_rows if (r.msg_id, r.raw_name) not in existing]
    merged = sorted(history + added, key=lambda r: (r.msg_id, r.place))

    matcher = NameMatcher(aliases)
    canonical_rows: list[HistoryRow] = []
    for r in merged:
        res = matcher.resolve(r.raw_name)
        if res.kind == "auto_merged":
            review.append(("auto_merged",
                           f"«{r.raw_name}» → «{res.canonical}» "
                           f"(score {res.score:.0f})"))
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

    return {"fetched_posts": len(posts), "new_rows": len(added),
            "review_items": len(fresh_review)}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from .sheet import Sheet
    summary = run(Sheet())
    print(f"posts fetched: {summary['fetched_posts']}, "
          f"history rows added: {summary['new_rows']}, "
          f"new review items: {summary['review_items']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -v`
Expected: ALL tests from all tasks PASS.

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat: add orchestration entry point"
```

---

### Task 7: GitHub Actions workflow and setup README

**Files:**
- Create: `.github/workflows/update.yml`, `README.md`

**Interfaces:**
- Consumes: `python -m src.main` entry point (Task 6); env vars `GOOGLE_CREDENTIALS`, `SHEET_ID` (Task 5).
- Produces: daily cron at 08:00 UTC + manual trigger; user-facing setup guide.

- [ ] **Step 1: Write the workflow**

`.github/workflows/update.yml`:
```yaml
name: Update ratings

on:
  schedule:
    - cron: "0 8 * * *"
  workflow_dispatch:

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python -m pytest -q
      - run: python -m src.main
        env:
          GOOGLE_CREDENTIALS: ${{ secrets.GOOGLE_CREDENTIALS }}
          SHEET_ID: ${{ secrets.SHEET_ID }}
```

- [ ] **Step 2: Write the README**

`README.md` — must contain, in this order:
1. One-paragraph description (what the bot does, link to the channel and the spec).
2. **Google setup (click-by-click):** console.cloud.google.com → create project `ducks-rating` → "APIs & Services" → enable **Google Sheets API** and **Google Drive API** → "Credentials" → "Create credentials" → "Service account" → any name → done → open the service account → "Keys" → "Add key" → "Create new key" → JSON → file downloads. Create a Google Sheet at sheets.new, click Share, paste the service account's email (from the JSON, field `client_email`), give **Editor**. Copy the sheet ID from the URL (`/d/<THIS PART>/edit`).
3. **GitHub setup:** create a repo, push this code, then Settings → Secrets and variables → Actions → New repository secret: `GOOGLE_CREDENTIALS` = full contents of the JSON file; `SHEET_ID` = the sheet ID.
4. **Local run (backfill):** `pip install -r requirements.txt`, put the JSON next to the code as `service_account.json` (it is gitignored), then PowerShell: `$env:SHEET_ID = "<id>"; python -m src.main`. First run walks the whole channel history (a few minutes).
5. **Daily operation:** Actions tab → the "Update ratings" workflow runs daily at 08:00 UTC; green check = updated, red ❌ = look at the log. "Run workflow" button = manual update.
6. **Fixing names:** Aliases tab (`written as` → `real player`), takes effect next run, retroactively. "Needs review" tab lists what the bot wants a human to look at.

- [ ] **Step 3: Verify workflow YAML is well-formed**

Run: `python -c "import json, urllib.request; print('yaml check skipped - no pyyaml')"` — instead verify by eye against the block above, and run the full suite once more: `python -m pytest -q`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add .github README.md
git commit -m "feat: add GitHub Actions daily workflow and setup guide"
```

---

## Post-plan: first real run (with the user)

Not a coding task — done together with the user after Task 7:
1. User completes README §2–3 (Google + GitHub setup).
2. Local backfill run: watch it populate History, Overall, Monthly.
3. User eyeballs the Sheet; fix aliases as needed; re-run to see retro-fix.
4. Push to GitHub; trigger "Run workflow" manually once; confirm green.
5. Cron takes over.
