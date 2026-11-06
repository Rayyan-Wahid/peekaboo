import unittest
from unittest.mock import patch

import numpy as np
from peekaboo.experiment import select_baseline


class TrainingIsolation(unittest.TestCase):
    def test_model_selection_never_reads_test_rows(self):
        class GuardedRows:
            def __init__(self, rows):
                self.rows = np.asarray(rows)
            def __getitem__(self, indices):
                if any(i >= 4 for i in indices):
                    raise AssertionError('Selection accessed held-out test rows')
                return self.rows[indices]

        fit_calls = []
        class Candidate:
            def fit(self, values, labels):
                np.testing.assert_array_equal(values, [[1], [2]])
                np.testing.assert_array_equal(labels, ['a', 'b'])
                fit_calls.append(1)
            def predict(self, values):
                np.testing.assert_array_equal(values, [[3], [4]])
                return np.array(['a', 'b'])

        matrix = GuardedRows([[1], [2], [3], [4], [999], [999]])
        labels = GuardedRows(['a', 'b', 'a', 'b', 'secret-test-a', 'secret-test-b'])
        split = {'train': np.array([0, 1]), 'validation': np.array([2, 3]), 'test': np.array([4, 5])}
        with patch('peekaboo.experiment.forest', side_effect=lambda *args: Candidate()):
            _, candidates = select_baseline(matrix, labels, split,
                {'min_samples_leaf_candidates': [1, 2, 4]}, ['a', 'b'])
        self.assertEqual(len(fit_calls), 3)
        self.assertEqual(len(candidates), 3)


if __name__ == '__main__':
    unittest.main()
