"""PDF를 이미지로 변환하는 서비스 (pdf2image 사용)."""

import os
import sys
from pathlib import Path

from pdf2image import convert_from_path
from PIL import Image, ImageEnhance


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


def preprocess_for_ocr(img: Image.Image) -> Image.Image:
    """
    OCR 인식률 개선을 위한 이미지 전처리 (대비·선명도 보정).
    흐리거나 어두운 스캔본·연속 페이지에 효과적. RGB로 통일해 PaddleOCR 입력 안정화.
    """
    if img.mode != "RGB":
        img = img.convert("RGB")
    img = ImageEnhance.Contrast(img).enhance(1.2)
    img = ImageEnhance.Sharpness(img).enhance(1.15)
    return img


def _resize_if_large(img: Image.Image, max_side: int) -> Image.Image:
    """긴 변이 max_side를 넘으면 비율 유지하며 리사이즈 (OCR 속도 개선)."""
    w, h = img.size
    if max(w, h) <= max_side:
        return img
    if w >= h:
        new_w = max_side
        new_h = int(h * max_side / w)
    else:
        new_h = max_side
        new_w = int(w * max_side / h)
    return img.resize((new_w, new_h), Image.Resampling.LANCZOS)


def pdf_to_images(
    pdf_path: str | Path,
    dpi: int = 150,
    max_side_len: int = 1280,
    thread_count: int = 2,
):
    """
    PDF 파일을 페이지별 이미지(PIL Image) 리스트로 변환.
    - dpi: 150이면 평문서 OCR 속도에 유리, 스캔본은 200 권장.
    - max_side_len: 긴 변 제한(픽셀). 넘으면 리사이즈해 CPU 부담 감소.
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
