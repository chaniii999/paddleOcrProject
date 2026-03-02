import asyncio
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from app.services.ocr_service import extract_text_from_image, get_ocr_engine
from app.services.pdf_service import pdf_to_images, preprocess_for_ocr

router = APIRouter()

_ocr_engine = None


def get_engine():
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = get_ocr_engine()
    return _ocr_engine


def _run_ocr_sync(tmp_path: str):
    """블로킹 OCR 로직. 스레드에서 실행해 이벤트 루프를 막지 않음."""
    images = pdf_to_images(tmp_path, dpi=150, max_side_len=1280)
    engine = get_engine()
    pages = []
    for i, img in enumerate(images):
        img = preprocess_for_ocr(img)
        text = extract_text_from_image(engine, img)
        pages.append({"page": i + 1, "text": text})
    return pages


MAX_PDF_SIZE_MB = 50


@router.post("")
@router.post("/from-pdf")
async def ocr_from_pdf(file: UploadFile = File(...)):
    """
    스캔본 PDF를 업로드하면 페이지별로 OCR 후 텍스트 반환.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return {"ok": False, "error": "PDF 파일만 업로드 가능합니다."}

    content = await file.read()
    if len(content) > MAX_PDF_SIZE_MB * 1024 * 1024:
        return {"ok": False, "error": f"PDF 크기는 {MAX_PDF_SIZE_MB}MB 이하여야 합니다."}

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        pages = await asyncio.to_thread(_run_ocr_sync, tmp_path)
        return {"ok": True, "pages": pages, "total_pages": len(pages)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)
