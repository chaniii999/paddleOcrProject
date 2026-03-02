"""PDF를 이미지로 변환하는 서비스 (pdf2image 사용)."""

import os
import sys
from pathlib import Path

from pdf2image import convert_from_path
from PIL import Image


_POPPLER_CACHE_SENTINEL = object()
_poppler_path_cache: str | None | object = _POPPLER_CACHE_SENTINEL


# Windows에서 pdftoppm 등 Poppler 실행 파일 경로를 찾아 반환 (한 번 찾은 값 캐싱).
def _get_poppler_path() -> str | None:
    global _poppler_path_cache
    if _poppler_path_cache is not _POPPLER_CACHE_SENTINEL:
        return _poppler_path_cache
    if sys.platform != "win32":
        _poppler_path_cache = None
        return None
    env_path = os.environ.get("POPPLER_PATH")
    if env_path and Path(env_path).joinpath("pdftoppm.exe").exists():
        _poppler_path_cache = env_path
        return env_path
    candidates = [
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Poppler" / "bin",
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "poppler" / "Library" / "bin",
        Path(os.environ.get("LocalAppData", "")) / "Programs" / "Poppler" / "bin",
    ]
    for p in candidates:
        if p.joinpath("pdftoppm.exe").exists():
            _poppler_path_cache = str(p)
            return _poppler_path_cache
    # winget 설치 경로 (예: ...\WinGet\Packages\oschwartz10612.Poppler_...\poppler-25.07.0\Library\bin)
    winget = Path(os.environ.get("LocalAppData", "")) / "Microsoft" / "WinGet" / "Packages"
    if winget.is_dir():
        for pkg in winget.iterdir():
            if pkg.is_dir() and "Poppler" in pkg.name:
                for sub in pkg.iterdir():
                    if sub.is_dir() and "poppler" in sub.name.lower():
                        bin_path = sub / "Library" / "bin"
                        if bin_path.joinpath("pdftoppm.exe").exists():
                            _poppler_path_cache = str(bin_path)
                            return _poppler_path_cache
    _poppler_path_cache = None
    return None


# adaptiveThreshold·과보정 방지: 대비/선명도 보정 없이 RGB만 통일
# (과한 전처리 시 2페이지 등에서 오인식)


# OCR 입력 전 이미지를 RGB로만 맞추고, 대비/선명도 등은 건드리지 않음 (엔진과 충돌 방지).
def preprocess_for_ocr(img: Image.Image) -> Image.Image:
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


# PaddleOCR 등은 32 단위 입력을 선호. 리사이즈 시 32 정렬해 내부 리사이즈 충돌 방지
RESIZE_ALIGN = 32


# 긴 변이 max_side를 넘으면 비율 유지해 줄이고, 가로·세로를 32 배수로 맞춰 엔진 입력에 맞춤.
def _resize_if_large(img: Image.Image, max_side: int) -> Image.Image:
    w, h = img.size
    if max(w, h) <= max_side:
        return img
    if w >= h:
        new_w = max_side
        new_h = int(h * max_side / w)
    else:
        new_h = max_side
        new_w = int(w * max_side / h)
    new_w = max(RESIZE_ALIGN, (new_w // RESIZE_ALIGN) * RESIZE_ALIGN)
    new_h = max(RESIZE_ALIGN, (new_h // RESIZE_ALIGN) * RESIZE_ALIGN)
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


# PDF 파일을 지정 DPI로 렌더한 뒤 페이지별 PIL Image 리스트로 반환 (긴 변 제한·32 정렬 리사이즈 적용).
def pdf_to_images(
    pdf_path: str | Path,
    dpi: int = 300,
    max_side_len: int = 960,
    thread_count: int = 2,
):
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError("File must be a PDF")
    kwargs: dict = {"dpi": dpi, "thread_count": thread_count}
    poppler_path = _get_poppler_path()
    if poppler_path:
        kwargs["poppler_path"] = poppler_path
    images = convert_from_path(str(path), **kwargs)
    if max_side_len and max_side_len > 0:
        images = [_resize_if_large(im, max_side_len) for im in images]
    return images
