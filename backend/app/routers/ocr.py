"""OCR API: PDF 업로드 수신·검증, 서비스 호출, JSON 응답만 담당. 실행 흐름은 ocr_runner."""

import asyncio
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from app.config import MAX_PDF_SIZE_MB
from app.services.ocr_runner import run_ocr_sync, run_ocr_with_test_mode
from app.services.ocr_service import get_ocr_engine

router = APIRouter()


def get_ocr_engine_dep(request: Request):
    """FastAPI Depends: 프로세스별로 lifespan에서 생성한 OCR 엔진을 주입."""
    return request.app.state.ocr_engine


@router.post("")
@router.post("/from-pdf")
async def ocr_from_pdf(
    file: UploadFile = File(...),
    test_mode: str = Form("false"),
    engine=Depends(get_ocr_engine_dep),
):
    """
    스캔본 PDF를 업로드하면 페이지별로 OCR 후 텍스트 반환.
    test_mode=true 이고 디지털 PDF(텍스트 레이어 있음)면 direct vs OCR diff 및 정확도 표시.
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
            data = await asyncio.to_thread(run_ocr_with_test_mode, engine, tmp_path)
            return {
                "ok": True,
                "pages": data["pages"],
                "total_pages": len(data["pages"]),
                "test_mode": True,
                "direct_available": data["direct_available"],
                "page_results": data["page_results"],
            }
        pages = await asyncio.to_thread(run_ocr_sync, engine, tmp_path)
        return {"ok": True, "pages": pages, "total_pages": len(pages)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)
