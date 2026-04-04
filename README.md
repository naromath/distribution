# 유통관리사 2급 학습 웹앱

유통관리사 2급 학습용 정적 웹앱(Vite)입니다.

## 폴더 구조

- `src/`: 화면/퀴즈 로직/문항 데이터
- `public/`: 정적 아이콘
- `기출문제/`: 연도/회차 기준으로 정리된 기출 자료
- `dist/`: 빌드 결과물

## 실행 방법

```bash
npm ci
npm run dev
```

## 배포

- `main` 브랜치 푸시 시 GitHub Pages 배포 워크플로우 실행
- 워크플로우: `.github/workflows/deploy.yml`

## 문제은행 생성

- 생성 스크립트: `scripts/build_question_bank.py`
- 생성 파일: `src/data/generatedQuestions.js`
- 실행:

```bash
python3 scripts/build_question_bank.py
```

- 현재 설정은 다음 회차의 A형 문제지/답안(가답안·확정답안)을 기반으로 자동 생성합니다.
  - `2021-R2`, `2022-R1`, `2022-R2`, `2022-R3`, `2023-R1`, `2023-R2`, `2023-R3`, `2024-R1`, `2024-R2`, `2024-R3`
- `2025-R1/R2/R3`는 문제지(`A형 PDF`)만 분류 완료되었고, 답안이 이미지 파일이라 OCR 정확도 이슈로 자동 생성 대상에서 제외했습니다.

## 문제은행 신뢰도 검증(교차매칭)

- 검증 스크립트: `scripts/build_question_reliability.py`
- 입력 파일:
  - `src/data/generatedQuestions.js`
  - `src/data/learningAssets.js`
- 생성 파일:
  - `src/data/questionReliability.js`
  - `reports/question_reliability_report.md`
- 실행:

```bash
python3 scripts/build_question_reliability.py
```

- 등급 기준:
  - `Strict(완전매치)`: 빈출/핵심 동시 매칭 + 노이즈 플래그 없음 + 고신뢰 점수
  - `Gold`: 자동 출제 우선 사용 가능
  - `Silver`: 학습용 사용 가능(수기 검토 권장)
  - `Review`: 자동 출제 제외 권장
- 앱 기본 문제풀은 운영 가능한 문항 수(기본 200개) 이상일 때만 `Strict`를 사용하고, 그 미만이면 `Gold+Silver` 자동 fallback을 사용합니다.

## Review 검수 큐 생성

- 큐 스크립트: `scripts/export_review_queue.py`
- 입력 파일:
  - `src/data/generatedQuestions.js`
  - `src/data/questionReliability.js`
- 생성 파일:
  - `reports/review_queue.csv`
  - `reports/review_queue_summary.md`
- 실행:

```bash
python3 scripts/export_review_queue.py
```

- 우선순위:
  - `A`: 확정답안 기반 + 노이즈/오탐 가능성이 높은 문항(최우선 수기검수)
  - `B`: 가답안 기반 중 오탐 가능성이 높은 문항
  - `C`: 의미 매칭 부족 위주 장기 검수 대상

## 출제기준 커버리지 점검

- 점검 스크립트: `scripts/validate_question_bank_against_blueprint.py`
- 리포트 파일: `reports/blueprint_coverage_report.md`
- 실행:

```bash
python3 scripts/validate_question_bank_against_blueprint.py
```

- 참고 기준: `/Users/wacus/Downloads/기출기준.pdf`의 2급 출제기준(13~18p)

## 빈출/핵심요약 자산 생성

- 생성 스크립트: `scripts/build_learning_assets.py`
- 입력 파일:
  - `/Users/wacus/Downloads/유통관리사_빈출100선.pdf`
  - `/Users/wacus/Downloads/유통관리사_핵심요점정리.pdf`
- 생성 파일: `src/data/learningAssets.js`
- 실행:

```bash
python3 scripts/build_learning_assets.py
```

- 앱 반영 내용:
  - 퀴즈 모드 `빈출 우선`
  - 퀴즈 모드 `빈출 20문제 세트`
  - 문제 해설 하단 `핵심요약` 및 `빈출연계` 표시

## 기출문제 파일명 규칙

- 형식: `YYYY-RN[-type].ext`
- 예시:
  - `2023-R1-A.pdf`: 2023년 1회 A형
  - `2023-R3-answer-final.pdf`: 2023년 3회 확정답안
  - `2024-R1-answer-tentative.pdf`: 2024년 1회 가답안

상세 목록은 `기출문제/README.md`를 확인하세요.
