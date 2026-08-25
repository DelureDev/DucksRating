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
    knockouts: int
    transferred_to: str = ""  # raw name of who received this player's stack


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
    knockouts: int
    transferred_to: str = ""   # raw, as written in the post
    transfer_player: str = ""  # canonical, recomputed every run like `player`
