import re

from .models import RawPost, ResultLine, TournamentResult

RESULTS_MARKER = "ИТОГИ"
_MEDALS = {"\U0001F947": 1, "\U0001F948": 2, "\U0001F949": 3}

# Full result line: place marker, name, dash, stars, optional "| N ♠".
# Tolerances learned from real posts: the ⭐ before the number may be absent
# ("11. m0nakhov —  200"), a trailing word may follow it ("1 104 очка"), the
# space after a medal may be missing ("🥈Alamroom"), the knockout segment
# may use the wrong emoji or no spaces ("| ⭐️ 7", "380|3 ♥️"), the dash
# itself may be missing when the ⭐ marks the boundary ("🥇Mr.ВB ⭐️635"),
# and a decorative ⭐️ may trail the points on the guest's line
# ("Alullla - 330 ⭐️", msg 434).
_LINE_RE = re.compile(
    r"^\s*(?:(?P<medal>[\U0001F947-\U0001F949])\s*"
    r"|(?:[♠♥♦♣]️?\s*)?(?P<num>\d{1,3})[.)](?!\d)\s*)"
    r"(?P<name>.+?)(?:\s+[—–-]|[—–]|\s+(?=⭐))\s*"
    r"(?:⭐️?\s*)?(?P<stars>\d[\d\s.,]*?)\s*(?:очк\w*)?\s*(?:⭐️?\s*)?"
    r"(?:\|\s*(?:[⭐♠♥♦♣]?️?\s*(?P<knockouts>\d+)\s*[⭐♠♥♦♣]?️?)?)?\s*$"
)
# Looser marker: a line that CLAIMS to be a result line ("🥇 ..." / "8. ...")
_MARKER_RE = re.compile(
    r"^\s*(?:(?P<medal>[\U0001F947-\U0001F949])"
    r"|(?:[♠♥♦♣]️?\s*)?(?P<num>\d{1,3})[.)](?!\d))"
)
# New dialect since msg 407 (2026-08-26): medals and ⭐ dropped. Top-3 lines
# carry a ♠️ prefix ("♠️1. T.VI-4230"), points are glued to the name with a
# plain hyphen ("All_in_a-1410") or separated by spaces only ("Kastiel  1090"),
# and knockouts trail as "13 ♠️" instead of "| 13 ♠". U+208B is a subscript
# minus the admin's keyboard produced once ("Kradushiy₋500"). Since msg 428
# the points themselves may carry a decorative suit, glued ("Ула 2950♠️") or
# spaced ("Amourrrr_6 300 ♠️") — a suit with no count before it is ornament,
# not knockouts. These rules apply only to posts with at least one
# ♠️-numbered line, so glued-hyphen names in old posts ("Anna-2") keep
# parsing as names.
_NEW_DIALECT_RE = re.compile(r"^\s*[♠♥♦♣]️?\s*\d{1,3}[.)](?!\d)")
_NEW_LINE_RE = re.compile(
    r"^\s*(?:[♠♥♦♣]️?\s*)?(?P<num>\d{1,3})[.)](?!\d)\s*"
    r"(?P<name>.+?)(?:[-₋]|\s+)\s*(?P<stars>\d+)"
    r"(?:\s+(?P<knockouts>\d+))?\s*[♠♥♦♣]?️?\s*$"
)
_GLUED_DIGIT_RE = re.compile(r"[-₋]\d")
# A points-like dash followed (maybe after spaces) by a digit. Em/en dashes
# always count; a plain hyphen only when preceded by whitespace, so glued
# hyphens stay part of names ("Anna-2"). Well-formed dash-number lines parse
# via _LINE_RE; one that still reaches the bare-line branch is malformed
# ("2. Xx — 100 zz") and must reject the post rather than pass as a 0-star
# participant.
_DASH_DIGIT_RE = re.compile(r"(?:[—–]|\s-)\s*\d")
_TOP_N_RE = re.compile(r"ТОП[-\s]?(\d+)", re.IGNORECASE)
# Brothers-tournament stack transfer, in all real notations: parenthesized
# between name and points ("Mr. BB (передал стек Sailor Moon ) — ⭐️ 432"),
# replacing the points segment after the dash ("Calimocho — передал стек
# DelurKing"), or — since msg 458 — an arrow at the receiver, after the
# points ("Pereliv 1060 —> GeramiSwift") or the bare name ("Damir —>
# Robbie_robson"). «передала» is the feminine form, «передает» the present
# tense (msg 407), hence the wide «переда\w*» stem.
_TRANSFER_RE = re.compile(
    r"\s*\(\s*переда\w*\s+стек\s+(?P<paren>[^()]+?)\s*\)"
    r"|(?:\s+[—–-]|[—–])\s*переда\w*\s+стек\s+(?P<tail>.+?)\s*$"
    r"|\s*[—–-]\s*>\s*(?P<arrow>.+?)\s*$",
    re.IGNORECASE)


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
    if not tournament:
        # since msg 428 the header is a bare «ИТОГИ» and the tournament name
        # sits on the next line; a «ТОП-…» or result line means there is none
        for line in post.text.splitlines()[header_idx + 1:]:
            if not line.strip():
                continue
            if not _MARKER_RE.match(line) and not _TOP_N_RE.search(line):
                tournament = line.strip(" :!️⭐♠🔥—–-")
            break

    new_dialect = any(_NEW_DIALECT_RE.match(l) for l in post.text.splitlines())

    lines: list[ResultLine] = []
    for i, line in enumerate(post.text.splitlines()):
        if i == header_idx or not line.strip():
            continue
        transfer = ""
        tm = _TRANSFER_RE.search(line)
        if tm:
            transfer = (tm["paren"] or tm["tail"]
                        or tm["arrow"]).strip().replace("\\", "")
            line = line[:tm.start()] + line[tm.end():]
        m = _LINE_RE.match(line)
        if m:
            place = _MEDALS[m["medal"]] if m["medal"] else int(m["num"])
            lines.append(ResultLine(
                place=place,
                raw_name=m["name"].strip().replace("\\", ""),
                stars=_digits(m["stars"]),
                knockouts=int(m["knockouts"]) if m["knockouts"] else 0,
                transferred_to=transfer,
            ))
            continue
        if new_dialect:
            m = _NEW_LINE_RE.match(line)
            if m:
                lines.append(ResultLine(
                    place=int(m["num"]),
                    raw_name=m["name"].strip().replace("\\", ""),
                    stars=int(m["stars"]),
                    knockouts=int(m["knockouts"]) if m["knockouts"] else 0,
                    transferred_to=transfer,
                ))
                continue
        marker = _MARKER_RE.match(line)
        if not marker:
            continue
        if ("⭐" in line or _DASH_DIGIT_RE.search(line)
                or (new_dialect and _GLUED_DIGIT_RE.search(line))):
            # malformed star line, or a points line whose star marker is missing
            raise PostParseError(post.msg_id, f"unparseable result line: {line.strip()!r}")
        name = line[marker.end():].strip().replace("\\", "")
        if new_dialect:
            # msg 428: the ornament suit glues to pointless names too
            # ("missJuliya1679♠️")
            name = name.rstrip("♠♥♦♣️ ")
        if not name:
            raise PostParseError(post.msg_id, f"unparseable result line: {line.strip()!r}")
        if transfer and re.search(r"\s\d+$", name):
            # a stripped arrow transfer left a trailing number behind: that is
            # a points line no dialect branch managed to parse, not a bare
            # participant — quarantine instead of storing «Pereliv 1060»
            raise PostParseError(post.msg_id, f"unparseable result line: {line.strip()!r}")
        place = _MEDALS[marker["medal"]] if marker["medal"] else int(marker["num"])
        lines.append(ResultLine(place=place, raw_name=name, stars=0, knockouts=0,
                                transferred_to=transfer))

    if not lines:
        raise PostParseError(post.msg_id, "no result lines found")

    # The admin sometimes skips a number when renumbering (msg 374: 13 → 15),
    # so gaps are tolerated; order, uniqueness, and starting at 1 are not.
    places = [l.place for l in lines]
    if places[0] != 1 or any(a >= b for a, b in zip(places, places[1:])):
        raise PostParseError(post.msg_id, f"places not increasing from 1: {places}")

    # With gaps the declared ТОП-N matches the last place, not the line count;
    # a post cut short at the bottom matches neither and still quarantines.
    top_n = _TOP_N_RE.search(post.text)
    if top_n and int(top_n.group(1)) not in (len(lines), places[-1]):
        raise PostParseError(
            post.msg_id,
            f"header says ТОП-{top_n.group(1)} but {len(lines)} lines parsed"
            f" ending at place {places[-1]}")

    return TournamentResult(post.msg_id, post.date, tournament, tuple(lines))
