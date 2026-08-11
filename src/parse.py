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
