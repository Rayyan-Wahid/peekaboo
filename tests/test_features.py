import unittest
from pathlib import Path
import socket
import struct
import tempfile
import numpy as np

from peekaboo.features import connect_boundaries, select_packets, feature_vector, split_for, extract_capture
from peekaboo.collect import executable


def trace():
    return {'time': np.array([0., .001, .002, .004, .008]),
            'size': np.array([100, 200, 500, 50, 600]),
            'direction': np.array([1, 1, -1, 1, -1]),
            'flow': np.array([0, 0, 0, 1, 0])}


class PlaintextExclusion(unittest.TestCase):
    def test_segmented_header_and_coalesced_tls_boundary(self):
        # The displayed TCP payload may contain only the last fragment of a header.
        tail = b'Host: hidden.example\r\n\r\n'
        reply = b'HTTP/1.1 200 Connection Established\r\n\r\n'
        rows = [['0', '50000', '25', tail.hex(), 'CONNECT', ''],
                ['0', '60000', '1', (reply + b'\x16\x03\x03opaque').hex(), '', '200']]
        boundaries = connect_boundaries(rows, 60000)
        self.assertEqual(boundaries[0][1], 25 + len(tail))
        self.assertEqual(boundaries[0][-1], 1 + len(reply))

    def test_plaintext_retransmissions_clipped_and_unknown_tunnels_excluded(self):
        boundaries = {0: {1: 101, -1: 51}}
        rows = [['10', '0', '50000', '60000', '1', '100'],  # CONNECT only
                ['11', '0', '50000', '60000', '91', '30'],  # ten plaintext bytes
                ['12', '0', '60000', '50000', '51', '100'],
                ['13', '0', '50000', '60000', '91', '30'],  # retransmission
                ['14', '1', '50001', '60000', '1', '900'],  # incomplete tunnel
                ['31', '0', '60000', '50000', '151', '100']]  # window endpoint
        selected, info = select_packets(rows, boundaries, 60000, 20)
        np.testing.assert_array_equal(selected['size'], [20, 100, 20])
        np.testing.assert_array_equal(selected['direction'], [1, -1, 1])
        np.testing.assert_allclose(selected['time'], [0, 1, 2])
        self.assertEqual(info['outside_window_packets'], 1)
        self.assertEqual(info['unmapped_payload_packets'], 1)

    def test_incomplete_header_fails_closed(self):
        with self.assertRaises(ValueError):
            connect_boundaries([['0', '50000', '1', b'CONNECT incomplete'.hex(), 'CONNECT', '']], 60000)

    def test_orphan_reassembled_response_cannot_create_a_tunnel(self):
        self.assertEqual(connect_boundaries([['4', '60000', '4083', '', '', '200']], 60000), {})

    def test_reassembly_on_ack_uses_reassembled_byte_boundary(self):
        request = b'CONNECT example.org:443 HTTP/1.1\r\n\r\n'
        reply = b'HTTP/1.1 200 Connection Established\r\n\r\n'
        rows = [['0', '50000', '1', request.hex(), 'CONNECT', '', '', str(len(request))],
                ['0', '60000', str(1 + len(reply)), '', '', '200', reply.hex(), '0']]
        self.assertEqual(connect_boundaries(rows, 60000)[0][-1], 1 + len(reply))

    @unittest.skipUnless(executable('tshark'), 'Wireshark is required for integration test')
    def test_real_tshark_handles_fragmented_connect_and_mixed_response(self):
        # Tiny synthetic IPv4/TCP capture: split CONNECT, response plus TLS,
        # then client TLS. Only the two nine-byte TLS pieces should survive.
        request = b'CONNECT example.org:443 HTTP/1.1\r\nHost: example.org\r\n\r\n'
        reply = b'HTTP/1.1 200 Connection Established\r\n\r\n'
        tls = b'\x16\x03\x03\x00\x04\x01\x00\x00\x00'
        packets = []
        def packet(src, dst, seq, ack, flags, data=b''):
            tcp = struct.pack('!HHIIBBHHH', src, dst, seq, ack, 5 << 4, flags, 65535, 0, 0) + data
            ip = struct.pack('!BBHHHBBH4s4s', 0x45, 0, 20 + len(tcp), 0, 0, 64, 6, 0,
                             socket.inet_aton('127.0.0.1'), socket.inet_aton('127.0.0.1'))
            packets.append(ip + tcp)
        packet(50000, 60000, 1000, 0, 2)
        packet(60000, 50000, 9000, 1001, 18)
        packet(50000, 60000, 1001, 9001, 16)
        packet(50000, 60000, 1001, 9001, 24, request[:20])
        packet(50000, 60000, 1021, 9001, 24, request[20:])
        packet(60000, 50000, 9001, 1001 + len(request), 24, reply + tls)
        packet(50000, 60000, 1001 + len(request), 9001 + len(reply) + len(tls), 24, tls)
        with tempfile.TemporaryDirectory() as directory:
            capture = Path(directory) / 'synthetic.pcap'
            with capture.open('wb') as stream:
                stream.write(struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 101))
                for i, raw in enumerate(packets):
                    stream.write(struct.pack('<IIII', 100, i * 1000, len(raw), len(raw)))
                    stream.write(raw)
            result, _ = extract_capture(capture, 60000)
        np.testing.assert_array_equal(result['size'], [9, 9])
        np.testing.assert_array_equal(result['direction'], [-1, 1])


class FeatureChecks(unittest.TestCase):
    def test_numerical_counts_directions_and_bursts(self):
        vector = feature_vector(trace())
        self.assertEqual(vector['all_bytes'], 1450)
        self.assertEqual(vector['out_bytes'], 350)
        self.assertEqual(vector['in_packets'], 2)
        self.assertEqual(vector['out_bursts'], 2)
        self.assertEqual(vector['out_burst_packets_max'], 2)
        self.assertAlmostEqual(vector['in_iat_mean'], .006)
        self.assertTrue(all(np.isfinite(list(vector.values()))))

    def test_flow_ids_and_absolute_time_cannot_be_learned(self):
        original = trace()
        changed = {key: value.copy() for key, value in original.items()}
        changed['flow'] += 8000
        changed['time'] += 10000
        a, b = feature_vector(original), feature_vector(changed)
        self.assertEqual(list(a), list(b))
        np.testing.assert_allclose(list(a.values()), list(b.values()), atol=1e-10)
        self.assertFalse(any(s in key for key in a for s in ('port', 'host', 'site', 'flow', 'visit', 'date')))

    def test_ambiguous_or_unknown_split_rejected(self):
        with self.assertRaises(ValueError):
            split_for('day1', {'train': ['day1'], 'test': ['day1']})
        with self.assertRaises(ValueError):
            split_for('day2', {'train': ['day1']})


if __name__ == '__main__':
    unittest.main()
