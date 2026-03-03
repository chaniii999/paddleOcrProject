"""PDF를 이미지로 변환하는 서비스 (PyMuPDF 사용)."""

from pathlib import Path

import fitz  # pymupdf
from PIL import Image


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
    thread_count: int = 2,  # 호환용 (PyMuPDF는 페이지별 순차 처리)
):
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError("File must be a PDF")

    images = []
    with fitz.open(path) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            img = pix.pil_image()
            images.append(img)

    if max_side_len and max_side_len > 0:
        images = [_resize_if_large(im, max_side_len) for im in images]
    return images
