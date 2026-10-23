import { loadPyodide } from 'https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.mjs';

let ready;
async function engine() {
  if (!ready) ready = (async () => {
    postMessage({ type: 'stage', text: '로컬 분석 엔진을 준비하고 있습니다. 첫 실행에는 잠시 시간이 걸립니다.' });
    const py = await loadPyodide();
    const response = await fetch('engine.json');
    if (!response.ok) throw new Error('분석 엔진 파일을 읽지 못했습니다.');
    const sources = await response.json();
    py.FS.mkdirTree('/sdk/officeparse');
    for (const [name, source] of Object.entries(sources)) py.FS.writeFile('/sdk/officeparse/' + name, source);
    py.runPython(`import sys\nsys.path.insert(0, '/sdk')\nimport json\nfrom officeparse import parse_bytes, to_chunks, to_text`);
    return py;
  })();
  return ready;
}

self.onmessage = async ({ data }) => {
  const { bytes, name, id } = data;
  try {
    const py = await engine();
    postMessage({ type: 'stage', text: '문단과 표를 읽고 원문 근거를 연결하고 있습니다.' });
    const started = performance.now();
    py.globals.set('_input', new Uint8Array(bytes));
    py.globals.set('_name', name);
    const result = py.runPython(`
from officeparse import Limits
_result = parse_bytes(bytes(_input), _name, Limits(max_input_bytes=20_000_000, max_xml_nodes=150_000, max_blocks=50_000, max_text_chars=2_000_000, max_output_chars=12_000_000))
if _result['ok']:
    _result['text'] = to_text(_result['document'])
    _result['chunks'] = to_chunks(_result['document'])
json.dumps(_result, ensure_ascii=False)
`);
    const decoded = JSON.parse(result);
    py.runPython("del _input, _name, _result");
    postMessage({ type: 'result', id, result: decoded, elapsedMs: performance.now() - started });
  } catch (error) {
    postMessage({ type: 'result', id, result: { ok: false, error: { code: 'ENGINE_FAILED', message: '분석 엔진을 실행하지 못했습니다. 네트워크 연결을 확인하고 다시 시도해 주세요.' } } });
    console.error('Local parser initialization failed', error);
  }
};
