"""PDF를 이미지로 변환하는 서비스 (pdf2image 사용)."""

import os
import sys
from pathlib import Path

from pdf2image import convert_from_path
from PIL import Image


def _get_poppler_path() -> str | None:
    """Windows에서 PATH에 없을 때 Poppler bin 경로를 찾음. 환경변수 POPPLER_PATH 또는 흔한 설치 경로."""
    if sys.platform != "win32":
        return None
    env_path = os.environ.get("POPPLER_PATH")
    if env_path and Path(env_path).joinpath("pdftoppm.exe").exists():
        return env_path
    candidates = [
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Poppler" / "bin",
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "poppler" / "Library" / "bin",
        Path(os.environ.get("LocalAppData", "")) / "Programs" / "Poppler" / "bin",
    ]
    for p in candidates:
        if p.joinpath("pdftoppm.exe").exists():
            return str(p)
    # winget 설치 경로 (예: ...\WinGet\Packages\oschwartz10612.Poppler_...\poppler-25.07.0\Library\bin)
    winget = Path(os.environ.get("LocalAppData", "")) / "Microsoft" / "WinGet" / "Packages"
    if winget.is_dir():
        for pkg in winget.iterdir():
            if pkg.is_dir() and "Poppler" in pkg.name:
                for sub in pkg.iterdir():
                    if sub.is_dir() and "poppler" in sub.name.lower():
                        bin_path = sub / "Library" / "bin"
                        if bin_path.joinpath("pdftoppm.exe").exists():
                            return str(bin_path)
    return None


# adaptiveThreshold·과보정 방지: 대비/선명도 보정 없이 RGB만 통일
# (과한 전처리 시 2페이지 등에서 오인식)


def preprocess_for_ocr(img: Image.Image) -> Image.Image:
    """
    OCR 입력용 최소 전처리. RGB 통일만 수행.
    대비·선명도·이진화 미적용 → 엔진 내부 처리와 충돌·과적용 방지.
    """
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


# PaddleOCR 등은 32 단위 입력을 선호. 리사이즈 시 32 정렬해 내부 리사이즈 충돌 방지
RESIZE_ALIGN = 32


def _resize_if_large(img: Image.Image, max_side: int) -> Image.Image:
    """긴 변이 max_side를 넘으면 비율 유지 리사이즈. 출력 크기는 RESIZE_ALIGN 배수로 맞춤."""
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


def pdf_to_images(
    pdf_path: str | Path,
    dpi: int = 300,
    max_side_len: int = 960,
    thread_count: int = 2,
):
    """
    PDF 파일을 페이지별 이미지(PIL Image) 리스트로 변환.
    OCR용: dpi=300, max_side_len=960. 큰 글자도 리사이즈로 유효 높이에 맞춰 인식 개선.
    - max_side_len: 긴 변 제한(픽셀). 초과 시 비율 유지·32 정렬 리사이즈 1회만.
    - thread_count: 다중 페이지 변환 시 스레드 수 (기본 2).
    """
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
