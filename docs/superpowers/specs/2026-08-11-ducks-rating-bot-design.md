# DUCKS Poker Club Rating Bot — Design

**Date:** 2026-08-11
**Status:** Approved by user (conversation), pending spec review

## Purpose

The DUCKS poker club posts tournament results in the public Telegram channel
https://t.me/DUCKS_POKER. This bot parses those posts, keeps a full per-player
points history, and publishes monthly and overall leaderboards in a Google
Sheet — automatically, every day.

## Requirements (agreed with user)

- **Source:** public channel `t.me/DUCKS_POKER`, posts starting with «ИТОГИ».
- **Points:** the ⭐️ star number in each results line IS the rating points for
  that tournament. ♠️ spades are tracked as a secondary stat (no formula).
- **Output:** Google Sheets — full history plus Monthly and Overall leaderboards.
- **Schedule:** GitHub Actions, daily cron; manual run also possible.
- **Backfill:** entire channel history on first run.
- **Name matching:** misspelled names (e.g. `Delurking` vs `Delureking`) should
  merge into one player; uncertain cases must never be merged silently.
- **Telegram access:** web preview scraping (`t.me/s/DUCKS_POKER`) — chosen over
  Telethon/Bot API so the user needs zero Telegram-side setup (Option A).

## Architecture

One Python script, four stages: **fetch → parse → match names → write**.
The Google Sheet is the only database. GitHub Actions runs `python -m src.main`
daily; the same command runs locally on Windows.

```
t.me/s/DUCKS_POKER ──fetch──▶ raw posts ──parse──▶ results ──match──▶ canonical
                                                                        │
        Google Sheet (History / Overall / Monthly / Aliases / Needs review) ◀──write
```

### Fetch (`src/fetch.py`)

- HTTP GET `https://t.me/s/DUCKS_POKER` with a normal browser User-Agent;
  parse with BeautifulSoup. Each page shows ~20 posts; older pages are reached
  via `?before=<message_id>`.
- **Daily run:** read newest pages backward until hitting a message ID already
  present in History.
- **Backfill (first run):** paginate to the oldest post.
- Polite 1–2 s delay between page requests.
- Any HTTP error or unrecognized page structure → exit non-zero, write nothing
  (GitHub Actions shows ❌). Never write partial/guessed data.

### Parse (`src/parse.py`)

A post is a results post if its text starts with «ИТОГИ» (case-insensitive).
From it we extract:

- **Tournament name:** first line, the text after «ИТОГИ» (e.g. `SPY 007 TOURNAMENT`).
- **Tournament date:** calendar date of the Telegram post (explicit decision;
  editable later — see Write stage).
- **Result lines**, matching:
  - place: `🥇`/`🥈`/`🥉` (→ 1/2/3) or `N.` prefix
  - player name: free text, may contain spaces (`Sailor Moon`), any alphabet
  - separator: em/en dash or hyphen
  - stars: `⭐️ <integer>` (optional — see below)
  - spades: `| <integer> ♠️` (optional → 0 when absent)
- **Bare participant lines:** a line that carries a valid place marker but no
  `⭐️`/dash-number segment at all (e.g. `10. Sailormoon`) parses as a
  participation row with 0 stars, 0 spades, rather than rejecting the post —
  real posts routinely trail off into unscored names.
- **Real-world tolerances** (each learned from an actual quarantined post):
  the ⭐️ before the number may be absent (`11. m0nakhov —  200` → 200
  stars), a trailing word may follow the number (`1 104 очка` → 1104), the
  space after a medal may be missing (`🥈Alamroom`), and the knockout
  segment may use the wrong emoji or no spaces (`| ⭐️ 7`, `380|3 ♥️` →
  spades 7 / 3). A marker line with a dash segment that still fails this
  grammar (e.g. `8. Delureking — ⭐️` with no number) rejects the whole
  post as before.
- **All-or-nothing per post:** if any line inside the ТОП-N block fails to
  parse, the whole post is written to *Needs review* and none of its results
  enter History. Partial standings are worse than delayed ones.

### Name matching (`src/names.py`)

Layered, certain → uncertain:

1. **Normalize** (for comparison only): lowercase, trim/collapse spaces,
   `ё → е`, and map Latin/Cyrillic homoglyphs (а/a, е/e, о/o, р/p, с/c, х/x,
   у/y, к/k, м/m, т/t) to one alphabet. Exact match after normalization →
   same player.
2. **Aliases tab** (manual override): rows of `written as → real player`.
   Always wins over fuzzy logic.
3. **Fuzzy** (rapidfuzz similarity vs all known players), for new names only:
   - ≥ 90 → auto-merge into the existing player; an informational row is added
     to *Needs review* (`type=auto-merged`) so it can be audited.
   - 70–89 → treated as a NEW player; a *Needs review* row suggests the
     possible match («X looks like Y — same player? add an Aliases row»).
   - < 70 → new player, no note.

The **canonical display name** of a player is the raw spelling seen first;
aliases can override it. All merges are reversible: History keeps the raw
name, and canonical names are re-derived on every run (see below).

### Write (`src/sheet.py`)

Google Sheets via `gspread` + a service account (JSON key in env var
`GOOGLE_CREDENTIALS`; sheet ID in `config.py`). Batched writes.

Tabs:

| Tab | Content |
|---|---|
| **History** | one row per player per tournament: `msg_id, date, tournament, place, raw_name, player, stars, spades`; newest first |
| **Overall** | `rank, player, total ⭐️, total ♠️, tournaments played`, sorted by stars |
| **Monthly** | same columns, grouped by calendar month of `date`, current month on top |
| **Aliases** | manual `written as → real player` table |
| **Needs review** | unparseable posts, 70–89 fuzzy suggestions, auto-merge audit rows |

Update rules:

- **Dedup / idempotency:** a `(msg_id, raw_name)` pair already in History is
  never written again. Re-running is always safe.
- **Recompute:** every run re-derives the `player` (canonical) column of ALL
  History rows from `raw_name` + current Aliases, then rebuilds Overall and
  Monthly from History. So editing Aliases retroactively fixes everything.
- **Manual edits persist:** `date`, `tournament`, `stars`, `spades` etc. are
  written only when a row is created; the script never overwrites them. The
  only column it rewrites is `player`. To fix a wrong date or number, edit
  History directly.
- **Crash-safe writes:** History and the leaderboard tabs are written by
  resizing the worksheet grid to the new data's exact row count and then
  overwriting every remaining row — never by `clear()`-ing first. A crash
  between those two steps leaves the previous contents in place instead of an
  empty sheet, and the resize also lets the grid grow past its initial 1000
  rows during backfill.

## Error handling summary

| Failure | Behavior |
|---|---|
| Telegram page unreachable / markup changed | exit non-zero, no writes, ❌ in Actions |
| Post looks like results but a line won't parse | whole post → Needs review, run continues |
| Google Sheets API error | exit non-zero; next run retries (idempotent) |
| Ambiguous name (70–89) | new player + review row; never silent merge |

## Runtime & repo layout

- Python 3.12; deps: `requests`, `beautifulsoup4`, `gspread`, `rapidfuzz`,
  `pytest` (dev).
- `src/` — `main.py`, `fetch.py`, `parse.py`, `names.py`, `sheet.py`,
  `config.py`; `tests/`; `.github/workflows/update.yml`.
- Workflow: daily cron (08:00 UTC) + `workflow_dispatch` for manual runs.
  Secret: `GOOGLE_CREDENTIALS`.

## One-time setup (user, guided)

1. Create Google Cloud service account, download JSON key.
2. Create the Google Sheet, share it with the service account email (Editor).
3. Create GitHub repo, add `GOOGLE_CREDENTIALS` secret, push code.
4. First backfill run done manually together; user eyeballs the Sheet before
   the cron goes live.

## Testing

- `pytest`, no network: fixtures are saved HTML snapshots of real channel
  pages and real post texts (including SPY 007 from 2026-08-10).
- Parser: medal vs numbered places, missing spades, names with spaces,
  dash variants, non-results posts ignored, broken line → whole post rejected.
- Names: `Delureking/DelureKing` (case), `Delurking` (≥90 merge), 70–89 →
  review row, homoglyph pairs, alias override.
- Leaderboards: month grouping, totals, ranking ties (equal stars → equal
  rank, next rank skips accordingly).

## Out of scope (YAGNI)

- Posting leaderboards back into Telegram.
- Any stars+spades combined formula.
- Web UI beyond the Google Sheet.
- Handling private-channel access (channel is public).
