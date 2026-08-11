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
