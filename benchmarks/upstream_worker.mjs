import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { performance } from 'node:perf_hooks';
import { createInterface } from 'node:readline';

const { parseFileToText } = await import(pathToFileURL(resolve(process.argv[2], 'packages/file-parse/src/parse.ts')).href);
if(process.argv[3]) {
  console.log(JSON.stringify(await parseFileToText(process.argv[3])));
} else {
  console.log(JSON.stringify({ready:true}));
  for await (const line of createInterface({input:process.stdin})) {
    const {path} = JSON.parse(line);
    const start=performance.now();
    const result=await parseFileToText(path);
    console.log(JSON.stringify({result,ms:performance.now()-start}));
  }
}
