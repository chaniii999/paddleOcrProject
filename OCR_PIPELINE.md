# OCR 진행 파이프라인

현재 프로젝트에서 PDF 업로드부터 텍스트 추출까지의 처리 흐름을 정리한 문서다.

---

## 1. 전체 흐름

```
[클라이언트] PDF 업로드
       ↓
[라우터] ocr_from_pdf (POST /api/ocr)
       ↓
[임시 파일] 업로드 바이트 → 임시 PDF 저장
       ↓
[스레드] asyncio.to_thread(_run_ocr_sync, tmp_path)
       ↓
[PDF→이미지] pdf_to_images (Poppler + 리사이즈)
       ↓
[OCR 엔진] get_engine() (싱글톤, 최초 1회 로드)
       ↓
[페이지별] for each 이미지 → extract_text_from_image(engine, img)
       ↓
[결과 파싱] PaddleOCR 결과 → 줄 단위 텍스트 (한 글자 검출 시 y 기준 줄 묶음)
       ↓
[응답] { ok, pages: [{ page, text }, ...], total_pages }
       ↓
[정리] 임시 PDF 파일 삭제
```

---

## 2. 단계별 상세

### 2.1 진입점 (라우터)

| 항목 | 내용 |
|------|------|
| 파일 | `backend/app/routers/ocr.py` |
| 엔드포인트 | `POST /api/ocr`, `POST /api/ocr/from-pdf` |
| 입력 | multipart `file`: PDF 파일 |
| 동작 | PDF 확장자 검사 → 업로드 본문을 임시 파일로 저장 → `_run_ocr_sync(tmp_path)` 를 **스레드**에서 실행 → 결과 반환 후 임시 파일 삭제 |

블로킹 구간은 `asyncio.to_thread(_run_ocr_sync, tmp_path)` 로 스레드에서 실행해 이벤트 루프가 막히지 않도록 한다.

### 2.2 PDF → 이미지 (`pdf_service`)

| 항목 | 내용 |
|------|------|
| 파일 | `backend/app/services/pdf_service.py` |
| 함수 | `pdf_to_images(pdf_path, dpi=150, max_side_len=1280, thread_count=2)` |
| 의존성 | Poppler (시스템), pdf2image, PIL |
| 흐름 | 1) `convert_from_path(path, dpi, thread_count)` 로 페이지별 PIL Image 리스트 생성<br>2) 각 이미지에 대해 `_resize_if_large(img, max_side_len)` 적용 (긴 변 > 1280px 이면 비율 유지 리사이즈) |
| 출력 | `list[PIL.Image]` (페이지 순서 유지) |

- **dpi 150**: 평문서 위주 속도 고려. 스캔본은 200 등으로 조정 가능.
- **max_side_len 1280**: OCR 입력 크기 제한으로 CPU 부담·속도 조절.

### 2.3 OCR 엔진 (`ocr_service`)

| 항목 | 내용 |
|------|------|
| 파일 | `backend/app/services/ocr_service.py` |
| 생성 | `get_ocr_engine(use_angle_cls=False, lang="korean")` → `PaddleOCR(...)` |
| 재사용 | 라우터의 `get_engine()` 이 모듈 전역으로 1회만 생성해 재사용 (첫 요청 시 로드). |

- **use_angle_cls=False**: 정방향 문서 기준, 각도 분류 생략으로 속도 우선.
- **lang="korean"**: 한글 인식용.

### 2.4 이미지 → 텍스트 (`extract_text_from_image`)

| 항목 | 내용 |
|------|------|
| 입력 | `ocr_engine`, `image` (PIL Image / numpy ndarray / 파일 경로) |
| 전처리 | PIL 이면 `np.array(image)` 로 ndarray 변환 (PaddleOCR는 ndarray 또는 경로만 지원) |
| 추론 | `ocr_engine.ocr(inp)` → PaddleOCR 결과 구조 |
| 파싱 | 1) `result[0]` 이 dict 면 `rec_texts` / `texts` 를 줄 단위로 이어 붙임<br>2) list 면 각 item 에서 `_text_from_item` 으로 텍스트만 추출<br>3) **한 글자씩만 나오는 경우**: 박스 y 중앙으로 같은 줄로 묶은 뒤 `"\n".join` |
| 출력 | 페이지당 하나의 문자열 (줄 구분은 `\n`) |

결과 구조는 PaddleOCR 버전에 따라 `[box, (text, conf)]` 또는 dict 등으로 달라질 수 있어, 위 파싱이 여러 형태를 처리하도록 되어 있다.

### 2.5 동기 OCR 루프 (`_run_ocr_sync`)

| 항목 | 내용 |
|------|------|
| 위치 | `backend/app/routers/ocr.py` |
| 입력 | 임시 PDF 경로 `tmp_path` |
| 순서 | 1) `pdf_to_images(tmp_path, dpi=150, max_side_len=1280)`<br>2) `get_engine()` 으로 엔진 획득<br>3) `for i, img in enumerate(images): extract_text_from_image(engine, img)`<br>4) `pages = [{"page": i+1, "text": text}, ...]` |
| 출력 | `list[dict]` → `{"page": 1, "text": "..."}, ...` |

페이지는 **순차** 처리한다. (엔진 재사용, 스레드 안전성 등 이유로 병렬화는 하지 않음.)

---

## 3. 데이터 형식

### 3.1 API 요청

- Method: `POST`
- Content-Type: `multipart/form-data`
- Body: `file` = PDF 파일

### 3.2 API 응답 (성공)

```json
{
  "ok": true,
  "pages": [
    { "page": 1, "text": "첫 페이지 추출 텍스트\n줄 단위..." },
    { "page": 2, "text": "두 번째 페이지..." }
  ],
  "total_pages": 2
}
```

### 3.3 API 응답 (실패)

```json
{
  "ok": false,
  "error": "에러 메시지"
}
```

---

## 4. 의존성 요약

| 구간 | 라이브러리 / 시스템 |
|------|---------------------|
| PDF → 이미지 | Poppler (pdftoppm 등), pdf2image, Pillow |
| OCR | PaddlePaddle, PaddleOCR (한글 모델) |
| 서버 | FastAPI, uvicorn |

---

## 5. 설정·튜닝 포인트

- **pdf_service**: `dpi`, `max_side_len`, `thread_count`
- **ocr_service**: `get_ocr_engine(use_angle_cls=..., lang=...)`
- **라우터**: `_run_ocr_sync` 내부에서 `pdf_to_images(..., dpi=150, max_side_len=1280)` 호출부

상세 파라미터는 각 파일의 함수 시그니처와 docstring을 참고하면 된다.
