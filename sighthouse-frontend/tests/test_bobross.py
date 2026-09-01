"""Unit tests for the Bob Ross algorithm."""

import json
import unittest

from sighthouse.frontend.bobross import (
    BobRossConfig,
    BobRossFunction,
    BobRossMatch,
    compute_neighborhoods,
    converge_metadata_selection,
)


def _match(name, library, similarity, significance):
    """A Ghidra-shaped match."""
    return {
        "name": name,
        "metadata": {
            "significance": significance,
            "similarity": similarity,
            "executable": json.dumps(
                {"metadata": [[library, "1.0"]], "origin": "test"}
            ),
        },
    }


def _func(fid, offset, matches):
    """A Ghidra-shaped function."""
    return {"id": fid, "offset": offset, "name": f"func_{fid}", "matches": matches}


def _run(func_dicts, **cfg):
    """Wrapper for running bob ross"""
    functions = [BobRossFunction.from_analysis_dict(d) for d in func_dicts]
    return converge_metadata_selection(functions, BobRossConfig(**cfg))


class TestBobRoss(unittest.TestCase):

    def test_compute_neighborhoods(self):
        # Positional: k nearest on each side in address order, self included.
        functions = [
            BobRossFunction(fid, "f", off, [])
            for fid, off in enumerate([0, 32, 64, 200])
        ]
        self.assertEqual(
            compute_neighborhoods(functions, k=1),
            [[0, 1], [0, 1, 2], [1, 2, 3], [2, 3]],
        )

        self.assertEqual(
            compute_neighborhoods(functions, k=2),
            [[0, 1, 2], [0, 1, 2, 3], [0, 1, 2, 3], [1, 2, 3]],
        )

    def test_single(self):
        self.assertEqual(
            compute_neighborhoods([BobRossFunction(0, "f", 0, [])], k=1), [[0]]
        )

    def test_max_gap(self):
        functions = [
            BobRossFunction(fid, "f", off, [])
            for fid, off in enumerate([0, 5000, 10000])
        ]
        self.assertEqual(
            compute_neighborhoods(functions, k=1, max_gap=1024), [[0], [1], [2]]
        )
        # Without the cap the full positional window is kept.
        self.assertEqual(
            compute_neighborhoods(functions, k=1, max_gap=None),
            [[0, 1], [0, 1, 2], [1, 2]],
        )

    def test_idempotent(self):
        """Running the algorithm once it converges should yield the same result"""
        scenario = [
            _func(1, 0, [_match("c", "zlib", 0.9, 1.0)]),
            _func(2, 10, [_match("n1", "openssl", 0.95, 5.0)]),
            _func(3, 20, [_match("n2", "openssl", 0.95, 5.0)]),
        ]
        one = _run(scenario, k=2, bonus_malus=0.1, max_iterations=1)
        many = _run(scenario, k=2, bonus_malus=0.1, max_iterations=10)
        self.assertEqual(
            [m.significance() for f in one for m in f.matches],
            [m.significance() for f in many for m in f.matches],
        )

    def test_determinism(self):
        """Running twice the algorithm give the same result"""
        scenario = [
            _func(1, 0, [_match("c", "zlib", 0.9, 1.0)]),
            _func(2, 10, [_match("n1", "openssl", 0.95, 5.0)]),
            _func(3, 20, [_match("n2", "openssl", 0.95, 5.0)]),
        ]
        first = _run(scenario, k=2, max_iterations=3)
        second = _run(scenario, k=2, max_iterations=3)
        self.assertEqual(
            [m.significance() for f in first for m in f.matches],
            [m.significance() for f in second for m in f.matches],
        )


if __name__ == "__main__":
    unittest.main()
