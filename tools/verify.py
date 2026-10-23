"""Save a reproducible test report. Optional external corpus paths are not bundled."""
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from officeparse import parse_file


def main():
    dest = ROOT / 'validation'
    dest.mkdir(exist_ok=True)
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), top_level_dir=str(ROOT))
    start = time.perf_counter()
    with (dest / 'tests.txt').open('w', encoding='utf-8') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    report = {'python': platform.python_version(), 'tests_run': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors),
              'elapsed_seconds': round(time.perf_counter() - start, 3), 'external_corpus': []}
    for arg in sys.argv[1:]:
        path = Path(arg)
        parsed = parse_file(path)
        entry = {'name': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'ok': parsed['ok']}
        if parsed['ok']:
            doc = parsed['document']
            entry.update(format=doc['format'], blocks=doc['metrics']['blocks'], diagnostics=[d['code'] for d in doc['diagnostics']])
        else:
            entry['error'] = parsed['error']
        report['external_corpus'].append(entry)
    (dest / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() and all(x['ok'] for x in report['external_corpus']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
