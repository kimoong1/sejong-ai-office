const $ = (id) => document.getElementById(id);
const records = [];
let selected, currentTab = 'text', worker, working = false, cancelled = false;
const errorLabels = { RESOURCE_LIMIT:'문서가 분석 자원 상한을 초과했습니다. 더 작은 문서로 나누어 주세요.', UNSUPPORTED_FORMAT:'현재 지원하는 DOCX·XLSX·PPTX·HWPX 문서를 선택해 주세요.', REDACTION_UNSUPPORTED:'민감정보 가리기 표시가 있는 문서는 원문 보호를 위해 읽지 않습니다.', INVALID_CONTAINER:'문서 파일이 손상되었거나 읽을 수 없는 형식입니다.', MALFORMED_XML:'문서 내부 XML이 손상되어 분석을 중단했습니다.', ENCRYPTED:'암호화된 문서는 지원하지 않습니다. 암호를 해제한 복사본을 선택해 주세요.' };
const diagnosticLabels = { EXTRACTION_SCOPE:'문단과 표 중심으로 추출합니다. 이미지·임베디드 객체 전체를 해석하지 않습니다.', LAYOUT_NOT_RECONSTRUCTED:'원래 문서의 페이지 배치와 시각적 레이아웃은 재현하지 않습니다.', FORMULA_CACHE_UNVERIFIED:'수식을 계산하지 않았습니다. 저장된 캐시값은 오래된 값일 수 있습니다.', NON_TEXT_OBJECTS:'이미지·차트·수식 등 별도 해석이 필요한 객체가 있습니다.', NUMBER_FORMAT_UNAPPLIED:'일부 숫자 표시 형식은 원시값과 다를 수 있습니다.', NON_SECTION_SPINE_ITEM:'본문 섹션이 아닌 HWPX 메타데이터는 별도로 해석하지 않았습니다.', CURRENT_REVISION:'변경 추적 문서의 삽입 내용은 포함하고 삭제 내용은 제외했습니다.', TEXTBOX_FLATTENED:'텍스트 상자의 글은 문단에 함께 추출했습니다.' };
function el(tag, cls, text) { const node = document.createElement(tag); if (cls) node.className = cls; if (text !== undefined) node.textContent = text; return node; }
function toast(text) { $('toast').textContent = text; $('toast').hidden = false; setTimeout(() => $('toast').hidden = true, 2800); }
function showError(message) { $('error-message').textContent = message; $('error-message').hidden = false; }
function walk(blocks) { return blocks.flatMap(b => [b, ...walk(b.children || [])]); }
function download(name, value, type='application/json') { const blob = new Blob([typeof value === 'string' ? value : JSON.stringify(value, null, 2)], {type}); const url=URL.createObjectURL(blob); const a=el('a'); a.href=url; a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000); }
function resetWorker() { worker?.terminate(); worker = undefined; }
function processFile(file) {
  return new Promise(async (resolve) => {
    if (!worker) worker = new Worker('worker.js', {type:'module'});
    let timer = setTimeout(() => { resetWorker(); resolve({ok:false,error:{code:'TIMEOUT',message:'분석 시간이 90초를 초과했습니다. 다시 시도하거나 문서를 나누어 주세요.'}}); },90000);
    const id = crypto.randomUUID();
    worker.onmessage = ({data}) => {
      if(data.type==='stage') {$('activity-text').textContent=data.text; return;}
      if(data.id!==id) return;
      clearTimeout(timer); resolve({...data.result,elapsedMs:data.elapsedMs});
    };
    worker.onerror = () => { clearTimeout(timer); resetWorker(); resolve({ok:false,error:{code:'ENGINE_FAILED',message:'로컬 분석 엔진을 시작하지 못했습니다. 새로고침 후 다시 시도해 주세요.'}}); };
    const stop = () => {clearTimeout(timer);resetWorker(); resolve({ok:false,error:{code:'ABORTED',message:'분석을 취소했습니다.'}});};
    $('cancel-analysis').onclick = () => {cancelled=true;stop();};
    try { const bytes=await file.arrayBuffer(); if(cancelled){stop();return;} worker.postMessage({bytes,name:file.name,id},[bytes]); }
    catch { clearTimeout(timer); resolve({ok:false,error:{code:'READ_FAILED',message:'파일을 읽지 못했습니다.'}}); }
  });
}
async function analyze(files) {
  if (working) {toast('현재 문서 분석이 끝난 뒤 다시 선택해 주세요.');return;}
  working=true; cancelled=false; $('error-message').hidden=true;
  $('choose-files').disabled=true;
  for(const file of files) {
    if(cancelled) break;
    if(!/\.(docx|xlsx|pptx|hwpx)$/i.test(file.name)){showError(`${file.name}: 지원하지 않는 확장자입니다.`);continue;}
    if(file.size>20_000_000){showError(`${file.name}: 파일당 최대 20 MB까지 지원합니다.`);continue;}
    $('activity').hidden=false; $('activity-title').textContent=file.name+' 분석 중'; $('activity-text').textContent='문서와 로컬 분석 엔진을 준비하고 있습니다.';
    const result=await processFile(file);
    if(result.ok){const record={name:file.name,size:file.size,...result}; records.push(record);selected=record;renderList();renderResult();}
    else showError(file.name+': '+(errorLabels[result.error.code]||result.error.message)+` (${result.error.code})`);
  }
  $('activity').hidden=true; $('choose-files').disabled=false;working=false;
}
function renderList(){
  $('empty-state').hidden=records.length>0;$('clear-files').hidden=records.length===0;$('file-count').textContent=records.length;$('document-count').textContent=records.length;
  $('document-list').replaceChildren();
  records.forEach(record=>{const row=el('button','document-row'+(selected===record?' selected':''));row.style.width='100%';row.style.textAlign='left';const ext=record.document.format;row.append(el('span','file-icon '+(ext==='xlsx'?'sheet':'word'),ext[0].toUpperCase()));const label=el('div');label.append(el('strong','',record.name),el('small','',`${ext.toUpperCase()} · ${(record.size/1024).toFixed(1)} KB · ${(record.elapsedMs/1000).toFixed(2)}초`));row.append(label,el('span','status','분석 완료'));row.onclick=()=>{selected=record;renderList();renderResult();};$('document-list').append(row);});
}
function renderResult(){
  $('result-panel').hidden=!selected;if(!selected)return;
  $('result-name').textContent=selected.name;
  const all=walk(selected.document.blocks);const counts=[['문단',all.filter(b=>['paragraph','heading','list_item'].includes(b.type)).length],['표',all.filter(b=>b.type==='table').length],['셀',all.filter(b=>b.type==='cell').length],['진단',selected.document.diagnostics.length]];
  $('result-metrics').replaceChildren(...counts.map(([label,count])=>{const node=el('div');node.append(el('b','',count),el('span','',label));return node;}));
  renderBody();
}
function sourceNode(unit){const b=el('button','source-button',`↳ ${unit.source.part} · XML ${unit.source.line}행`);b.onclick=()=>{const next=b.nextElementSibling;if(next?.className==='source-details'){next.remove();return;}const info=el('div','source-details',`${unit.source.part}\n${unit.source.path}\n블록: ${unit.id}\nSHA-256: ${selected.document.source.sha256}`);b.after(info);};return b;}
function contentUnits(blocks){const out=[];for(const b of blocks){if(b.text!==undefined)out.push({...b,display:b.text});else if(b.type==='cell'&&b.address){const val=b.display_value??b.value??'';out.push({...b,display:`${b.address}  ${val}${b.formula!==null?'  [수식: ='+b.formula+' / 캐시 미검증]':''}`});}else{if(b.type==='slide'||b.type==='sheet')out.push({...b,display:b.type==='slide'?`슬라이드 ${b.number}`:`시트 · ${b.name}`});out.push(...contentUnits(b.children||[]));}}return out;}
function renderBody(){
  const body=$('result-body');body.replaceChildren();if(!selected)return;
  const query=$('search-text').value.trim().toLocaleLowerCase();
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.tab===currentTab));
  if(currentTab==='json'){body.append(el('pre','json-view',JSON.stringify(selected.document,null,2)));return;}
  if(currentTab==='diagnostics'){selected.document.diagnostics.forEach(d=>{const n=el('div','diagnostic');n.append(el('b','',d.code),el('span','',diagnosticLabels[d.code]||d.message));if(d.part)n.append(el('small','source-button',d.part));body.append(n);});return;}
  if(currentTab==='structure'){
    function tree(blocks,parent){for(const b of blocks){const n=el('div','structure-node');n.append(el('strong','',b.type),el('small','',b.address||b.name||b.text?.slice(0,80)||''));n.append(sourceNode(b));if(b.children)tree(b.children,n);parent.append(n);}}tree(selected.document.blocks,body);return;
  }
  const units=contentUnits(selected.document.blocks).filter(u=>!query||u.display.toLocaleLowerCase().includes(query));
  if(!units.length){body.append(el('p','intro',query?'일치하는 본문이 없습니다.':'추출할 텍스트가 없습니다. 진단을 확인해 주세요.'));return;}
  units.forEach(unit=>{const n=el('div','text-unit '+(unit.type==='heading'?'heading':''));n.append(el('span','',unit.display),sourceNode(unit));body.append(n);});
}
async function benchmark(){
  const box=$('benchmark-content');if(box.dataset.loaded)return;
  try{const response=await fetch('benchmark.json');if(!response.ok)throw new Error();const data=await response.json();box.dataset.loaded='true';
    const rows=data.documents;const sum=(which,key)=>rows.reduce((a,r)=>a+(r[which][key]||0),0);const stats=el('div','benchmark-stats');
    for(const [value,label] of [[rows.length,'비교한 실파일'],[(100*sum('upstream','spans_found')/sum('upstream','spans_total')).toFixed(1)+'%','원본 · 검증 구간 회수율'],[(100*sum('candidate','spans_found')/sum('candidate','spans_total')).toFixed(1)+'%','개선 · 검증 구간 회수율']]){const n=el('div');n.append(el('strong','',value),el('span','',label));stats.append(n);}box.append(stats);
    box.append(el('div','benchmark-note','검증 구간 회수율은 독립된 문서 라이브러리로 얻은 문장·셀 값이 결과에 포함되는 비율입니다. 전체 문서 정확도, 읽기 순서, 중복 또는 레이아웃 정확도와 다릅니다. 속도는 동일 파일을 예열 후 7회 읽은 중앙값이며 CPython·Node 측정값입니다. 브라우저 실행 속도와는 다릅니다.'));
    const table=el('table','benchmark-table');const head=el('tr');['문서','원본 회수율','개선 회수율','원본 속도','개선 속도'].forEach(x=>head.append(el('th','',x)));const thead=el('thead');thead.append(head);table.append(thead);const tbody=el('tbody');
    rows.forEach(r=>{const tr=el('tr');const name=el('td','',r.id);name.append(el('small','',r.format.toUpperCase()));tr.append(name);for(const which of ['upstream','candidate'])tr.append(el('td','',r[which].span_recall===null?'—':(r[which].span_recall*100).toFixed(1)+'%'));for(const which of ['upstream','candidate'])tr.append(el('td','',r[which].warm_median_ms.toFixed(2)+' ms'));tbody.append(tr);});table.append(tbody);box.append(table);const dl=el('button','subtle','측정 JSON 내려받기 ↓');dl.style.marginTop='18px';dl.onclick=()=>download('sejong-ai-office-benchmark.json',data);box.append(dl);
  }catch{box.append(el('div','benchmark-note','비교 리포트를 불러오지 못했습니다. 잠시 뒤 다시 열어 주세요.'));}
}
$('choose-files').onclick=()=>$('file-input').click();$('file-input').onchange=()=>{analyze([...$('file-input').files]);$('file-input').value='';};
const zone=$('drop-zone');['dragenter','dragover'].forEach(event=>zone.addEventListener(event,e=>{e.preventDefault();zone.classList.add('dragover');}));['dragleave','drop'].forEach(event=>zone.addEventListener(event,e=>{e.preventDefault();zone.classList.remove('dragover');}));zone.addEventListener('drop',e=>analyze([...e.dataTransfer.files]));
document.querySelectorAll('[data-sample]').forEach(button=>button.onclick=async()=>{try{const response=await fetch('samples/'+button.dataset.sample);if(!response.ok)throw new Error();const blob=await response.blob();await analyze([new File([blob],button.dataset.sample)]);}catch{showError('예제 파일을 불러오지 못했습니다.');}});
document.querySelectorAll('.tab').forEach(button=>button.onclick=()=>{currentTab=button.dataset.tab;renderBody();});$('search-text').oninput=renderBody;
$('clear-files').onclick=()=>{records.length=0;selected=undefined;renderList();renderResult();toast('이 세션의 분석 결과를 지웠습니다.');};
$('download-json').onclick=()=>selected&&download(selected.name+'.json',selected.document);$('download-chunks').onclick=()=>selected&&download(selected.name+'.chunks.json',selected.chunks);
document.querySelectorAll('[data-page]').forEach(button=>button.onclick=()=>{document.querySelectorAll('[data-page]').forEach(b=>b.classList.toggle('active',b===button));const isReport=button.dataset.page==='benchmark';$('workspace-page').hidden=isReport;$('benchmark-page').hidden=!isReport;$('page-label').textContent=isReport?'파서 비교 리포트':'문서 분석';if(isReport)benchmark();});
