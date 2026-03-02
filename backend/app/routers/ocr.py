import tempfile
from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from app.services.ocr_service import extract_text_from_image, get_ocr_engine
from app.services.pdf_service import pdf_to_images

router = APIRouter()

_ocr_engine = None


def get_engine():
    global _ocr_engine
    if _ocr_engine is None:
        _ocr_engine = get_ocr_engine()
    return _ocr_engine


@router.post("")
@router.post("/from-pdf")
async def ocr_from_pdf(file: UploadFile = File(...)):
    """
    스캔본 PDF를 업로드하면 페이지별로 OCR 후 텍스트 반환.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return {"ok": False, "error": "PDF 파일만 업로드 가능합니다."}

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # dpi 150 + 긴 변 1280 제한 → 평문서 1페이지 OCR 속도 개선 (기존 200dpi 대비)
        images = pdf_to_images(tmp_path, dpi=150, max_side_len=1280)
        engine = get_engine()
        pages = []
        for i, img in enumerate(images):
            text = extract_text_from_image(engine, img)
            pages.append({"page": i + 1, "text": text})
        return {"ok": True, "pages": pages, "total_pages": len(pages)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)
