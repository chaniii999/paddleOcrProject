"""Paddle OCR로 이미지에서 텍스트 추출."""

import logging

import numpy as np
from paddleocr import PaddleOCR

# "Creating model" 등 INFO 로그 억제
try:
    from paddleocr import logger as _paddleocr_logger
    _paddleocr_logger.setLevel(logging.ERROR)
except Exception:
    pass


# 의회문서(공문서)용: 오인식 억제를 위해 신뢰도 기준을 약간 엄격하게 (0.55)
DROP_SCORE_FOR_COUNCIL_DOCS = 0.55
REC_BATCH_NUM_FOR_GPU = 10


def get_ocr_engine(
    use_angle_cls: bool = False,
    lang: str = "korean",
    drop_score: float = DROP_SCORE_FOR_COUNCIL_DOCS,
    rec_char_dict_path: str | None = None,
    rec_batch_num: int = REC_BATCH_NUM_FOR_GPU,
):
    """
    PaddleOCR 엔진 (재사용 권장).
    - use_angle_cls=False: 평문서·정방향 문서는 꺼두면 속도 개선. 회전 문서만 True.
    - drop_score, rec_batch_num: 현재 PaddleOCR whl 버전에서 생성자 인자 미지원. 인터페이스만 유지.
    - rec_char_dict_path: 커스텀 문자 사전 경로 (한 줄 한 글자). 지원 시에만 전달.
    """
    kwargs: dict = {"use_angle_cls": use_angle_cls, "lang": lang}
    if rec_char_dict_path:
        kwargs["rec_char_dict_path"] = rec_char_dict_path
    return PaddleOCR(**kwargs)


def _to_numpy(image):
    """PIL Image → numpy.ndarray (PaddleOCR는 ndarray 또는 str 경로만 지원)."""
    if isinstance(image, np.ndarray):
        return image
    if isinstance(image, str):
        return image
    return np.array(image)


def _text_from_item(item) -> str:
    """한 개 검출 결과에서 텍스트만 추출 (형식: [box, (text, conf)] 또는 [box, text] 등)."""
    if not item or len(item) < 2:
        return ""
    part = item[1]
    if isinstance(part, (list, tuple)) and len(part) >= 1:
        return str(part[0]).strip()
    return str(part).strip()


def _y_center(box) -> float:
    """박스 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] 의 대략적인 y 중앙."""
    if not box or len(box) < 4:
        return 0.0
    ys = [p[1] if len(p) > 1 else 0 for p in box]
    return sum(ys) / len(ys)


def _get_box_from_item(item):
    """item이 [box, text_or_tuple] 또는 [text, box] 형태일 수 있음."""
    if not item or len(item) < 2:
        return None
    first = item[0]
    if isinstance(first, (list, tuple)) and len(first) >= 4:
        return first
    if len(item) > 1 and isinstance(item[1], (list, tuple)) and len(item[1]) >= 4:
        return item[1]
    return None


def extract_text_from_image(ocr_engine: PaddleOCR, image) -> str:
    """
    단일 이미지(PIL Image, numpy.ndarray 또는 파일 경로)에서 텍스트 추출.
    반환: 줄 단위로 합친 문자열.
    """
    inp = _to_numpy(image)
    result = ocr_engine.ocr(inp)
    if not result or not result[0]:
        return ""

    raw = result[0]
    # dict 형태 (rec_texts 등) 인 경우
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

    # 한 글자씩만 나오면 같은 줄(y)끼리 묶어서 한 줄로 합침
    if all(len(t) <= 1 for t in texts) and len(items) >= 2:
        try:
            boxes = [_get_box_from_item(items[i]) for i in range(len(items)) if items[i]]
            y_centers = [_y_center(b) for b in boxes if b is not None]
            if len(y_centers) == len(texts):
                combined = []
                current_y = None
                y_threshold = 20
                current_line = []
                for i, (t, y) in enumerate(zip(texts, y_centers)):
                    if current_y is None or abs(y - current_y) <= y_threshold:
                        current_line.append(t)
                        if current_y is None:
                            current_y = y
                    else:
                        combined.append("".join(current_line))
                        current_line = [t]
                        current_y = y
                if current_line:
                    combined.append("".join(current_line))
                return "\n".join(combined)
        except Exception:
            pass
        return "".join(texts)

    return "\n".join(texts)
