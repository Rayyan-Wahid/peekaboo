"""Date-held-out Random Forest baseline and a predeclared jitter comparison."""
from collections import Counter
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import platform
import re

import joblib
import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

from .defense import jitter_trace
from .features import (VERSION, accepted_rows, extract_capture, feature_vector, file_hash,
                       load_config, load_trace, write_json)


def schema_names():
    template = {'time': np.array([0., 1.]), 'size': np.array([1, 1]),
                'direction': np.array([1, -1])}
    return list(feature_vector(template))


def load_dataset(root):
    root = Path(root)
    folder = root / 'data/processed/analysis-v1'
    manifest = json.loads((folder / 'dataset.json').read_text())
    config = load_config(root)
    if manifest['version'] != VERSION or manifest['config'] != config:
        raise ValueError('Extraction version/config changed; run extract again')
    for filename, key in [('features.csv', 'features_sha256'), ('visits.jsonl', 'visits_sha256')]:
        if file_hash(folder / filename) != manifest[key]:
            raise ValueError(f'{filename} differs from extraction manifest')
    if file_hash(root / 'data/processed/accepted-visits.jsonl') != manifest['accepted_index_sha256']:
        raise ValueError('Accepted input index changed; run extract again')
    names = (folder / 'features.csv').read_text().splitlines()[0].split(',')
    if names != schema_names() or names != manifest['features']:
        raise ValueError('Feature columns violate the metadata allowlist')
    rows = [json.loads(line) for line in (folder / 'visits.jsonl').read_text().splitlines()]
    expected = accepted_rows(root, config)
    if len(rows) != len(expected) or any(any(row[k] != reference[k] for k in row)
                                       for row, reference in zip(rows, expected)):
        raise ValueError('Feature row identities/splits differ from accepted input order')
    matrix = np.loadtxt(folder / 'features.csv', delimiter=',', skiprows=1, ndmin=2)
    if matrix.shape != (len(rows), len(names)) or not np.isfinite(matrix).all():
        raise ValueError('Invalid feature matrix shape or nonfinite values')
    labels = np.asarray([r['site_id'] for r in rows])
    split = {name: np.asarray([i for i, r in enumerate(rows) if r['split'] == name])
             for name in ('train', 'validation', 'test')}
    return folder, manifest, rows, matrix, labels, split


def metrics(actual, predicted, classes):
    return {'accuracy': float(accuracy_score(actual, predicted)),
            'macro_f1': float(f1_score(actual, predicted, labels=classes, average='macro', zero_division=0)),
            'samples': len(actual),
            'per_class': classification_report(actual, predicted, labels=classes,
                                               output_dict=True, zero_division=0),
            'confusion_matrix': confusion_matrix(actual, predicted, labels=classes).tolist()}


def forest(config, leaf):
    return RandomForestClassifier(n_estimators=config['n_estimators'],
        min_samples_leaf=leaf, max_features='sqrt', class_weight='balanced_subsample',
        random_state=config['seed'], n_jobs=config['jobs'])


def select_baseline(matrix, labels, split, config, classes):
    candidates = []
    best_model, best_key = None, None
    for leaf in config['min_samples_leaf_candidates']:
        model = forest(config, leaf)
        model.fit(matrix[split['train']], labels[split['train']])
        validation = metrics(labels[split['validation']], model.predict(matrix[split['validation']]), classes)
        candidates.append({'min_samples_leaf': leaf, 'validation_accuracy': validation['accuracy'],
                           'validation_macro_f1': validation['macro_f1']})
        key = (validation['macro_f1'], validation['accuracy'], leaf)
        if best_key is None or key > best_key:
            best_model, best_key = model, key
    return best_model, candidates


def model_bundle(model, names, config, source_manifest, condition):
    return {'model': model, 'features': names, 'extractor_version': VERSION,
            'window_seconds': config['features']['window_seconds'], 'condition': condition,
            'accepted_index_sha256': source_manifest['accepted_index_sha256'],
            'split': config['split'], 'classes': list(model.classes_)}


def write_summary(report, report_dir):
    baseline = report['baseline']['test']
    correct = sum(p['actual'] == p['predicted'] for p in report['baseline_test_predictions'])
    text = [
        '# Peekaboo experiment results', '',
        f"Run: {report['run_name']}. Completed UTC: {report.get('completed_utc', 'pending')}.", '',
        f"Baseline Random Forest: **{baseline['accuracy']:.2%} test accuracy** "
        f"({correct}/{baseline['samples']} correct), **{baseline['macro_f1']:.4f} macro F1**.", '',
        f"Validation macro F1: {report['baseline']['validation']['macro_f1']:.4f}. "
        f"Selected minimum leaf size: {report['selection']['selected_min_samples_leaf']}.", '',
        f"Training/validation/test: {report['split_counts']['train']}/"
        f"{report['split_counts']['validation']}/{report['split_counts']['test']}; "
        f"{report['feature_count']} numerical features; {len(report['classes'])} known sites.", '',
        f"Majority-class test accuracy: {report['dummy']['most_frequent']['accuracy']:.2%}. "
        f"Observed seeded uniform-guess accuracy: {report['dummy']['uniform']['accuracy']:.2%}; expected 5%.", '',
        '## Simulated jitter comparison', '',
        'Nonzero rows average three seeds. These are test results for a predeclared grid, not test-selected settings.', '',
        '| Delay bound | Original accuracy | Retrained accuracy | Original macro F1 | Retrained macro F1 | Mean packet delay |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for bound in report['config']['defense']['max_delay_ms']:
        runs = [r for r in report['defense'] if r['max_delay_ms'] == bound]
        fixed = np.mean([r['fixed']['test']['accuracy'] for r in runs])
        adaptive = np.mean([r['adaptive']['test']['accuracy'] for r in runs])
        fixed_f1 = np.mean([r['fixed']['test']['macro_f1'] for r in runs])
        adaptive_f1 = np.mean([r['adaptive']['test']['macro_f1'] for r in runs])
        delay = np.mean([r['test_simulated_costs']['mean_packet_delay_ms'] for r in runs])
        text.append(f'| {bound} ms | {fixed:.2%} | {adaptive:.2%} | {fixed_f1:.4f} | {adaptive_f1:.4f} | {delay:.2f} ms |')
    text += ['', '## Interpretation and limits', '',
        'Judge privacy by the measured recognition rates, including the retrained model. '
        'Do not describe timing jitter as effective simply because it was implemented.', '',
        *['- ' + limitation for limitation in report['limitations']], '',
        'Detailed per-class metrics, confusion matrices, predictions, package versions, and validation '
        'candidates are in `results.json`. `locked-protocol.json` records choices before test scoring.', '']
    (Path(report_dir) / 'SUMMARY.md').write_text('\n'.join(text), encoding='utf-8')


def run_experiment(root, run_name='experiment-v1'):
    root = Path(root).resolve()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', run_name):
        raise ValueError('Run name must contain only letters, numbers, hyphens, and underscores')
    folder, manifest, rows, matrix, labels, split = load_dataset(root)
    config, names = manifest['config'], manifest['features']
    classes = sorted(set(labels))
    report_dir, model_dir = root / 'reports' / run_name, root / 'models' / run_name
    if report_dir.exists() or model_dir.exists():
        raise FileExistsError('Run already exists. Use a new run name; preserve prior evaluation results.')
    report_dir.mkdir(parents=True)
    model_dir.mkdir(parents=True)
    report = {'status': 'running', 'started_utc': datetime.now(timezone.utc).isoformat(),
        'run_name': run_name, 'config': config, 'classes': classes, 'feature_count': len(names),
        'source_dataset': manifest,
        'split_counts': {name: len(indices) for name, indices in split.items()},
        'class_counts': {name: dict(Counter(labels[indices])) for name, indices in split.items()},
        'versions': {name: version(name) for name in ('numpy', 'pandas', 'scikit-learn', 'joblib', 'streamlit')},
        'python': platform.python_version(),
        'limitations': [
            'Closed-world 20-site, fixed-window, fresh-profile loopback TCP experiment.',
            'Only four collection dates; test classes have small and unequal counts.',
            'Jitter is a timestamp simulation, not a measured live-network defense.',
            'No browser feedback, retransmission changes, or actual page-load delay are simulated.',
            'Byte overhead is zero by construction; raw bytes and packet counts are retained.',
            'Per-flow/direction order is preserved; cross-direction causal dependencies are not modeled.',
            'Test results do not select hyperparameters or jitter bounds.',
            'Seed variation is simulation variability, not a confidence interval for new websites/days.'
        ]}
    write_json(report_dir / 'results.json', report)
    # Lock model choice using training/validation only, before evaluating any test scores.
    baseline, candidates = select_baseline(matrix, labels, split, config['model'], classes)
    report['selection'] = {'criterion': 'validation macro F1, then accuracy, then larger leaf',
        'candidates': candidates, 'selected_min_samples_leaf': baseline.min_samples_leaf,
        'adaptive_policy': 'Same baseline-selected hyperparameters, refit on defended training data only.'}
    write_json(report_dir / 'locked-protocol.json', {'config': config, 'selection': report['selection'],
        'source_dataset_sha256': file_hash(folder / 'dataset.json'), 'test_accessed': False})
    joblib.dump(model_bundle(baseline, names, config, manifest, 'baseline'), model_dir / 'baseline.joblib', compress=3)
    report['baseline'] = {name: metrics(labels[split[name]], baseline.predict(matrix[split[name]]), classes)
                          for name in ('validation', 'test')}
    report['dummy'] = {}
    for strategy in ('most_frequent', 'uniform'):
        dummy = DummyClassifier(strategy=strategy, random_state=config['model']['seed'])
        dummy.fit(matrix[split['train']], labels[split['train']])
        report['dummy'][strategy] = metrics(labels[split['test']], dummy.predict(matrix[split['test']]), classes)
    report['uniform_guess_expected_accuracy'] = 1 / len(classes)
    report['feature_importance'] = sorted(
        [{'feature': name, 'importance': float(value)} for name, value in zip(names, baseline.feature_importances_)],
        key=lambda row: row['importance'], reverse=True)
    baseline_pred = baseline.predict(matrix[split['test']])
    report['baseline_test_predictions'] = [
        {'visit_id': rows[i]['visit_id'], 'actual': str(labels[i]), 'predicted': str(predicted)}
        for i, predicted in zip(split['test'], baseline_pred)]
    print(f"Baseline: validation F1={report['baseline']['validation']['macro_f1']:.3f}; "
          f"test accuracy={report['baseline']['test']['accuracy']:.3f}", flush=True)
    traces = []
    for row in rows:
        path = folder / 'traces' / (row['visit_id'] + '.npz')
        metadata = json.loads(path.with_suffix('.json').read_text())
        if file_hash(path) != metadata['trace_sha256'] or metadata['key']['sha256'] != row['sha256']:
            raise ValueError('Cached trace integrity mismatch')
        traces.append(load_trace(path))
    report['defense'] = []
    for bound in config['defense']['max_delay_ms']:
        seeds = config['defense']['seeds'] if bound else config['defense']['seeds'][:1]
        for seed in seeds:
            defended_matrix, costs = [], []
            for row, trace in zip(rows, traces):
                defended, cost = jitter_trace(trace, bound, seed, row['sha256'])
                vector = feature_vector(defended)
                defended_matrix.append([vector[name] for name in names])
                costs.append(cost)
            defended_matrix = np.asarray(defended_matrix)
            if bound == 0:
                if not np.allclose(matrix, defended_matrix, rtol=1e-12, atol=1e-12):
                    raise ValueError('Zero-jitter control does not reproduce baseline features')
                adaptive = baseline
            else:
                adaptive = forest(config['model'], baseline.min_samples_leaf)
                adaptive.fit(defended_matrix[split['train']], labels[split['train']])
            outcome = {'max_delay_ms': bound, 'seed': seed, 'fixed': {}, 'adaptive': {}}
            for name in ('validation', 'test'):
                idx = split[name]
                outcome['fixed'][name] = metrics(labels[idx], baseline.predict(defended_matrix[idx]), classes)
                outcome['adaptive'][name] = metrics(labels[idx], adaptive.predict(defended_matrix[idx]), classes)
            outcome['test_simulated_costs'] = {
                key: float(np.mean([costs[i][key] for i in split['test']])) for key in costs[0]}
            outcome['cost_aggregation'] = 'Mean across test traces, including mean of each trace p95/max.'
            report['defense'].append(outcome)
            if seed == config['defense']['seeds'][0] and bound:
                joblib.dump(model_bundle(adaptive, names, config, manifest,
                    {'simulation_max_delay_ms': bound, 'seed': seed}),
                    model_dir / f'adaptive-{bound}ms.joblib', compress=3)
            write_json(report_dir / 'results.json', report)
            print(f"Jitter {bound} ms seed {seed}: fixed test={outcome['fixed']['test']['accuracy']:.3f}, "
                  f"adaptive test={outcome['adaptive']['test']['accuracy']:.3f}", flush=True)
    report['status'] = 'complete'
    report['completed_utc'] = datetime.now(timezone.utc).isoformat()
    write_json(report_dir / 'results.json', report)
    write_summary(report, report_dir)
    write_json(root / 'reports/latest.json', {'run_name': run_name})
    return report_dir


def predict_capture(capture, proxy_port, model_path):
    # Only locally created, trusted joblib files should be loaded.
    saved = joblib.load(model_path)
    if saved['extractor_version'] != VERSION or saved['features'] != schema_names():
        raise ValueError('Model uses an incompatible extractor/schema')
    if saved['condition'] != 'baseline':
        raise ValueError('Fresh captures require the baseline model; adaptive models expect simulated features')
    trace, diagnostic = extract_capture(capture, proxy_port, saved['window_seconds'])
    vector = feature_vector(trace)
    values = np.asarray([[vector[name] for name in saved['features']]])
    scores = saved['model'].predict_proba(values)[0]
    ranked = sorted(zip(saved['classes'], scores), key=lambda x: x[1], reverse=True)
    return {'prediction': ranked[0][0],
            'top_three': [{'site': str(site), 'forest_score': float(score)} for site, score in ranked[:3]],
            'scope': 'Prediction among the 20 known sites; scores are not calibrated confidence.',
            'diagnostic': diagnostic}
