"""Build a static browser client around exactly the same Python engine."""
import datetime as dt
import base64
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
DIST=ROOT/'web/dist'


def main():
    DIST.mkdir(parents=True,exist_ok=True)
    for encoded in (ROOT/'web/samples').glob('*.b64'):
        target=DIST/'samples'/encoded.name.removesuffix('.b64')
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(base64.b64decode(encoded.read_text(encoding='ascii')))
    sources={p.name:p.read_text(encoding='utf-8') for p in (ROOT/'officeparse').glob('*.py')}
    # Browser only imports pure extraction/export. No process or thread helpers.
    sources['__init__.py']='from .core import parse_bytes\nfrom .export import to_chunks, to_text\nfrom .model import Limits\n'
    (DIST/'engine.json').write_text(json.dumps(sources,ensure_ascii=False),encoding='utf-8')
    if (ROOT/'validation/comparison.json').exists():
        data=json.loads((ROOT/'validation/comparison.json').read_text(encoding='utf-8'))
        (DIST/'benchmark.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    print('Browser engine bundle ready:', len(sources),'modules')


if __name__=='__main__':main()
