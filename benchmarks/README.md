# 비교 재현

검증 구간 생성에는 SDK가 의존하지 않는 python-docx·openpyxl·python-pptx·lxml을 사용합니다. HWPX는 별도 lxml 경로로 직접 문단 실행을 읽습니다. 레이아웃·이미지·순서·중복의 정확도 평가는 포함하지 않습니다.

1. `git clone https://github.com/pblsketch/openoffice.git` 후 기준 커밋 `5fda8298a042318048a768e10fadadcc02a6d49c`으로 체크아웃합니다.
2. 원본 폴더에서 `npm ci --ignore-scripts --no-audit --no-fund`를 실행합니다. 이 작업은 원본 잠금 파일을 사용합니다. 기준 실행 환경은 Node 22.23.2입니다.
3. `python -m pip install -r benchmarks/requirements.txt`로 평가용 라이브러리를 준비합니다.
4. `python benchmarks/download_corpus.py --destination work/corpus`로 공개 문서를 받고 SHA-256을 확인합니다. 파일 URL이 바뀌거나 해시가 다르면 자동 진행하지 않습니다.
5. `python benchmarks/run.py --upstream /absolute/path/openoffice --corpus work/corpus --output validation/reproduced-comparison.json`을 실행합니다.

문서 바이트와 파서 출력을 배포물에 넣지 않습니다. 현재 `validation/comparison.json`은 별도 설치 작업이 끝난 뒤 실행 순서를 번갈아 측정한 7회 원시값과 중앙값을 포함합니다. 두 구현은 반환 계약이 달라 성능을 완전한 동등 작업으로 해석할 수 없습니다. 브라우저 성능은 별도 검증해야 합니다.

`initial-mvp-comparison.json`은 개선 전 개발 스냅샷의 측정 기록입니다. 최종 원본 대 개선 비교는 `comparison.json`을 사용합니다.
