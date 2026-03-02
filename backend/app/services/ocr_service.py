"""Paddle OCR 엔진 생성 및 이미지→텍스트 추출. 레이아웃 후처리는 ocr_layout."""

import logging

import numpy as np
from paddleocr import PaddleOCR

try:
    from paddleocr import logger as _paddleocr_logger
    _paddleocr_logger.setLevel(logging.ERROR)
except Exception:
    pass

# 의회문서(공문서)용: 오인식 억제를 위해 신뢰도 기준을 약간 엄격하게 (0.55)
DROP_SCORE_FOR_COUNCIL_DOCS = 0.55
REC_BATCH_NUM_FOR_GPU = 10


# PaddleOCR 엔진 인스턴스를 생성해 반환 (앱 lifespan에서 한 번만 만들고 재사용).
def get_ocr_engine(
    use_angle_cls: bool = False,
    lang: str = "korean",
    drop_score: float = DROP_SCORE_FOR_COUNCIL_DOCS,
    rec_char_dict_path: str | None = None,
    rec_batch_num: int = REC_BATCH_NUM_FOR_GPU,
):
    kwargs: dict = {"use_angle_cls": use_angle_cls, "lang": lang}
    if rec_char_dict_path:
        kwargs["rec_char_dict_path"] = rec_char_dict_path
    return PaddleOCR(**kwargs)


# PIL/ndarray/경로를 OCR 엔진이 받을 수 있는 RGB·C-contiguous numpy 배열로 바꿈.
def _to_numpy(image):
    if isinstance(image, str):
        return image
    try:
        from PIL import Image
        if isinstance(image, Image.Image):
            if image.mode != "RGB":
                image = image.convert("RGB")
            arr = np.array(image, dtype=np.uint8)
            return np.ascontiguousarray(arr)
    except Exception:
        pass
    if isinstance(image, np.ndarray):
        return np.ascontiguousarray(image.copy())
    return np.array(image)


# OCR 검출 한 건([box, text] 등)에서 텍스트 문자열만 꺼내 반환.
def _text_from_item(item) -> str:
    if not item or len(item) < 2:
        return ""
    part = item[1]
    if isinstance(part, (list, tuple)) and len(part) >= 1:
        return str(part[0]).strip()
    return str(part).strip()


# OCR 검출 한 건에서 좌표 박스(4점 리스트)만 꺼내 반환 (순서 무관하게 처리).
def _get_box_from_item(item):
    if not item or len(item) < 2:
        return None
    first = item[0]
    if isinstance(first, (list, tuple)) and len(first) >= 4:
        return first
    if len(item) > 1 and isinstance(item[1], (list, tuple)) and len(item[1]) >= 4:
        return item[1]
    return None


# 한 장 이미지를 OCR 엔진에 넣어 검출한 뒤, ocr_layout으로 줄/공백/문단을 반영한 텍스트 한 덩어리 반환.
def extract_text_from_image(ocr_engine: PaddleOCR, image) -> str:
    from app.services.ocr_layout import (
        box_y_center,
        build_lines_with_spaces,
        single_char_lines_with_spaces,
    )

    inp = _to_numpy(image)
    result = ocr_engine.ocr(inp)
    if not result or not result[0]:
        return ""

    raw = result[0]
    if isinstance(raw, dict):
        rec = raw.get("rec_texts") or raw.get("texts") or []
        if isinstance(rec, list) and rec:
            return "\n".join(str(t) for t in rec if t)
        return ""

    items = raw if isinstance(raw, list) else [raw]
    texts = [_text_from_item(item) for item in items if item]
    texts = [t for t in texts if t]

    if not texts:
        return ""

    boxes = [_get_box_from_item(item) for item in items if item]
    if len(boxes) != len(texts):
        boxes = [None] * len(texts)

    line_built = build_lines_with_spaces(texts, boxes)
    if line_built is not None:
        return line_built

    if all(len(t) <= 1 for t in texts) and len(items) >= 2:
        try:
            y_centers = [box_y_center(b) for b in boxes if b is not None]
            if len(y_centers) == len(texts):
                combined = single_char_lines_with_spaces(texts, boxes, y_centers)
                if combined is not None:
                    return combined
        except Exception:
            pass
        return "".join(texts)

    return "\n".join(texts)
