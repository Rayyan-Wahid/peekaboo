"""Metadata features from TCP bytes after successful CONNECT handshakes.

Header payloads are inspected only to locate byte boundaries, never saved or
used as features. Reassembled TLS display filters would miss TCP fragments.
"""
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tomllib

import numpy as np

from .collect import executable

VERSION = 'tcp-after-connect-v1'
STAT_NAMES = ('mean', 'std', 'min', 'p25', 'median', 'p75', 'p90', 'max')


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def load_config(root):
    return tomllib.loads((Path(root) / 'configs/analysis.toml').read_text(encoding='utf-8'))


def split_for(date, split):
    matches = [name for name, dates in split.items() if date in dates]
    if len(matches) != 1:
        raise ValueError(f'Date {date} must belong to exactly one split')
    return matches[0]


def accepted_rows(root, config):
    root = Path(root).resolve()
    index = root / 'data/processed/accepted-visits.jsonl'
    summary = json.loads((root / 'data/processed/dataset-summary.json').read_text())
    if file_hash(index) != summary['allowlist_sha256']:
        raise ValueError('Accepted index checksum differs from audited dataset summary')
    rows = [json.loads(line) for line in index.read_text().splitlines() if line.strip()]
    if len(rows) != summary['accepted_total']:
        raise ValueError('Accepted index count differs from dataset summary')
    for key in ('visit_id', 'capture', 'sha256'):
        if len({r[key] for r in rows}) != len(rows):
            raise ValueError(f'Duplicate accepted {key}')
    for row in rows:
        (root / row['capture']).resolve().relative_to(root / 'data/raw')
        if row['condition'] != 'baseline' or row['split_group'] != row['session_id'][:8]:
            raise ValueError('Unexpected accepted condition or date')
        row['split'] = split_for(row['split_group'], config['split'])
    classes = set(summary['per_site'])
    for name in ('train', 'validation', 'test'):
        if {r['site_id'] for r in rows if r['split'] == name} != classes:
            raise ValueError(f'{name} does not contain all classes')
    return rows


def tshark_table(capture, port, display_filter, fields):
    tshark = executable('tshark')
    if not tshark:
        raise RuntimeError('tshark is required for capture extraction')
    args = [tshark, '-n', '-2', '-r', str(capture), '-d', f'tcp.port=={int(port)},http',
            '-o', 'tcp.relative_sequence_numbers:TRUE', '-o', 'tls.keylog_file:',
            '-Y', display_filter, '-T', 'fields', '-E', 'separator=/t',
            '-E', 'occurrence=f']
    for field in fields:
        args.extend(['-e', field])
    env = dict(os.environ)
    env.pop('SSLKEYLOGFILE', None)
    result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=180, env=env,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError('tshark extraction failed: ' + result.stderr.strip()[:500])
    return csv.reader(io.StringIO(result.stdout), delimiter='\t', quoting=csv.QUOTE_NONE)


def connect_boundaries(header_rows, port):
    """End sequence number of each plaintext request/response, including splits."""
    requests, responses = {}, {}
    header_rows = list(header_rows)
    requested_streams = {int(fields[0]) for fields in header_rows if fields[4] == 'CONNECT'}
    for fields in header_rows:
        stream, src, seq, payload, method, response = fields[:6]
        if int(stream) not in requested_streams:
            # Existing connections can be partially captured and dissected as HTTP
            # on a later ACK. Without their CONNECT request they cannot be retained.
            continue
        raw = bytes.fromhex(payload.replace(':', ''))
        end = raw.find(b'\r\n\r\n')
        start_sequence = int(seq)
        if end < 0 and len(fields) >= 8 and fields[6]:
            raw = bytes.fromhex(fields[6].replace(':', ''))
            start_sequence = int(seq) + int(fields[7]) - len(raw)
            end = raw.find(b'\r\n\r\n')
        if end < 0:
            raise ValueError('Cannot locate CONNECT header end; refusing ambiguous extraction')
        boundary = start_sequence + end + 4
        stream, src = int(stream), int(src)
        if method == 'CONNECT' and src != port:
            requests[stream] = min(boundary, requests.get(stream, boundary))
        elif response == '200' and src == port:
            responses[stream] = min(boundary, responses.get(stream, boundary))
    return {stream: {1: requests[stream], -1: responses[stream]}
            for stream in requests.keys() & responses.keys()}


def select_packets(packet_rows, boundaries, port, window_seconds):
    """Retain observed TLS-stream payload bytes, including retransmissions.

Pure ACK/SYN/FIN frames and incomplete tunnels are excluded. A segment that
straddles a CONNECT boundary contributes only the bytes beyond that boundary.
"""
    selected = []
    excluded = 0
    for fields in packet_rows:
        timestamp, stream, src, dst, sequence, length = fields
        stream, src, dst, sequence, length = map(int, (stream, src, dst, sequence, length))
        if src != port and dst != port:
            excluded += 1
            continue
        direction = -1 if src == port else 1
        if stream not in boundaries:
            excluded += 1
            continue
        size = max(0, sequence + length - max(sequence, boundaries[stream][direction]))
        if size:
            selected.append((float(timestamp), size, direction, stream))
    if not selected:
        raise ValueError('No TLS-stream payload after complete successful CONNECT exchanges')
    selected.sort(key=lambda x: x[0])
    array = np.asarray(selected, dtype=np.float64)
    array[:, 0] -= array[0, 0]
    outside = int(np.sum(array[:, 0] >= window_seconds))
    array = array[array[:, 0] < window_seconds]
    if len(array) < 2 or set(array[:, 2]) != {-1, 1}:
        raise ValueError('Need bidirectional payload in the observation window')
    trace = {'time': array[:, 0], 'size': array[:, 1].astype(np.int64),
             'direction': array[:, 2].astype(np.int8), 'flow': array[:, 3].astype(np.int32)}
    return trace, {'successful_tunnels': len(boundaries), 'unmapped_payload_packets': excluded,
                   'outside_window_packets': outside, 'selected_packets': len(array),
                   'selected_bytes': int(trace['size'].sum()),
                   'observed_span_seconds': float(trace['time'][-1])}


def extract_capture(capture, port, window_seconds=20.0):
    headers = tshark_table(capture, port,
        'http.request.method == "CONNECT" || http.response.code == 200',
        ['tcp.stream', 'tcp.srcport', 'tcp.seq', 'tcp.payload', 'http.request.method',
         'http.response.code', 'tcp.reassembled.data', 'tcp.len'])
    boundaries = connect_boundaries(headers, port)
    packets = tshark_table(capture, port, f'tcp.port == {int(port)} && tcp.len > 0',
        ['frame.time_epoch', 'tcp.stream', 'tcp.srcport', 'tcp.dstport', 'tcp.seq', 'tcp.len'])
    return select_packets(packets, boundaries, port, window_seconds)


def statistics(values):
    values = np.asarray(values, dtype=float)
    if not len(values):
        return np.zeros(len(STAT_NAMES))
    return np.r_[values.mean(), values.std(), np.percentile(values, [0, 25, 50, 75, 90, 100])]


def feature_vector(trace):
    """Explicit metadata allowlist. No label, date, flow ID, port, or path enters X."""
    times, sizes, directions = (np.asarray(trace[k]) for k in ('time', 'size', 'direction'))
    if not len(times) or not np.isfinite(times).all() or (np.diff(times) < 0).any():
        raise ValueError('Trace timestamps must be finite, ordered, and nonempty')
    if (sizes <= 0).any() or not set(directions).issubset({-1, 1}):
        raise ValueError('Invalid payload sizes or directions')
    features = {}
    def stats(prefix, values):
        features.update(zip((prefix + '_' + name for name in STAT_NAMES), statistics(values)))
    features['duration'] = float(times[-1] - times[0])
    for name, mask in [('all', np.ones(len(times), dtype=bool)),
                       ('out', directions == 1), ('in', directions == -1)]:
        features[name + '_packets'] = int(mask.sum())
        features[name + '_bytes'] = int(sizes[mask].sum())
        stats(name + '_size', sizes[mask])
        stats(name + '_iat', np.diff(times[mask]))
    features['out_packet_fraction'] = float(np.mean(directions == 1))
    features['out_byte_fraction'] = float(sizes[directions == 1].sum() / sizes.sum())
    # A burst is a maximal consecutive run in the merged, time-ordered trace.
    starts = np.r_[0, np.flatnonzero(directions[1:] != directions[:-1]) + 1]
    stops = np.r_[starts[1:], len(times)]
    counts = stops - starts
    byte_totals = np.add.reduceat(sizes, starts)
    durations = times[stops - 1] - times[starts]
    for name, direction in [('out', 1), ('in', -1)]:
        mask = directions[starts] == direction
        features[name + '_bursts'] = int(mask.sum())
        stats(name + '_burst_packets', counts[mask])
        stats(name + '_burst_bytes', byte_totals[mask])
        stats(name + '_burst_duration', durations[mask])
    return {key: float(value) for key, value in features.items()}


def load_trace(path):
    with np.load(path, allow_pickle=False) as saved:
        return {key: saved[key] for key in ('time', 'size', 'direction', 'flow')}


def extract_dataset(root, workers=None):
    root = Path(root).resolve()
    config = load_config(root)
    rows = accepted_rows(root, config)
    output = root / 'data/processed/analysis-v1'
    cache = output / 'traces'
    cache.mkdir(parents=True, exist_ok=True)
    window = config['features']['window_seconds']
    tshark_version = subprocess.check_output([executable('tshark'), '--version'], text=True).splitlines()[0]
    failures, successful, features, diagnostics = [], [], [], []

    def process(row):
        try:
            capture = root / row['capture']
            if file_hash(capture) != row['sha256']:
                raise ValueError('Capture hash mismatch')
            key = {'version': VERSION, 'sha256': row['sha256'], 'proxy_port': row['proxy_port'],
                   'window_seconds': window, 'tshark': tshark_version}
            stem = cache / row['visit_id']
            cached_metadata = stem.with_suffix('.json')
            npz = stem.with_suffix('.npz')
            metadata = json.loads(cached_metadata.read_text()) if cached_metadata.exists() else {}
            if npz.exists() and metadata.get('key') == key and metadata.get('trace_sha256') == file_hash(npz):
                trace, diagnostic = load_trace(npz), metadata['diagnostic']
            else:
                trace, diagnostic = extract_capture(capture, row['proxy_port'], window)
                np.savez_compressed(npz, **trace)
                write_json(cached_metadata, {'key': key, 'diagnostic': diagnostic, 'trace_sha256': file_hash(npz)})
            return row, feature_vector(trace), diagnostic, None
        except Exception as error:
            return row, None, None, f'{type(error).__name__}: {error}'

    with ThreadPoolExecutor(max_workers=workers or config['features']['workers']) as pool:
        for i, (row, vector, diagnostic, error) in enumerate(pool.map(process, rows), 1):
            if error:
                failures.append({'visit_id': row['visit_id'], 'error': error})
            else:
                successful.append(row)
                features.append(vector)
                diagnostics.append({'visit_id': row['visit_id'], **diagnostic})
            if i % 25 == 0 or i == len(rows):
                print(f'Extracted {i}/{len(rows)}; failures={len(failures)}', flush=True)
    write_json(output / 'extraction-audit.json', {'version': VERSION, 'tshark': tshark_version,
               'accepted': len(rows), 'extracted': len(successful), 'failures': failures, 'traces': diagnostics})
    if failures:
        raise RuntimeError(f'{len(failures)} accepted traces failed extraction; training is blocked. See extraction-audit.json')
    with (output / 'features.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(features[0]))
        writer.writeheader()
        writer.writerows(features)
    metadata_rows = [{k: r[k] for k in ('visit_id', 'site_id', 'session_id', 'split_group', 'split', 'sha256')}
                     for r in successful]
    (output / 'visits.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in metadata_rows), encoding='utf-8')
    write_json(output / 'dataset.json', {'version': VERSION, 'rows': len(rows),
        'features': list(features[0]), 'config': config,
        'accepted_index_sha256': file_hash(root / 'data/processed/accepted-visits.jsonl'),
        'features_sha256': file_hash(output / 'features.csv'),
        'visits_sha256': file_hash(output / 'visits.jsonl')})
    return output
