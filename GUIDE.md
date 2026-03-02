# 의회문서 OCR 프로젝트 가이드

스캔본 PDF 의회문서에서 Paddle OCR로 텍스트를 추출하는 테스트용 프로젝트입니다.

## 기술 스택

| 구분 | 기술 |
|------|------|
| 언어 | Python 3.10 |
| 백엔드 | FastAPI (테스트용 HTML 포함) |
| OCR 엔진 | PaddleOCR |

---

## 1. 프로젝트 구조 (초기 세팅)

```
paddleOcrProject/
├── .cursor/rules/   # Cursor 규칙 (commit-convention.mdc 등)
├── .gitignore       # Git 제외 (가상환경, __pycache__, .env 등)
├── GUIDE.md        # 이 가이드 (세팅 기록)
├── backend/         # FastAPI + Paddle OCR + 테스트용 HTML
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── static/  # 테스트용 index.html
│   │   ├── routers/
│   │   └── services/
│   ├── requirements.txt
│   └── .env.example # 환경 변수 예시(커밋). 실제 값은 .env 에 두고 제외
└── README.md
```

**Git**: `.env` 는 커밋하지 않고, `.env.example` 만 버전 관리. 가상환경·캐시는 `.gitignore` 로 제외. 커밋 메시지 규칙은 `.cursor/rules/commit-convention.mdc` (Cursor에서만 적용).

---

## 2. 백엔드 세팅 기록

### 2.1 환경 요구사항

- Python 3.10
- (선택) Poppler: PDF → 이미지 변환 시 필요 (`pdf2image` 사용 시)
  - Ubuntu: `sudo apt-get install poppler-utils`
  - Windows: poppler for Windows 배포본 설치 또는 chocolatey

### 2.2 의존성 (requirements.txt)

- `fastapi` - API 서버
- `uvicorn[standard]` - ASGI 서버
- `paddlepaddle` - Paddle OCR 기반 (CPU 버전)
- `paddleocr` - OCR 엔진
- `pdf2image` - PDF 페이지 → 이미지 변환
- `python-multipart` - 파일 업로드
- `pillow` - 이미지 처리 (PaddleOCR 의존)

### 2.3 실행 방법

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8100
```

- 테스트 화면: http://localhost:8100 (PDF 업로드 폼)
- API 문서: http://localhost:8100/docs

---

## 3. OCR 로직 개요

1. 클라이언트에서 스캔본 PDF 업로드
2. 백엔드에서 PDF → 이미지(페이지별) 변환 (`pdf_service`: dpi 150, 긴 변 1280px 제한)
3. 각 페이지 이미지에 Paddle OCR 적용 (엔진 1회 생성 후 재사용)
4. 추출 텍스트를 페이지별/전체로 반환

### 3.1 OCR 속도 (평문서 1페이지 기준)

- **원인**: (1) 200 DPI로 큰 이미지 → detection/recognition 부담 (2) `use_angle_cls=True`로 매번 각도 분류 (3) CPU만 사용.
- **조치**: DPI 150, `max_side_len=1280` 리사이즈, `use_angle_cls=False`(정방향 문서). 스캔본·회전본이 필요하면 `pdf_to_images(..., dpi=200)`, `get_ocr_engine(use_angle_cls=True)`로 조정 가능.
- **리팩터**: OCR 블로킹 구간을 `asyncio.to_thread`로 실행해 이벤트 루프 비차단. PDF 다중 페이지 변환에 `thread_count=2` 사용.

---

## 4. 세팅 이력 (체크리스트)

- [x] GUIDE.md 생성 및 프로젝트 구조 정의
- [x] backend 폴더 및 FastAPI 앱 초기화 (`app/main.py`, CORS, 라우터)
- [x] backend requirements.txt 및 가상환경 안내
- [x] Paddle OCR 연동 및 PDF → 이미지 변환 서비스 (`services/ocr_service.py`, `pdf_service.py`)
- [x] OCR API 엔드포인트: `POST /api/ocr/from-pdf` (파일 업로드 → 페이지별 텍스트 반환)
- [x] 테스트용 HTML (backend/app/static/index.html) — 루트(/)에서 PDF 업로드·OCR 결과 표시

---

## 5. 백엔드 디렉터리 상세

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI 앱, CORS, 라우터 등록, 루트(/) → static/index.html
│   ├── static/
│   │   └── index.html    # 테스트용 PDF 업로드 폼
│   ├── routers/
│   │   ├── health.py     # GET /api/health
│   │   └── ocr.py        # POST /api/ocr/from-pdf
│   └── services/
│       ├── pdf_service.py   # pdf_to_images() — pdf2image 사용
│       └── ocr_service.py  # get_ocr_engine(), extract_text_from_image()
├── requirements.txt
└── .env.example
```

---

*이 파일은 세팅을 진행하면서 계속 업데이트됩니다.*
