"""PDF를 이미지로 변환하는 서비스 (pdf2image 사용)."""

from pathlib import Path

from pdf2image import convert_from_path
from PIL import Image


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


def pdf_to_images(pdf_path: str | Path, dpi: int = 150, max_side_len: int = 1280):
    """
    PDF 파일을 페이지별 이미지(PIL Image) 리스트로 변환.
    - dpi: 150이면 평문서 OCR 속도에 유리, 스캔본은 200 권장.
    - max_side_len: 긴 변 제한(픽셀). 넘으면 리사이즈해 CPU 부담 감소.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError("File must be a PDF")
    images = convert_from_path(str(path), dpi=dpi)
    if max_side_len and max_side_len > 0:
        images = [_resize_if_large(im, max_side_len) for im in images]
    return images
