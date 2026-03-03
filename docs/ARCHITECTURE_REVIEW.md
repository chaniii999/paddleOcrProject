# 아키텍처·가독성·성능 검토

## 1. 현재 구조 요약

| 파일 | 역할 | 줄 수 |
|------|------|-------|
| `main.py` | 앱 생성, lifespan, CORS, 라우터 등록, 정적 파일 | ~60 |
| `routers/health.py` | 헬스 체크 | ~10 |
| `routers/ocr.py` | OCR API + DPI/리사이즈 상수 + `_run_ocr_sync` / `_run_ocr_with_test_mode` | ~118 |
| `services/ocr_service.py` | 엔진 생성 + 이미지 변환 + **박스 유틸 + 레이아웃 상수 + 줄/문단/들여쓰기** + 추출 | **365** |
| `services/pdf_service.py` | PDF→이미지, 전처리, 리사이즈 (PyMuPDF) | ~75 |
| `services/pdf_direct_service.py` | 직접 추출 + **문자 타입·정규화·diff/정확도 계산** | ~139 |

---

## 2. 아키텍처 이슈

### 2.1 단일 책임 위반

- **`ocr_service.py`**: 다음이 한 파일에 혼재
  - OCR 엔진 생성·호출
  - 이미지 → numpy 변환
  - 박스 좌표 유틸 (`_box_x_bounds`, `_box_y_bounds`, `_box_height`, `_y_center`)
  - 레이아웃 상수 (SPACE_GAP_RATIO, COLUMN_GAP_RATIO, PARAGRAPH_* 등)
  - 줄 구분·공백/탭/들여쓰기·문단 빈 줄 삽입 (`_build_lines_with_spaces`, `_single_char_lines_with_spaces`, `_join_lines_with_paragraph_gaps`)
  - 최상위 오케스트레이션 (`extract_text_from_image`)
- **`pdf_direct_service.py`**: "PDF 텍스트 레이어 추출"과 "두 텍스트 비교·정확도·diff 세그먼트"가 함께 있음. 비교/정확도는 direct 전용이 아니라 범용 "텍스트 비교" 도메인에 가깝다.
- **`routers/ocr.py`**: HTTP 계층인데 `_run_ocr_sync`, `_run_ocr_with_test_mode` 같은 비즈니스 오케스트레이션이 들어 있음. 라우터는 요청 검증·서비스 호출·응답 반환만 담당하는 편이 좋다.

### 2.2 설정 분산

- `OCR_DPI`, `OCR_MAX_SIDE_LEN` → `routers/ocr.py`
- `MAX_PDF_SIZE_MB` → `routers/ocr.py`
- `SPACE_GAP_RATIO`, `PARAGRAPH_*` 등 → `services/ocr_service.py`
- `RESIZE_ALIGN` → `services/pdf_service.py`

설정/상수를 한곳에서 관리하지 않아, 변경 시 여러 파일을 찾아야 한다.

---

## 3. 가독성 이슈

### 3.1 파일별 역할이 불명확

- **ocr_service.py (365줄)**: "OCR 서비스"라고만 하면 엔진 호출·한 장 추출 정도를 기대하는데, 실제로는 레이아웃 후처리까지 모두 포함. 새 팀원이 "줄/문단 로직 수정"을 할 때 이 파일만으로는 "레이아웃 전담 모듈"이란 인식이 잘 안 생김.
- **pdf_direct_service.py**: 제목은 "디지털 PDF 직접 추출"인데, `compute_diff_accuracy`, `_build_diff_segments` 등 비교·정확도 로직이 절반 가까이 차지함.

### 3.2 라우터가 비즈니스 로직을 포함

- `_run_ocr_sync`, `_run_ocr_with_test_mode`가 라우터에 있으면, "PDF 업로드 → OCR 실행" 플로우를 이해하려면 라우터 파일을 깊이 봐야 함. "실행 흐름"은 서비스/러너 계층에 두고, 라우터는 "입력 검증 → 실행기 호출 → JSON 반환"만 하면 읽기 쉬워진다.

---

## 4. 성능

- 박스 좌표 일괄 계산, `_join_lines_with_paragraph_gaps` 공통화 등 이미 적용되어 있어 **현재 구현 기준으로는 큰 이슈 없음**.
- 상수를 config로 모으면, 나중에 DPI/리사이즈/레이아웃 계수만 바꿔서 실험하기 쉬워져 **튜닝·성능 실험** 측면에서 유리하다.

---

## 5. 개선 제안 (파일별 역할 정리)

| 파일 | 책임 (읽는 사람이 기대할 내용) |
|------|-------------------------------|
| **main.py** | 앱 진입점, lifespan, 미들웨어, 라우트 등록 |
| **config.py** (신규) | OCR/PDF 관련 상수 일원화 (DPI, max_side_len, MAX_PDF_SIZE_MB 등) |
| **routers/health.py** | 헬스 체크 엔드포인트만 |
| **routers/ocr.py** | PDF 업로드 수신·검증, **서비스/러너 호출**, JSON 응답만 |
| **services/ocr_service.py** | 엔진 생성, 이미지→텍스트 추출 오케스트레이션 (레이아웃은 하위 모듈에 위임) |
| **services/ocr_layout.py** (신규) | 박스 리스트 → 줄/공백/탭/들여쓰기/문단 빈 줄이 반영된 텍스트 (상수 포함) |
| **services/pdf_service.py** | PDF → 이미지, 전처리, 리사이즈 (역할 유지) |
| **services/pdf_direct_service.py** | 디지털 PDF 텍스트 레이어만 추출 |
| **services/diff_service.py** (신규) | 두 텍스트 비교, 정확도, diff 세그먼트 생성 |
| **services/ocr_runner.py** (신규) | "PDF 경로 → OCR 실행" / "PDF 경로 → 테스트 모드(direct+OCR+diff)" 오케스트레이션; 라우터는 여기만 호출 |

이렇게 나누면 **아키텍처(단일 책임)·가독성(파일별 역할 명확)·성능(설정 일원화로 튜닝 용이)** 이 모두 개선된다.

---

## 6. 리팩터링 적용 후 구조

| 파일 | 책임 (한 줄 요약) |
|------|-------------------|
| **main.py** | 앱 진입점, lifespan, CORS, 라우트·정적 파일 |
| **config.py** | OCR_DPI, OCR_MAX_SIDE_LEN, MAX_PDF_SIZE_MB |
| **routers/health.py** | 헬스 체크 |
| **routers/ocr.py** | 업로드 검증 → ocr_runner 호출 → JSON 반환 |
| **services/ocr_service.py** | 엔진 생성, 이미지→텍스트 추출 (레이아웃은 ocr_layout 위임) |
| **services/ocr_layout.py** | 박스→줄/공백/탭/문단/들여쓰기 텍스트 변환 |
| **services/ocr_runner.py** | PDF 경로 → run_ocr_sync / run_ocr_with_test_mode |
| **services/pdf_service.py** | PDF→이미지, 전처리, 리사이즈 |
| **services/pdf_direct_service.py** | 디지털 PDF 텍스트 레이어 추출만 |
| **services/diff_service.py** | 두 텍스트 비교·정확도·diff 세그먼트 |
