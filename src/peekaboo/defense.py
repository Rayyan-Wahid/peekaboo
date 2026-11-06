"""Bounded, order-preserving per-direction/flow timestamp simulation only."""
import hashlib
import numpy as np


def jitter_trace(trace, max_delay_ms, seed, source_hash):
    if not np.isfinite(max_delay_ms) or max_delay_ms < 0:
        raise ValueError('Jitter bound must be finite and nonnegative')
    times = np.asarray(trace['time'], dtype=float)
    if not len(times) or not np.isfinite(times).all() or (np.diff(times) < 0).any():
        raise ValueError('Jitter input must be finite, nonempty, and time ordered')
    seed_bytes = hashlib.sha256(f'{seed}:{source_hash}'.encode()).digest()[:8]
    rng = np.random.default_rng(int.from_bytes(seed_bytes, 'big'))
    delayed = times + rng.uniform(0, max_delay_ms / 1000, len(times))
    # Do not reorder packets inside a TCP direction. Directions/flows may interleave.
    previous = {}
    for i, (flow, direction) in enumerate(zip(trace['flow'], trace['direction'])):
        key = (int(flow), int(direction))
        delayed[i] = max(delayed[i], previous.get(key, delayed[i]))
        previous[key] = delayed[i]
    order = np.argsort(delayed, kind='stable')
    result = {key: np.asarray(values)[order].copy() for key, values in trace.items()}
    result['time'] = delayed[order]
    delays_ms = (delayed - times) * 1000
    costs = {'mean_packet_delay_ms': float(delays_ms.mean()),
             'p95_packet_delay_ms': float(np.percentile(delays_ms, 95)),
             'max_packet_delay_ms': float(delays_ms.max()),
             'trace_finish_extension_ms': float((delayed.max() - times[-1]) * 1000),
             'byte_overhead_percent': 0.0}
    return result, costs
