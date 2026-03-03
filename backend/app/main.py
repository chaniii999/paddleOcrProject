import logging
import os
import warnings
from contextlib import asynccontextmanager
from pathlib import Path

# OneDNN 관련 Paddle 3.3+ CPU 추론 오류 우회 (ConvertPirAttribute2RuntimeAttribute)
os.environ["FLAGS_use_mkldnn"] = "0"

# Paddle/PaddleOCR 실행 시 반복 출력되는 로그·경고 억제
os.environ["DISABLE_AUTO_LOGGING_CONFIG"] = "1"
warnings.filterwarnings("ignore", message=".*ccache.*", category=UserWarning)
for _name in ("ppocr", "paddle", "paddlex"):
    logging.getLogger(_name).setLevel(logging.WARNING)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.routers import health, ocr
from app.services.ocr_service import get_ocr_engine


# 앱 기동 시 OCR 엔진을 한 번 만들고 종료 시 정리 (프로세스/워커당 한 개만 유지).
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.ocr_engine = get_ocr_engine()
    except Exception:
        raise
    try:
        yield
    finally:
        app.state.ocr_engine = None


app = FastAPI(
    title="의회문서 OCR API",
    description="스캔본 PDF에서 Paddle OCR로 텍스트 추출",
    version="0.1.0",
    lifespan=lifespan,
)

_STATIC_DIR = Path(__file__).resolve().parent / "static"


# 루트 경로 접속 시 정적 HTML(업로드 폼)을 내려줌.
@app.get("/")
def root():
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
