import re

from .models import RawPost, ResultLine, TournamentResult

RESULTS_MARKER = "ИТОГИ"
_MEDALS = {"\U0001F947": 1, "\U0001F948": 2, "\U0001F949": 3}

# Full result line: place marker, name, dash, stars, optional "| N ♠".
# Tolerances learned from real posts: the ⭐ before the number may be absent
# ("11. m0nakhov —  200"), a trailing word may follow it ("1 104 очка"), the
# space after a medal may be missing ("🥈Alamroom"), and the knockout segment
# may use the wrong emoji or no spaces ("| ⭐️ 7", "380|3 ♥️").
_LINE_RE = re.compile(
    r"^\s*(?:(?P<medal>[\U0001F947-\U0001F949])\s*|(?P<num>\d{1,3})[.)](?!\d)\s*)"
    r"(?P<name>.+?)\s*[—–-]\s*"
    r"(?:⭐️?\s*)?(?P<stars>\d[\d\s.,]*?)\s*(?:очк\w*)?\s*"
    r"(?:\|\s*(?:[⭐♠♥♦♣]?️?\s*(?P<spades>\d+)\s*[⭐♠♥♦♣]?️?)?)?\s*$"
)
# Looser marker: a line that CLAIMS to be a result line ("🥇 ..." / "8. ...")
_MARKER_RE = re.compile(
    r"^\s*(?:(?P<medal>[\U0001F947-\U0001F949])|(?P<num>\d{1,3})[.)](?!\d))"
)
# A dash/hyphen followed (maybe after spaces) by a digit. Well-formed
# dash-number lines parse via _LINE_RE (stars without the ⭐ emoji); if one
# still reaches the bare-line branch it is malformed ("5. X — ⭐️" with no
# number, garbled tail, etc.) and must reject the post rather than pass as a
# 0-star participant.
_DASH_DIGIT_RE = re.compile(r"[—–-]\s*\d")
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
                raw_name=m["name"].strip().replace("\\", ""),
                stars=_digits(m["stars"]),
                spades=int(m["spades"]) if m["spades"] else 0,
            ))
            continue
        marker = _MARKER_RE.match(line)
        if not marker:
            continue
        if "⭐" in line or _DASH_DIGIT_RE.search(line):
            # malformed star line, or a points line whose star marker is missing
            raise PostParseError(post.msg_id, f"unparseable result line: {line.strip()!r}")
        name = line[marker.end():].strip().replace("\\", "")
        if not name:
            raise PostParseError(post.msg_id, f"unparseable result line: {line.strip()!r}")
        place = _MEDALS[marker["medal"]] if marker["medal"] else int(marker["num"])
        lines.append(ResultLine(place=place, raw_name=name, stars=0, spades=0))

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
