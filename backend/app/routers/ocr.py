import asyncio
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from app.services.ocr_service import extract_text_from_image, get_ocr_engine
from app.services.pdf_direct_service import compute_diff_accuracy, extract_text_direct
from app.services.pdf_service import pdf_to_images, preprocess_for_ocr

router = APIRouter()

# DPI 300으로 PDF 렌더 후, 960으로 리사이즈 → 큰 글자도 유효 글자 높이로 줄여 인식률 개선
OCR_DPI = 300
OCR_MAX_SIDE_LEN = 960


def get_ocr_engine_dep(request: Request):
    """FastAPI Depends: 프로세스별로 lifespan에서 생성한 OCR 엔진을 주입."""
    return request.app.state.ocr_engine


def _run_ocr_sync(engine, tmp_path: str) -> list[dict]:
    """블로킹 OCR 로직. 엔진은 호출측에서 주입 (프로세스당 1개)."""
    images = pdf_to_images(tmp_path, dpi=OCR_DPI, max_side_len=OCR_MAX_SIDE_LEN)
    pages = []
    for i, img in enumerate(images):
        img = preprocess_for_ocr(img)
        text = extract_text_from_image(engine, img)
        pages.append({"page": i + 1, "text": text, "source": "ocr"})
    return pages


def _run_ocr_with_test_mode(engine, tmp_path: str) -> dict:
    """
    테스트 모드: direct 추출 시도 → OCR 실행 → 페이지 수가 같으면 diff/정확도 계산.
    정답 기준은 direct 추출 텍스트. pages에는 direct(정답)을 넣고, page_results에서 ocr과 비교.
    반환: { "pages": [...], "test_mode": True, "direct_available": bool, "page_results": [ ... ] }
    """
    direct_pages = extract_text_direct(tmp_path)
    ocr_pages = _run_ocr_sync(engine, tmp_path)

    direct_available = direct_pages is not None and len(direct_pages) == len(ocr_pages)

    # 테스트 모드에서는 정답 기준을 direct로 둠 → pages에 direct 텍스트 반환
    if direct_available and direct_pages:
        pages = [
            {"page": i + 1, "text": (direct_pages[i] or "").strip(), "source": "direct"}
            for i in range(len(direct_pages))
        ]
    else:
        pages = ocr_pages

    result = {
        "pages": pages,
        "test_mode": True,
        "direct_available": direct_available,
        "page_results": [],
    }

    if not direct_available or not direct_pages:
        return result

    for i, (direct_text, ocr_page) in enumerate(zip(direct_pages, ocr_pages)):
        ocr_text = ocr_page.get("text", "") or ""
        diff_accuracy = compute_diff_accuracy(direct_text, ocr_text)
        result["page_results"].append({
            "page": i + 1,
            "direct_text": direct_text,
            "ocr_text": ocr_text,
            "diff_summary": diff_accuracy["diff_summary"],
            "diff_segments": diff_accuracy["diff_segments"],
            "accuracy": diff_accuracy["accuracy"],
            "total": diff_accuracy["total"],
            "correct": diff_accuracy["correct"],
        })

    return result


MAX_PDF_SIZE_MB = 50


@router.post("")
@router.post("/from-pdf")
async def ocr_from_pdf(
    file: UploadFile = File(...),
    test_mode: str = Form("false"),
    engine=Depends(get_ocr_engine_dep),
):
    """
    스캔본 PDF를 업로드하면 페이지별로 OCR 후 텍스트 반환.
    test_mode=true 이고 디지털 PDF(텍스트 레이어 있음)면 direct 추출 vs OCR diff 및 한글/숫자/영어별 정확도 표시.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return {"ok": False, "error": "PDF 파일만 업로드 가능합니다."}

    content = await file.read()
    if len(content) > MAX_PDF_SIZE_MB * 1024 * 1024:
        return {"ok": False, "error": f"PDF 크기는 {MAX_PDF_SIZE_MB}MB 이하여야 합니다."}

    is_test_mode = test_mode.lower() in ("true", "1", "yes")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if is_test_mode:
            data = await asyncio.to_thread(_run_ocr_with_test_mode, engine, tmp_path)
            return {"ok": True, "pages": data["pages"], "total_pages": len(data["pages"]), "test_mode": True, "direct_available": data["direct_available"], "page_results": data["page_results"]}
        pages = await asyncio.to_thread(_run_ocr_sync, engine, tmp_path)
        return {"ok": True, "pages": pages, "total_pages": len(pages)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)
