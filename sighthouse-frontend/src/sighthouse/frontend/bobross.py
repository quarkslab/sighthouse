from argparse import ArgumentParser
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter
import json
import re

import cxxfilt
import numpy as np


class NameDemangler:
    """Handle demangling for multiple languages and compilers."""

    @staticmethod
    def demangle(name: str) -> Tuple[str, str]:
        """
        Demangle a function name and return (demangled_name, mangling_type).
        Returns (original_name, 'none') if not mangled.
        """
        # Try C++ demangling (GCC/Clang Itanium ABI)
        if name.startswith("_Z"):
            demangled = NameDemangler._demangle_cpp_itanium(name)
            if demangled:
                return demangled, "cpp_itanium"

        # Try MSVC C++ mangling
        # if name.startswith("?"):
        #     demangled = NameDemangler._demangle_cpp_msvc(name)
        #     if demangled:
        #         return demangled, "cpp_msvc"

        # Try Rust mangling (legacy)
        # if name.startswith("_ZN") and "17h" in name:
        #     demangled = NameDemangler._demangle_rust_legacy(name)
        #     if demangled:
        #         return demangled, "rust_legacy"

        # Try Rust v0 mangling
        # if name.startswith("_R"):
        #     demangled = NameDemangler._demangle_rust_v0(name)
        #     if demangled:
        #         return demangled, "rust_v0"

        # Try D language mangling
        if name.startswith("_D"):
            demangled = NameDemangler._demangle_d(name)
            if demangled:
                return demangled, "d_lang"

        # Swift mangling
        # if name.startswith("_T") or name.startswith("$s") or name.startswith("_$s"):
        #     demangled = NameDemangler._demangle_swift(name)
        #     if demangled:
        #         return demangled, "swift"

        return name, "none"

    @staticmethod
    def _demangle_cpp_itanium(name: str) -> Optional[str]:
        """Demangle C++ Itanium ABI (GCC/Clang)."""
        try:
            return cxxfilt.demangle(name)
        except Exception:
            return None

    # @staticmethod
    # def _demangle_cpp_msvc(name: str) -> Optional[str]:
    #    """Demangle MSVC C++ names."""
    #    try:
    #        import subprocess
    #        # You'd need undname.exe or similar
    #        result = subprocess.run(['undname', name], capture_output=True, text=True, timeout=1)
    #        if result.returncode == 0:
    #            return result.stdout.strip()
    #    except:
    #        pass
    #    return None

    # @staticmethod
    # def _demangle_rust_legacy(name: str) -> Optional[str]:
    #    """Demangle legacy Rust names."""
    #    try:
    #        import subprocess
    #        result = subprocess.run(['rustfilt', name], capture_output=True, text=True, timeout=1)
    #        if result.returncode == 0:
    #            return result.stdout.strip()
    #    except:
    #        pass
    #
    #    # Fallback: remove hash suffix
    #    # _ZN4core3ptr85drop_in_place$LT$std..rt..lang_start$LT$$LP$$RP$$GT$..$u7b$$u7b$closure$u7d$$u7d$$GT$17h1234567890abcdefE
    #    match = re.match(r'(.+?)17h[0-9a-f]{16}E?$', name)
    #    if match:
    #        return match.group(1).replace('$LT$', '<').replace('$GT$', '>').replace('$u7b$', '{').replace('$u7d$', '}')
    #
    #    return None

    # @staticmethod
    # def _demangle_rust_v0(name: str) -> Optional[str]:
    #    """Demangle Rust v0 mangling scheme."""
    #    try:
    #        import subprocess
    #        result = subprocess.run(['rustfilt', name], capture_output=True, text=True, timeout=1)
    #        if result.returncode == 0:
    #            return result.stdout.strip()
    #    except:
    #        pass
    #    return None

    @staticmethod
    def _demangle_d(name: str) -> Optional[str]:
        """Demangle D language names."""
        # Basic D demangling - you might want a proper library
        if name.startswith("_D"):
            # Simple approach: extract readable parts
            return name[2:]  # Remove _D prefix
        return None

    # @staticmethod
    # def _demangle_swift(name: str) -> Optional[str]:
    #    """Demangle Swift names."""
    #    try:
    #        import subprocess
    #        result = subprocess.run(['swift-demangle', name], capture_output=True, text=True, timeout=1)
    #        if result.returncode == 0:
    #            return result.stdout.strip()
    #    except:
    #        pass
    #    return None

    @staticmethod
    def normalize_name(name: str) -> str:
        """
        Get a normalized version of the name for comparison.
        Removes common variations that don't affect function identity.
        """
        demangled, _ = NameDemangler.demangle(name)

        # Remove template parameters for comparison
        normalized = re.sub(r"<[^>]+>", "", demangled)

        # Remove namespace/class qualifiers for loose matching (optional)
        # normalized = normalized.split('::')[-1]

        # Remove parameter lists
        normalized = re.sub(r"\([^)]*\)", "", normalized)

        # Remove spaces
        normalized = normalized.replace(" ", "")

        return normalized.lower()

    @staticmethod
    def extract_function_name(name: str) -> str:
        """
        Extract just the function name from a fully qualified name.
        Examples:
            libcli::Cli::printlnNum -> printlnNum
            HAL_PWR_DisableBkUpAccess -> HAL_PWR_DisableBkUpAccess
            std::vector<int>::push_back -> push_back
            namespace::Class::method() -> method
        """
        # First demangle
        demangled, _ = NameDemangler.demangle(name)

        # Remove parameter lists: method(int, char) -> method
        demangled = re.sub(r"\([^)]*\).*$", "", demangled)

        # Remove template parameters: method<T> -> method
        demangled = re.sub(r"<[^>]*>", "", demangled)

        # Extract last part after ::
        if "::" in demangled:
            parts = demangled.split("::")
            function_name = parts[-1]
        else:
            function_name = demangled

        # Remove any remaining whitespace
        function_name = function_name.strip()

        return function_name


class Match:
    """Represents a single match for a function."""

    def __init__(
        self,
        name: str,
        confidence: float,
        similarity: float,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.confidence = confidence
        self.similarity = similarity
        self.metadata = metadata or {}

        # Cache demangled name
        self._demangled_name: Optional[str] = None
        self._normalized_name: Optional[str] = None
        self._function_name: Optional[str] = None

    def get_metadata_name(self) -> Optional[str]:
        """Extract library name from metadata (ignoring version)."""
        li = self.metadata.get("metadata")
        if not isinstance(li, list) or not isinstance(li[0], list):
            return None
        return li[0][0]

    def get_demangled_name(self) -> str:
        """Get demangled name (cached)."""
        if self._demangled_name is None:
            self._demangled_name, _ = NameDemangler.demangle(self.name)
        return self._demangled_name

    def get_normalized_name(self) -> str:
        """Get normalized name for comparison (cached)."""
        if self._normalized_name is None:
            self._normalized_name = NameDemangler.normalize_name(self.name)
        return self._normalized_name

    def get_function_name(self) -> str:
        """Get just the function name without namespace/class (cached)."""
        if self._function_name is None:
            self._function_name = NameDemangler.extract_function_name(self.name)
        return self._function_name

    def merge_with(self, other: "Match") -> "Match":
        """Merge this match with another, combining metadata."""
        combined_metadata = self.metadata.copy()
        combined_metadata.update(other.metadata.copy())

        return Match(
            name=self.name,
            confidence=max(self.confidence, other.confidence),
            similarity=max(self.similarity, other.similarity),
            metadata=combined_metadata,
        )

    def copy(self) -> "Match":
        """Create a deep copy of the match."""
        return Match(
            name=self.name,
            confidence=self.confidence,
            similarity=self.similarity,
            metadata={k: v for k, v in self.metadata.items()},
        )

    def sort_key(self) -> Tuple:
        """Return a deterministic sort key for this match."""
        metadata_str = str(self.metadata) if self.metadata else ""
        return (-self.similarity, self.name, metadata_str)

    def __repr__(self):
        return f"{self.name} {self.similarity} {self.metadata}"


class Function:
    """Represents a function with its matches."""

    def __init__(
        self, id: int, address: int, name: str, matches: Optional[List[Match]] = None
    ):
        self.id = id
        self.address = address
        self.name = name
        self.matches: List[Match] = matches or []

    def get_best_match(
        self, potential_candidates: Optional[List[Match]] = None
    ) -> Tuple[Optional[Match], float]:
        """Get the match with highest similarity (deterministic)."""
        if not self.matches:
            return None, 0.0

        if potential_candidates is None:
            candidate_matches = self.matches
        else:
            candidate_matches = [
                m for m in self.matches if m.get_metadata_name() in potential_candidates
            ]

        if not candidate_matches:
            return None, 0.0

        candidate_matches_sorted = sorted(candidate_matches, key=lambda m: m.sort_key())
        best = candidate_matches_sorted[0]
        return best, best.similarity

    def sort_matches_deterministic(self):
        """Sort matches deterministically by similarity (desc) then name (asc)."""
        self.matches.sort(key=lambda m: m.sort_key())

    def copy(self) -> "Function":
        """Create a deep copy of the function."""
        return Function(
            id=self.id,
            address=self.address,
            name=self.name,
            matches=[m.copy() for m in self.matches],
        )

    @classmethod
    def from_dict(cls, data: dict) -> "Function":
        """Create a Function from a dictionary."""
        matches = [
            Match(
                name=m["name"],
                confidence=m["metadata"]["significance"],
                similarity=m["metadata"]["similarity"],
                metadata=json.loads(m["metadata"]["executable"]),
            )
            for m in data.get("matches", [])
        ]
        return cls(
            id=data["id"],
            address=data["offset"],
            name=data["name"],
            matches=matches,
        )

    def to_dict(self) -> dict:
        """Convert Function to dictionary."""
        return {
            "id": self.id,
            "offset": self.address,
            "name": self.name,
            "matches": [
                {
                    "id": 0,
                    "function": self.id,
                    "name": m.name,
                    "metadata": {
                        "significance": m.confidence,
                        "similarity": m.similarity,
                        "executable": m.metadata,
                    },
                }
                for m in self.matches
            ],
        }

    # def to_dict_one_match(self) -> dict:
    #     """Convert Function to dictionary with only best match."""
    #     return {
    #         "address": self.address,
    #         "name": self.name,
    #         "matches": [
    #             {
    #                 "name": m.name,
    #                 "confidence": m.confidence,
    #                 "similarity": m.similarity,
    #                 "metadata": m.metadata,
    #             }
    #             for m in ([self.matches[0]] if len(self.matches) > 0 else [])
    #         ],
    #     }

    def __str__(self):
        return f"{self.address} : {self.name} | {self.matches}"


def converge_metadata_selection(
    functions: List[Function],
    distance: int = 1000,
    bonus_malus: float = 0.1,
    max_iterations: int = 100,
    convergence_threshold: float = 0.001,
    influence_sim: float = 0.85,
) -> List[Function]:
    """
    Iteratively refine function metadata selection using local democratic voting.

    Args:
        functions: List of Function objects (will be sorted by address)
        distance: Address distance threshold for local voting neighborhood
        bonus_malus: Bonus/malus factor for metadata alignment (default: 0.1)
        max_iterations: Maximum number of iterations (default: 100)
        convergence_threshold: Minimum change to continue iterating (default: 0.001)
        influence_sim: Minimum similarity need to take in count during local vote

    Returns:
        List of functions with updated similarity scores (sorted by address)
    """

    # Sort functions by address for optimized neighbor search
    functions = sorted(functions, key=lambda f: f.address)

    def get_neighbors(
        func_idx: int, functions: List[Function], distance: int
    ) -> np.ndarray:
        """Get indices of functions within distance threshold."""
        current_address = functions[func_idx].address
        neighbors = [func_idx]  # Include self

        # Search left (lower addresses)
        left_idx = func_idx - 1
        while (
            left_idx >= 0 and current_address - functions[left_idx].address <= distance
        ):
            neighbors.append(left_idx)
            left_idx -= 1

        # Search right (higher addresses)
        right_idx = func_idx + 1
        while (
            right_idx < len(functions)
            and functions[right_idx].address - current_address <= distance
        ):
            neighbors.append(right_idx)
            right_idx += 1

        return np.array(sorted(neighbors), dtype=np.int32)  # Sort for determinism

    def vote_locally(
        func_idx: int, functions: List[Function], distance: int
    ) -> Optional[str]:
        """Local democratic vote among neighboring functions."""
        neighbor_indices = get_neighbors(func_idx, functions, distance)
        metadata_votes = []
        potential_candidates = set()

        tmp_matches = functions[func_idx].matches
        if tmp_matches is not None and tmp_matches != []:
            for m in tmp_matches:
                candidate = m.get_metadata_name()
                if candidate:
                    potential_candidates.add(candidate)

        for neighbor_idx in neighbor_indices:
            neighbor_func = functions[neighbor_idx]
            best_match, best_similarity = neighbor_func.get_best_match(
                potential_candidates
            )
            if best_match and best_similarity >= influence_sim:
                metadata_name = best_match.get_metadata_name()
                if metadata_name:
                    metadata_votes.append(metadata_name)

        if not metadata_votes:
            return None

        # Count votes and return winner (deterministic in case of tie)
        counter = Counter(metadata_votes)
        # Sort by count (desc) then alphabetically (asc) for determinism
        most_common_list = counter.most_common()
        max_count = most_common_list[0][1]

        # Get all metadata with max count, then sort alphabetically
        winners = [meta for meta, count in most_common_list if count == max_count]
        # print(counter, winners)
        return sorted(winners)[0]  # Alphabetically first winner

    def compute_all_votes(functions: List[Function], distance: int) -> np.ndarray:
        """Compute local votes for all functions simultaneously."""
        votes = []
        for idx in range(len(functions)):
            chosen_metadata = vote_locally(idx, functions, distance)
            votes.append(chosen_metadata)
        return np.array(votes, dtype=object)

    def apply_bonus_malus_all(
        functions: List[Function],
        chosen_metadata_list: np.ndarray,
        bonus_malus: float,
    ) -> List[Function]:
        """Apply bonus/malus to all functions based on their local votes."""
        updated_functions = []

        for func_idx, func in enumerate(functions):
            chosen_metadata = chosen_metadata_list[func_idx]
            updated_func = func.copy()

            for match in updated_func.matches:
                metadata_name = match.get_metadata_name()

                # Apply bonus if metadata matches chosen one, malus otherwise
                if chosen_metadata and metadata_name == chosen_metadata:
                    match.similarity = min(1.0, match.similarity * (1 + bonus_malus))
                elif chosen_metadata and metadata_name is not None:
                    match.similarity = max(0.0, match.similarity * (1 - bonus_malus))

            updated_functions.append(updated_func)

        return updated_functions

    def calculate_total_change(
        old_functions: List[Function], new_functions: List[Function]
    ) -> float:
        """Calculate total change in similarity scores using NumPy."""
        old_sims = np.array([func.get_best_match()[1] for func in old_functions])
        new_sims = np.array([func.get_best_match()[1] for func in new_functions])
        return np.sum(np.abs(new_sims - old_sims))

    # Main convergence loop
    current_functions = [func.copy() for func in functions]

    for iteration in range(max_iterations):
        # Compute all local votes simultaneously
        chosen_metadata_list = compute_all_votes(current_functions, distance)

        # Sort matches deterministically
        for function in current_functions:
            function.sort_matches_deterministic()

        # Apply bonus/malus based on local votes
        updated_functions = apply_bonus_malus_all(
            current_functions, chosen_metadata_list, bonus_malus
        )

        # Check convergence
        total_change = calculate_total_change(current_functions, updated_functions)

        # Print iteration details (optional)
        # metadata_summary = Counter([m for m in chosen_metadata_list if m is not None])
        # print(f"Iteration {iteration + 1}: Total change = {total_change:.6f}")

        if total_change < convergence_threshold:
            current_functions = updated_functions
            break

        current_functions = updated_functions

    return current_functions


# def main():
#     parser = ArgumentParser()
#     parser.add_argument("output_path")
#
#     args = parser.parse_args()
#
#     # Analysis succeed, load program
#     with open(args.output_path, "r", encoding="utf-8") as fp:
#         program = json.load(fp)
#
#     # Delete all functions from all sections
#     for section in program["sections"]:
#         functions: List[Function] = [
#             Function.from_dict(f) for f in section["functions"]
#         ]
#         for function in functions:
#             function.sort_matches_deterministic()
#
#         result = converge_metadata_selection(
#             functions,
#             distance=64,
#             bonus_malus=0.0935,
#             max_iterations=1,
#             influence_sim=0.85,
#         )
#         section["functions"] = [f.to_dict() for f in result]
#         print(section)
#
#
# if __name__ == "__main__":
#     main()
