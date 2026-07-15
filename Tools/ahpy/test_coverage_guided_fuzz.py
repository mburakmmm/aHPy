import random
import unittest

from coverage_guided_fuzz import generate_candidates, greedy_select


class CoverageGuidedFuzzTest(unittest.TestCase):
    def test_candidates_are_deterministic_valid_python(self):
        first = generate_candidates(17, 32)
        second = generate_candidates(17, 32)
        changed = generate_candidates(18, 32)
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)
        self.assertEqual(len({candidate["name"] for candidate in first}), 32)
        self.assertEqual(len({candidate["family"] for candidate in first}), 16)
        for candidate in first:
            compile(candidate["source"], candidate["name"], "exec")

    def test_greedy_selection_keeps_new_lines_or_families(self):
        candidates = [
            ({"id": 0, "family": "a", "source": "", "name": "a0"}, {1, 2}),
            ({"id": 1, "family": "a", "source": "", "name": "a1"}, {2}),
            ({"id": 2, "family": "b", "source": "", "name": "b0"}, {2}),
            ({"id": 3, "family": "a", "source": "", "name": "a2"}, {2, 3}),
        ]
        selected, covered = greedy_select(candidates)
        self.assertEqual([candidate["id"] for candidate in selected], [0, 2, 3])
        self.assertEqual(covered, {1, 2, 3})
        self.assertEqual(selected[-1]["new_coverage_lines"], 1)

    def test_candidate_rng_does_not_change_global_random_state(self):
        random.seed(123)
        before = random.getstate()
        generate_candidates(99, 8)
        self.assertEqual(random.getstate(), before)


if __name__ == "__main__":
    unittest.main()
