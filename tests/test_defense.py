"""Partner-owned defense tests, separated from shared feature tests at handoff."""
import unittest
import numpy as np
from peekaboo.defense import jitter_trace


def trace():
    return {'time': np.array([0., .001, .002, .004, .008]),
            'size': np.array([100, 200, 500, 50, 600]),
            'direction': np.array([1, 1, -1, 1, -1]),
            'flow': np.array([0, 0, 0, 1, 0])}


class JitterChecks(unittest.TestCase):
    def test_zero_jitter_is_exact_control(self):
        original = trace()
        defended, costs = jitter_trace(original, 0, 42, 'source')
        for key in original:
            np.testing.assert_array_equal(original[key], defended[key])
        self.assertTrue(all(value == 0 for value in costs.values()))

    def test_seeded_delays_bounded_and_preserve_bytes_and_direction_order(self):
        original = trace()
        defended, costs = jitter_trace(original, 100, 42, 'source')
        again, _ = jitter_trace(original, 100, 42, 'source')
        np.testing.assert_array_equal(defended['time'], again['time'])
        self.assertLessEqual(costs['max_packet_delay_ms'], 100 + 1e-9)
        self.assertGreaterEqual(costs['mean_packet_delay_ms'], 0)
        self.assertEqual(defended['size'].sum(), original['size'].sum())
        for flow in (0, 1):
            for direction in (-1, 1):
                a = (original['flow'] == flow) & (original['direction'] == direction)
                b = (defended['flow'] == flow) & (defended['direction'] == direction)
                np.testing.assert_array_equal(original['size'][a], defended['size'][b])
                self.assertTrue((defended['time'][b] >= original['time'][a]).all())
        np.testing.assert_array_equal(original['time'], trace()['time'])


if __name__ == '__main__':
    unittest.main()
