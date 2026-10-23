import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import platform
import os
import datetime

import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--upstream',type=Path,required=True)
parser.add_argument('--corpus',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
SDK=Path(__file__).resolve().parents[1]
UP=args.upstream.resolve()
sys.path.insert(0,str(SDK))
from officeparse import Limits,to_text
from officeparse.core import parse_local
from reference import references,norm

loader=(UP/'node_modules/tsx/dist/loader.mjs').as_uri()
node=['node','--import',loader,str(SDK/'benchmarks/upstream_worker.mjs'),str(UP)]
flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
worker=subprocess.Popen(node,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',creationflags=flags)
assert json.loads(worker.stdout.readline())['ready']
corpus=json.loads((args.corpus/'manifest.json').read_text(encoding='utf-8'))
rows=[]
try:
    for item in corpus:
        def original():
            worker.stdin.write(json.dumps({'path':item['path']})+'\n');worker.stdin.flush()
            return json.loads(worker.stdout.readline())
        original();parse_local(item['path'],Limits())
        original_times=[];candidate_times=[]
        for index in range(7):
            if index%2==0:
                upstream=original();original_times.append(upstream['ms'])
            start=time.perf_counter();candidate=parse_local(item['path'],Limits())
            candidate_times.append((time.perf_counter()-start)*1000)
            if index%2:
                upstream=original();original_times.append(upstream['ms'])
        refs,method=references(item)
        metrics={}
        for which,text,ok,times in [('upstream',upstream['result'].get('text',''),upstream['result']['ok'],original_times),('candidate',to_text(candidate['document']) if candidate['ok'] else '',candidate['ok'],candidate_times)]:
            normalized=norm(text);hits=sum(ref in normalized for ref in refs)
            metrics[which]={'ok':ok,'spans_found':hits,'spans_total':len(refs),'span_recall':hits/len(refs) if refs else None,'warm_median_ms':statistics.median(times),'warm_samples_ms':times}
        rows.append({**{k:v for k,v in item.items() if k!='path'},'reference_method':method,**metrics})
        print(item['id'],metrics['upstream']['spans_found'],metrics['candidate']['spans_found'],round(metrics['upstream']['warm_median_ms'],2),round(metrics['candidate']['warm_median_ms'],2),flush=True)
finally:
    worker.stdin.close();worker.wait(timeout=15)
result={'measured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'platform':platform.platform(),'python':platform.python_version(),'node':subprocess.check_output(['node','--version'],text=True).strip(),'upstream_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=UP,text=True).strip(),
        'metric':'unique normalized reference span presence recall; not full accuracy, order, duplication, or precision',
        'method':'One warmed Node process and one CPython process; alternating execution order per document; seven runs each; both include file read. Candidate returns IR and checks JSON output budget. Installation complete before measurement. No browser/WASM timing implied.',
        'documents':rows}
dest=args.output.parent;dest.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
total=sum(r['upstream']['spans_total'] for r in rows)
summary={'files':len(rows),'reference_spans':total,'upstream_found':sum(r['upstream']['spans_found'] for r in rows),'candidate_found':sum(r['candidate']['spans_found'] for r in rows),'upstream_sum_medians_ms':sum(r['upstream']['warm_median_ms'] for r in rows),'candidate_sum_medians_ms':sum(r['candidate']['warm_median_ms'] for r in rows)}
(dest/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(summary)
