"""Bob Ross: local democratic refinement of BSIM match metadata."""

from collections import Counter
from logging import Logger
from typing import Any, List, Optional, TypeGuard
import json

from sighthouse.frontend.model import Function
from sighthouse.frontend.model import Match


class BobRossMatch(Match):

    def __init__(self, id: int, name: str, function: int, metadata: dict):
        super().__init__(id, name, function, metadata)
        # Lazy cache for the parsed executable
        self._parsed_executable_cached = False
        self._parsed_executable_value: Any = None

    def significance(self) -> float:
        """Read the significance/confidence score."""
        return self.metadata.get("significance", 0.0)

    def set_significance(self, value: float) -> None:
        """Write the significance/confidence score."""
        self.metadata["significance"] = value

    def similarity(self) -> float:
        """Read the BSIM similarity."""
        return self.metadata.get("similarity", 0.0)

    def _parsed_executable(self) -> Any:
        """Cache for the json metadata executable"""
        if not self._parsed_executable_cached:
            self._parsed_executable_cached = True
            raw = self.metadata.get("executable")
            try:
                self._parsed_executable_value = (
                    json.loads(raw) if isinstance(raw, str) else None
                )
            except (ValueError, TypeError):
                self._parsed_executable_value = None
        return self._parsed_executable_value

    def library_name(self) -> Optional[str]:
        """Extract the library name from executable or None on failure.

        Except something like this ``{"metadata": [[<library>, <version>], ...]}``.
        """
        parsed = self._parsed_executable()
        if not isinstance(parsed, dict):
            return None
        entries = parsed.get("metadata")
        if not isinstance(entries, list) or not entries:
            return None
        first = entries[0]
        if not isinstance(first, list) or not first:
            return None
        return first[0]


class BobRossFunction(Function):

    def __init__(
        self,
        id: int,
        name: str,
        offset: int,
        matches: Optional[List[BobRossMatch]] = None,
    ):
        # section/details are DB-only fields
        super().__init__(id=id, name=name, offset=offset, section=0, details={})
        self.matches: List[BobRossMatch] = matches or []

    @classmethod
    def from_analysis_dict(cls, data: dict) -> "BobRossFunction":
        """Build from a Ghidra function dict ``{id, offset, name, matches:[...]}``."""
        function_id = data["id"]
        matches = []
        for m in data.get("matches", []):
            m["function"] = function_id
            matches.append(BobRossMatch.from_dict(m))

        return cls(
            id=function_id,
            name=data["name"],
            offset=data["offset"],
            matches=matches,  # type: ignore[arg-type]
        )

    def to_analysis_dict(self) -> dict:
        """Serialise back to the pipeline shape expected the runner."""
        return {
            "id": self.id,
            "offset": self.offset,
            "name": self.name,
            "matches": [m.to_dict() for m in self.matches],
        }


class BobRossConfig:
    """Parameters for bobross algorithm `converge_metadata_selection`:

    - 'k' is the neighbourhood radius: each function votes with the
      k functions before and after it in address order.
    - 'max_gap' is a distance threshold after which function are not
      treated as neighbours anymore.
    - 'bonus_malus' is the bonus applied to the function significance.
    - 'influence_sim' allow to decide which neighbour matches are
      allowed to vote based on their similarity.
    - 'max_iterations' is the maximum number of iteration of the propagation
      loop. It may exit early if no vote changes.
    """

    def __init__(
        self,
        k: int = 1,
        max_gap: int = 1024,
        bonus_malus: float = 0.25,
        influence_sim: float = 0.95,
        max_iterations: int = 1,
    ):
        self.k = k
        self.max_gap = max_gap
        self.bonus_malus = bonus_malus
        self.influence_sim = influence_sim
        self.max_iterations = max_iterations


def compute_neighborhoods(
    functions: List[BobRossFunction], k: int, max_gap: Optional[int] = None
) -> List[List[int]]:
    """Indices of the k nearest functions on each side, in address order
    (assuming functions are sorted by offset). When max_gap is set, it drops
    neighbours whose address are more than that many bytes away.
    """
    offsets = [f.offset for f in functions]
    n = len(functions)
    neighborhoods: List[List[int]] = []
    for i in range(n):
        window = range(max(0, i - k), min(n, i + k + 1))
        if max_gap is None:
            neighborhoods.append(list(window))
        else:
            neighborhoods.append(
                [j for j in window if abs(offsets[j] - offsets[i]) <= max_gap]
            )
    return neighborhoods


def best_library(func: BobRossFunction, influence_sim: float) -> Optional[str]:
    """The library a function votes for: its highest-significance eligible match."""
    eligible = [
        m
        for m in func.matches
        if m.library_name() is not None and m.similarity() >= influence_sim
    ]
    if not eligible:
        return None
    best = min(eligible, key=lambda m: (-m.significance(), m.name))
    return best.library_name()


def choose_representant(votes: List[Optional[str]]) -> Optional[str]:
    """Most common vote, alphabetical tie-break for determinism."""
    if not votes:
        return None

    # Should never happens but keep mypy happy...
    def is_str(value: str | None) -> TypeGuard[str]:
        return value is not None

    counts = Counter(filter(is_str, votes))
    top = counts.most_common(1)[0][1]
    return sorted(lib for lib, count in counts.items() if count == top)[0]


def converge_metadata_selection(
    functions: List[BobRossFunction],
    config: Optional[BobRossConfig] = None,
    logger: Optional[Logger] = None,
) -> List[BobRossFunction]:
    """Refine match significance via local democratic voting.

    Each round every function votes for its best library; each function then
    adopts the plurality library of its neighbourhood and its matches for that
    library get a significance bonus (others a malus). Repeats until the vote
    assignment reaches a fixed point (no label changed) or max_iterations is
    hit. Mutates matches in place and returns the functions sorted by offset.
    """
    cfg = config or BobRossConfig()
    functions = sorted(functions, key=lambda f: f.offset)
    neighborhoods = compute_neighborhoods(functions, cfg.k, cfg.max_gap)

    prev_winners: Optional[List[Optional[str]]] = None
    iterations = 0
    for _ in range(cfg.max_iterations):
        # Array of potential candidates elected as best match by the function
        best_lib = [best_library(f, cfg.influence_sim) for f in functions]
        # Select the most common library among the neighbourhood as representant
        winners: List[Optional[str]] = [
            choose_representant(
                [best_lib[j] for j in neighborhoods[i] if best_lib[j] is not None]
            )
            for i in range(len(functions))
        ]

        # Convergence reach, we can stop
        if winners == prev_winners:
            break
        prev_winners = winners
        iterations += 1

        for func, winner in zip(functions, winners):
            if winner is None:
                continue
            for match in func.matches:
                library = match.library_name()
                if library is None:
                    continue
                score = match.significance()
                if library == winner:
                    # significance is unbounded [0, +inf]
                    match.set_significance(score * (1 + cfg.bonus_malus))
                else:
                    match.set_significance(max(0.0, score * (1 - cfg.bonus_malus)))

    if logger is not None:
        decided = Counter(w for w in (prev_winners or []) if w is not None)
        logger.info(
            "bobross: %d function(s), %d iteration(s), %d with a chosen library",
            len(functions),
            iterations,
            sum(decided.values()),
        )

    return functions
