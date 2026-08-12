from dataclasses import dataclass

from rapidfuzz import fuzz

AUTO_MERGE_SCORE = 90
REVIEW_SCORE = 70

# lowercase Cyrillic -> Latin lookalikes (comparison only, never for display)
_HOMOGLYPHS = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x",
    "у": "y", "к": "k", "м": "m", "т": "t", "н": "h", "в": "b",
})

# Informal Cyrillic -> Latin transliteration, the way club players actually
# romanize nicknames («Арчи» -> "archi"). Comparison only, never for display.
_CYR_LAT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
    "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "y",
    "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def normalize(name: str) -> str:
    n = " ".join(name.lower().split())
    n = n.replace("ё", "е")
    return n.translate(_HOMOGLYPHS)


def transliterate(name: str) -> str:
    n = " ".join(name.lower().split()).replace("ё", "е")
    return "".join(_CYR_LAT.get(ch, ch) for ch in n)


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
        self._translits: dict[str, str] = {}  # normalized -> transliterated

    def _register(self, norm: str, display: str) -> None:
        self._players[norm] = display
        self._translits[norm] = transliterate(display)

    def resolve(self, raw_name: str) -> Resolution:
        norm = normalize(raw_name)
        if norm in self._aliases:
            canonical = self._aliases[norm]
            if normalize(canonical) not in self._players:
                self._register(normalize(canonical), canonical)
            return Resolution(canonical, "alias")
        if norm in self._players:
            return Resolution(self._players[norm], "exact")

        translit = transliterate(raw_name)
        best_score, best_player = 0.0, ""
        for pnorm, canonical in self._players.items():
            score = max(fuzz.ratio(norm, pnorm),
                        fuzz.ratio(translit, self._translits[pnorm]))
            if score > best_score:
                best_score, best_player = score, canonical

        if best_score >= AUTO_MERGE_SCORE:
            return Resolution(best_player, "auto_merged",
                              similar_to=best_player, score=best_score)
        self._register(norm, raw_name)
        if best_score >= REVIEW_SCORE:
            return Resolution(raw_name, "new_review",
                              similar_to=best_player, score=best_score)
        return Resolution(raw_name, "new")
