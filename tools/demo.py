"""Generate owned fixtures and exports; run from the SDK directory."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from officeparse import parse_file, to_chunks, to_text
from tests.fixtures import archive, docx, hwpx, pptx, xlsx


def main():
    dest = Path(__file__).resolve().parents[1] / 'examples'
    dest.mkdir(exist_ok=True)
    for fmt, build in [('docx', docx), ('xlsx', xlsx), ('pptx', pptx), ('hwpx', hwpx)]:
        path = dest / f'sample.{fmt}'
        path.write_bytes(archive(build()))
        result = parse_file(path)
        if not result['ok']:
            raise RuntimeError(result)
        (dest / f'{fmt}.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        (dest / f'{fmt}.txt').write_text(to_text(result['document']), encoding='utf-8')
        (dest / f'{fmt}.chunks.json').write_text(json.dumps(to_chunks(result['document']), ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'{fmt}: example and exports ready')


if __name__ == '__main__':
    main()
