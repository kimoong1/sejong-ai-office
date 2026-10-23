"""Reproducible synthetic benchmark. Does not compare speed with upstream."""
import json
from pathlib import Path
import platform
import statistics
import sys
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from officeparse import parse_bytes, parse_file
from tests.fixtures import archive, docx, paragraph, pptx, xlsx, hwpx


def main():
    cases = {'docx_1000_paragraphs': archive(docx(''.join(paragraph(f'문단 {i} 02139 본문') for i in range(1000)))),
             'xlsx_sparse': archive(xlsx()), 'pptx_order': archive(pptx()), 'hwpx_table': archive(hwpx())}
    report = {'python': platform.python_version(), 'platform': platform.platform(),
              'method': '5 warm in-process runs; tracemalloc once separately; no upstream comparison; traced Python allocations are not process RSS', 'cases': {}}
    for name, data in cases.items():
        timings = []
        for _ in range(5):
            start = time.perf_counter()
            result = parse_bytes(data, name)
            timings.append((time.perf_counter() - start) * 1000)
            assert result['ok'], result
        tracemalloc.start()
        parse_bytes(data, name)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        report['cases'][name] = {'input_bytes': len(data), 'p50_ms': round(statistics.median(timings), 3),
            'max_ms': round(max(timings), 3), 'python_traced_peak_bytes': peak,
            'blocks': result['document']['metrics']['blocks']}
    dest = Path(__file__).resolve().parents[1] / 'validation'
    dest.mkdir(exist_ok=True)
    (dest / 'benchmark.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
