# 세종AI OFFICE

DOCX·XLSX·PPTX·HWPX의 문단·표·셀·슬라이드를 읽고 원문 근거를 연결하는 **브라우저 로컬 문서 분석 워크스페이스와 Python SDK**입니다. 파일을 서버로 업로드하지 않고 Pyodide Web Worker에서 같은 Python 추출기를 실행합니다.

[배포된 세종AI OFFICE](https://sejong-ai-office.dnwndrkdud1.chatgpt.site) · 현재 소유자 로그인 전용

현재 제품은 구조 추출·근거 확인·내보내기에 집중한 시제품입니다. 문서 편집·생성형 AI 대화·OCR·PDF·바이너리 HWP는 포함하지 않습니다.

## 실파일 비교 결과

2026-10-23, 공개 실파일 15개와 독립 참조 구간 417개로 원본 이음오피스의 `parseFileToText`와 비교했습니다.

| 측정 항목 | 원본 파서 | 세종AI OFFICE |
|---|---:|---:|
| 파싱 성공 | 15/15 | 15/15 |
| 참조 문장·셀 값 회수 | 412/417 (98.80%) | 417/417 (100%) |
| 문서별 예열 중앙값의 합 | 492.24 ms | 538.77 ms |

회수율은 정규화한 참조 문자열이 결과에 포함되는 비율입니다. **전체 문서 정확도, 읽기 순서, 중복, 레이아웃 또는 그림 인식 정확도가 아닙니다.** 100%는 이 작은 개발용 평가셋의 참조 구간에만 해당합니다. 별도 미사용 검증셋의 일반화 성능은 평가하지 않았습니다.

속도는 두 프로세스를 예열한 후 실행 순서를 번갈아 7회씩 측정했으며 양쪽 모두 파일 읽기를 포함합니다. 이 실행에서는 개선 파서가 합계 약 9.5% 느렸습니다. 큰 DOCX에서는 빨랐지만 모든 문서에서 빠르지는 않습니다. 원본은 평문, 개선 파서는 근거를 포함한 구조와 JSON 출력 예산 검사까지 수행합니다. 브라우저/WASM의 속도와는 구분해야 합니다.

별도 프로세스 시작을 포함한 개발 런타임 측정은 [cold-development.json](validation/cold-development.json)에 있습니다. 원본 쪽에는 TypeScript 소스 로더와 전체 모듈 import가 포함되므로 완성된 원본 앱의 시작 속도로 해석하지 않습니다.

원본 기준 커밋: [`5fda8298a042318048a768e10fadadcc02a6d49c`](https://github.com/pblsketch/openoffice/tree/5fda8298a042318048a768e10fadadcc02a6d49c). 자세한 측정 방법과 파일별 결과는 [비교 보고서](validation/COMPARISON.ko.md) 및 [원시 측정 JSON](validation/comparison.json)에 있습니다.

## 비교에서 확인하고 고친 문제

- DOCX의 `webHidden`을 일반 숨김으로 취급해 목차 쪽 번호를 빼던 문제를 수정했습니다. `vanish`로 숨긴 실행은 계속 제외합니다.
- XLSX의 날짜 직렬값을 1900/1904 날짜 체계에 맞춰 별도 `display_value`로 표시합니다. 원시값 `raw`와 `value`, 수식·캐시 정보는 유지합니다.
- 선행 0·퍼센트·경과 시간의 일부 표시 형식을 지원합니다. Excel의 모든 서식을 재현하지 않습니다.
- HWPX의 사용하지 않는 스타일 헤더 트리를 만들지 않아 불필요한 파싱을 줄였습니다.
- 중첩 표 속 셀의 병합 속성을 바깥 셀 속성으로 읽을 수 있는 경로를 제한했습니다.

## 실행

Python 3.11 이상. SDK 실행에는 외부 Python 패키지가 필요하지 않습니다.

```bash
python -m officeparse report.docx
python -m officeparse budget.xlsx --format text
python -m officeparse report.hwpx --format chunks --output chunks.json
python -m officeparse a.docx b.pptx --concurrency 2 --timeout 20 --output results.jsonl
```

```python
from officeparse import parse_file, to_chunks, to_text, Limits

result = parse_file('report.docx', timeout=20, limits=Limits(max_input_bytes=20_000_000))
if result['ok']:
    print(to_text(result['document']))
    print(result['document']['diagnostics'])
    chunks = to_chunks(result['document'])
else:
    print(result['error'])
```

`parse_file`은 문서별 별도 프로세스와 시간 제한을 적용합니다. `parse_bytes`는 현재 프로세스에서 실행하므로 직접 격리할 때 사용합니다. `integrations/node.mjs`는 셸 없는 Python 호출, 취소, 시간 제한, 출력 바이트 상한을 제공합니다.

## 웹앱 실행

`web/dist/`에 빌드된 정적 앱이 있습니다. 첫 분석 시 버전 고정 Pyodide CDN에서 런타임을 내려받습니다. 문서 내용은 워커 안에서만 읽습니다.

```bash
python tools/build_web.py
python -m http.server 8878 --directory web/dist
```

`http://localhost:8878`에서 열고 예제를 선택하거나 자신의 문서를 읽습니다. 최대 20 MB, 90초 분석 제한, 세션 내 문서 목록, 본문 검색, 구조 보기, JSON/검색용 청크 내보내기, 진단과 원문 위치 확인을 지원합니다.

## 원문 근거와 제한

각 블록은 파일 SHA-256과 XML 파트·구조 경로·XML 줄 번호를 가집니다. XML 줄 번호는 문서 쪽 번호가 아닙니다. 원문을 다시 저장하면 해시와 ID가 바뀔 수 있습니다.

입력·압축 해제·XML 노드/깊이·텍스트·블록·출력 예산을 적용합니다. 위험 ZIP 경로·중복 엔트리·DTD/엔티티·패키지 밖 관계·손상 XML을 거부합니다. 수식·매크로를 실행하거나 외부 관계를 내려받지 않습니다. 알려진 원본 가리기 표식은 호환 구현 전까지 전체 추출을 거부합니다.

전체 프로세스 RSS를 강제하는 OS 메모리 제한은 구현하지 않았습니다. 프로세스/워커 분리는 보안 샌드박스와 다릅니다. 레이아웃·차트·수식 시각 의미·이미지는 진단을 확인해야 합니다.

## 개발 검증

```bash
python -m unittest discover -v
python tools/verify.py
# Python 실행 파일을 지정한 뒤:
node tests/node-bridge.test.mjs web/dist/samples/business-report.docx
```

Python 회귀 검사 52개와 Node 연동 검사 6개를 제공합니다. 브라우저 검증 범위는 `validation/WEB-QA.md`에 기록합니다. 비교 평가 재현 절차는 `benchmarks/README.md`를 따릅니다.

## 라이선스와 출처

새로 작성한 SDK·웹앱은 MIT입니다. 분석 대상 [이음오피스](https://github.com/pblsketch/openoffice)는 별도 Apache-2.0 프로젝트이며 이 배포물에는 원본 엔진을 포함하지 않습니다. 비교에 사용한 제3자 문서는 포함하지 않고 URL·해시·측정값을 기록했습니다. `web/dist/samples`는 직접 만든 업무형 예제입니다. Pyodide는 별도의 오픈소스 프로젝트입니다. [NOTICE](NOTICE)를 함께 확인하세요.
