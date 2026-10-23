"""Measure development-runtime process startup plus extraction on four files."""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import os

parser=argparse.ArgumentParser()
parser.add_argument('--upstream',type=Path,required=True)
parser.add_argument('--corpus',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
node=['node','--import',(args.upstream.resolve()/'node_modules/tsx/dist/loader.mjs').as_uri(),str(root/'benchmarks/upstream_worker.mjs'),str(args.upstream.resolve())]
env=os.environ.copy();env['PYTHONPATH']=str(root);env['PYTHONIOENCODING']='utf-8'
flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
names=['calibre-demo.docx','port-lineup.xlsx','title-table-zone-fill.hwpx','01_standard_business.pptx']
rows=[]
for name in names:
    path=str((args.corpus/name).resolve())
    times={'upstream':[],'candidate':[]}
    for trial in range(3):
        for which in (['upstream','candidate'] if trial%2==0 else ['candidate','upstream']):
            start=time.perf_counter()
            proc=subprocess.run(node+[path] if which=='upstream' else [sys.executable,'-m','officeparse._worker'],
                input=None if which=='upstream' else json.dumps({'path':path,'limits':{}}),text=True,encoding='utf-8',capture_output=True,timeout=45,env=env,creationflags=flags)
            elapsed=(time.perf_counter()-start)*1000
            result=json.loads(proc.stdout)
            if proc.returncode or not result['ok']:raise RuntimeError(which+' failed')
            times[which].append(elapsed)
    row={'id':name,**{key:{'samples_ms':value,'median_ms':statistics.median(value)} for key,value in times.items()}}
    rows.append(row);print(name,round(row['upstream']['median_ms'],2),round(row['candidate']['median_ms'],2),flush=True)
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps({'scope':'development source runtimes: Node includes tsx loader/imports; not packaged upstream Electron performance; three process starts per file; OS caches not evicted','documents':rows},indent=2),encoding='utf-8')
