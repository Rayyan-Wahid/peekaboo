"""Print local collection outcomes without displaying browsing metadata."""
import collections
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'data' / 'raw'
total = collections.Counter()
for manifest in sorted(root.glob('*/manifest.jsonl')):
    counts = collections.Counter()
    for line in manifest.read_text(encoding='utf-8').splitlines():
        counts[json.loads(line)['status']] += 1
    total.update(counts)
    print(manifest.parent.name, dict(counts))
print('Total:', dict(total))
print('Candidate traces require review; failed attempts are not training data.')
