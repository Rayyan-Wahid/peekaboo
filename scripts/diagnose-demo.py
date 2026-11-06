"""Read-only model/data comparison for a fresh visit; never refit the classifier."""
import json
from pathlib import Path

import joblib
import numpy as np

from peekaboo.experiment import load_dataset
from peekaboo.features import extract_capture, feature_vector, write_json

root = Path(__file__).resolve().parents[1]
report = json.loads((root / 'reports/fresh-demo/latest.json').read_text())
session = Path(report['session'])
fresh_record = json.loads((session / 'manifest.jsonl').read_text().splitlines()[0])
folder, manifest, rows, matrix, labels, split = load_dataset(root)
bundle = joblib.load(report['model'])
names = bundle['features']

def recompute(row, capture):
    trace, diagnostic = extract_capture(capture, row['proxy_port'], bundle['window_seconds'])
    vector = feature_vector(trace)
    values = np.asarray([[vector[name] for name in names]])
    scores = bundle['model'].predict_proba(values)[0]
    return vector, values, scores, diagnostic

fresh_vector, _, fresh_scores, _ = recompute(fresh_record, session / fresh_record['capture'])
old_index = next(i for i, row in enumerate(rows)
                 if row['site_id'] == report['site_id'] and row['split'] == 'test')
old_row = rows[old_index]
accepted = [json.loads(line) for line in (root / 'data/processed/accepted-visits.jsonl').read_text().splitlines()]
old_input = next(row for row in accepted if row['visit_id'] == old_row['visit_id'])
_, old_values, old_scores, _ = recompute(old_input, root / old_input['capture'])
old_manifest = [json.loads(line) for line in (root / 'data/raw' / old_row['session_id'] / 'manifest.jsonl').read_text().splitlines()]
old_record = next(row for row in old_manifest if row['visit_id'] == old_row['visit_id'])
baseline = json.loads((root / 'reports/experiment-v1/results.json').read_text())
keys = list(dict.fromkeys([r['feature'] for r in baseline['feature_importance'][:10]] +
                         ['all_bytes', 'all_packets', 'in_bytes', 'in_packets', 'duration']))
comparison = []
train_indices = [i for i in split['train'] if labels[i] == report['site_id']]
test_indices = [i for i in split['test'] if labels[i] == report['site_id']]
for key in keys:
    col = names.index(key)
    train_values = matrix[train_indices, col]
    test_values = matrix[test_indices, col]
    comparison.append({'feature': key, 'fresh': fresh_vector[key],
        'site_train_min': float(train_values.min()), 'site_train_median': float(np.median(train_values)),
        'site_train_max': float(train_values.max()), 'site_test_median': float(np.median(test_values)),
        'outside_site_train_range': bool(fresh_vector[key] < train_values.min() or fresh_vector[key] > train_values.max())})
actual_index = list(bundle['classes']).index(report['site_id'])
diagnosis = {'fresh_visit_id': report['visit_id'],
    'actual_site': report['site_id'], 'fresh_predicted': str(bundle['classes'][int(fresh_scores.argmax())]),
    'fresh_actual_site_score': float(fresh_scores[actual_index]),
    'fresh_actual_site_rank': int(np.sum(fresh_scores > fresh_scores[actual_index]) + 1),
    'old_test_visit_id': old_row['visit_id'],
    'old_raw_reextraction_matches_saved_features': bool(np.allclose(old_values[0], matrix[old_index], rtol=1e-12, atol=1e-12)),
    'old_recomputed_prediction': str(bundle['classes'][int(old_scores.argmax())]),
    'old_actual_site_score': float(old_scores[actual_index]),
    'old_browser_version': old_record.get('browser_version'),
    'fresh_browser_version': fresh_record.get('browser_version'),
    'old_page_title': old_record.get('title'), 'fresh_page_title': fresh_record.get('title'),
    'comparison': comparison,
    'interpretation_limit': 'One fresh visit is not an accuracy estimate or proof of a specific distribution-shift cause.'}
write_json(root / 'reports/fresh-demo' / ('diagnosis-' + report['visit_id'] + '.json'), diagnosis)
print(json.dumps(diagnosis, indent=2))
