import asyncio
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile

from app.services.ocr_service import extract_text_from_image, get_ocr_engine
from app.services.pdf_direct_service import compute_diff_accuracy, extract_text_direct
from app.services.pdf_service import pdf_to_images, preprocess_for_ocr

router = APIRouter()

_ocr_engine = None


def get_engine():
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = get_ocr_engine()
    return _ocr_engine


def _run_ocr_sync(tmp_path: str) -> list[dict]:
    """블로킹 OCR 로직. 스레드에서 실행해 이벤트 루프를 막지 않음."""
    images = pdf_to_images(tmp_path, dpi=150, max_side_len=1280)
    engine = get_engine()
    pages = []
    for i, img in enumerate(images):
        img = preprocess_for_ocr(img)
        text = extract_text_from_image(engine, img)
        pages.append({"page": i + 1, "text": text})
    return pages


def _run_extract_sync(tmp_path: str) -> list[dict]:
    """
    일반 추출: direct 시도 후 OCR 실행. 페이지별로 direct 가능하면 direct 텍스트 + source='direct', 아니면 OCR + source='ocr'.
    """
    direct_pages = extract_text_direct(tmp_path)
    ocr_pages = _run_ocr_sync(tmp_path)
    pages = []
    for i, ocr_page in enumerate(ocr_pages):
        page_num = i + 1
        if direct_pages and len(direct_pages) == len(ocr_pages):
            direct_text = (direct_pages[i] or "").strip()
            if len(direct_text) >= 10:  # 해당 페이지에 direct 텍스트가 충분히 있으면
                pages.append({"page": page_num, "text": direct_text, "source": "direct"})
                continue
        pages.append({"page": page_num, "text": ocr_page.get("text", "") or "", "source": "ocr"})
    return pages


def _run_ocr_with_test_mode(tmp_path: str) -> dict:
    """
    테스트 모드: direct 추출 시도 → OCR 실행 → 페이지 수가 같으면 diff/정확도 계산.
    반환: { "pages": [...], "test_mode": True, "direct_available": bool, "page_results": [ { "diff_accuracy": {...} }, ... ] }
    """
    direct_pages = extract_text_direct(tmp_path)
    ocr_pages = _run_ocr_sync(tmp_path)

    result = {
        "pages": ocr_pages,
        "test_mode": True,
        "direct_available": direct_pages is not None and len(direct_pages) == len(ocr_pages),
        "page_results": [],
    }

    if not result["direct_available"] or not direct_pages:
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
            data = await asyncio.to_thread(_run_ocr_with_test_mode, tmp_path)
            return {"ok": True, "pages": data["pages"], "total_pages": len(data["pages"]), "test_mode": True, "direct_available": data["direct_available"], "page_results": data["page_results"]}
        pages = await asyncio.to_thread(_run_extract_sync, tmp_path)
        return {"ok": True, "pages": pages, "total_pages": len(pages)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)
