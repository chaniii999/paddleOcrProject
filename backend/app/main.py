import os
from pathlib import Path

# OneDNN 관련 Paddle 3.3+ CPU 추론 오류 우회 (ConvertPirAttribute2RuntimeAttribute)
os.environ["FLAGS_use_mkldnn"] = "0"

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.routers import health, ocr

app = FastAPI(
    title="의회문서 OCR API",
    description="스캔본 PDF에서 Paddle OCR로 텍스트 추출",
    version="0.1.0",
)

_STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/")
def root():
    """테스트용 프론트: PDF 업로드 폼."""
    return FileResponse(_STATIC_DIR / "index.html")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(ocr.router, prefix="/api/ocr", tags=["ocr"])
