import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

parser=argparse.ArgumentParser()
parser.add_argument('--destination',type=Path,required=True)
args=parser.parse_args()
manifest=json.loads(Path(__file__).with_name('corpus-manifest.json').read_text(encoding='utf-8'))
args.destination.mkdir(parents=True,exist_ok=True)
local=[]
for item in manifest:
    url=item['source_url']
    if url.startswith('https://github.com/') and '/blob/' in url:
        url=url.replace('https://github.com/','https://raw.githubusercontent.com/',1).replace('/blob/','/',1)
    path=args.destination/item['id']
    if path.exists():
        data=path.read_bytes()
    else:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'SejongAI-Office-Benchmark/0.2'}),timeout=60) as response:
            data=response.read(20_000_001)
    if len(data)>20_000_000 or hashlib.sha256(data).hexdigest()!=item['sha256']:
        raise RuntimeError('Corpus hash mismatch: '+item['id'])
    path.write_bytes(data)
    local.append({**item,'path':str(path.resolve())})
(args.destination/'manifest.json').write_text(json.dumps(local,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'{len(local)} corpus files verified')
