"""Check a new controlled visit and predict it without changing the frozen dataset."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess

from peekaboo.collect import executable
from peekaboo.experiment import predict_capture
from peekaboo.features import file_hash, write_json

parser = argparse.ArgumentParser()
parser.add_argument('--session', type=Path, required=True)
parser.add_argument('--model', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
session = args.session.resolve()
session.relative_to((root / 'data/demo').resolve())
records = [json.loads(line) for line in (session / 'manifest.jsonl').read_text().splitlines()]
if len(records) != 1:
    raise ValueError('Demo must contain exactly one recorded visit')
row = records[0]
report = {'kind': 'fresh_controlled_visit', 'recorded_utc': datetime.now(timezone.utc).isoformat(),
          'site_id': row['site_id'], 'visit_id': row['visit_id'], 'session': str(session),
          'model': str(args.model.resolve()), 'model_sha256': file_hash(args.model),
          'collection_status': row['status'], 'review_reasons': row.get('review_reasons', []),
          'visual_review': 'pending', 'used_for_training': False, 'quality_errors': []}
capture = session / row['capture']
if row['status'] != 'candidate':
    report['quality_errors'].append('Collection was not a candidate: ' + row.get('error', 'review flags'))
elif not capture.is_file() or file_hash(capture) != row.get('sha256'):
    report['quality_errors'].append('Capture is missing or hash differs from manifest')
else:
    check = subprocess.run([executable('capinfos'), '-c', str(capture)], capture_output=True,
                           text=True, timeout=60, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if check.returncode:
        report['quality_errors'].append('Capture structure check failed')
    log = capture.with_suffix('.capture.log').read_text(errors='replace')
    drops = re.search(r"Packets received/dropped on interface .*?:\s*(\d+)/(\d+)", log)
    if not drops or int(drops.group(2)):
        report['quality_errors'].append('Missing or nonzero capture-drop count')
    screenshot = capture.with_suffix('.png')
    if not screenshot.is_file() or not screenshot.stat().st_size:
        report['quality_errors'].append('Screenshot is missing')
    report['screenshot'] = str(screenshot)
    report['capture_sha256'] = row['sha256']
    report['page_title'] = row.get('title', '')
    report['navigation_response'] = row.get('navigation', {}).get('responseStatus')
    report['body_chars'] = row.get('body_chars')
    report['tls_frames'] = row.get('tls_frames')
if not report['quality_errors']:
    report['result'] = predict_capture(capture, row['proxy_port'], args.model)
    report['correct'] = report['result']['prediction'] == row['site_id']
write_json(session / 'prediction.json', report)
write_json(root / 'reports/fresh-demo/latest.json', report)
print(json.dumps(report, indent=2))
raise SystemExit(1 if report['quality_errors'] else 0)
