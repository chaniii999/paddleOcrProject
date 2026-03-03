"""OCR API: PDF 업로드 수신·검증, 서비스 호출, JSON 응답만 담당. 실행 흐름은 ocr_runner."""

import asyncio
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import MAX_PDF_SIZE_MB
from app.services.ocr_runner import run_ocr_sync, run_ocr_with_test_mode
from app.services.ocr_service import get_ocr_engine

router = APIRouter()
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


# FastAPI Depends: 요청 시점에 app.state의 OCR 엔진을 반환. 없으면 lazy init 후 저장.
def get_ocr_engine_dep(request: Request):
    engine = getattr(request.app.state, "ocr_engine", None)
    if engine is None:
        engine = get_ocr_engine()
        request.app.state.ocr_engine = engine
    return engine


# 테스트 UI (이식 시 선택적 사용)
@router.get("/test")
def ocr_test_ui():
    return FileResponse(_STATIC_DIR / "index.html")


router.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="ocr_static")


# PDF 업로드 받아 확장자·용량 검사 후, 테스트 모드 여부에 따라 OCR만 또는 direct+OCR+diff 실행해 JSON 반환.
@router.post("")
@router.post("/from-pdf")
async def ocr_from_pdf(
    file: UploadFile = File(...),
    test_mode: str = Form("false"),
    engine=Depends(get_ocr_engine_dep),
):
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
        t0 = time.perf_counter()
        if is_test_mode:
            data = await asyncio.to_thread(run_ocr_with_test_mode, engine, tmp_path)
            elapsed = time.perf_counter() - t0
            n = len(data["pages"])
            out = {
                "ok": True,
                "pages": data["pages"],
                "total_pages": n,
                "test_mode": True,
                "direct_available": data["direct_available"],
                "page_results": data["page_results"],
                "total_elapsed_sec": round(elapsed, 2),
                "avg_sec_per_page": round(elapsed / n, 2) if n else 0,
            }
            if data.get("overall_accuracy"):
                out["overall_accuracy"] = data["overall_accuracy"]
            return out
        pages = await asyncio.to_thread(run_ocr_sync, engine, tmp_path)
        elapsed = time.perf_counter() - t0
        n = len(pages)
        return {
            "ok": True,
            "pages": pages,
            "total_pages": n,
            "total_elapsed_sec": round(elapsed, 2),
            "avg_sec_per_page": round(elapsed / n, 2) if n else 0,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)
