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
    """
    PIL Image → numpy.ndarray (PaddleOCR는 ndarray 또는 str 경로만 지원).
    PIL인 경우 RGB로 통일해 전달 (RGBA/P/L 등은 인식 오류 원인 방지).
    """
    if isinstance(image, np.ndarray):
        return image
    if isinstance(image, str):
        return image
    try:
        from PIL import Image
        if isinstance(image, Image.Image) and image.mode != "RGB":
            image = image.convert("RGB")
    except Exception:
        pass
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


def _box_x_bounds(box) -> tuple[float, float]:
    """
    박스 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] 에서 왼쪽 x(min), 오른쪽 x(max) 반환.
    공백 삽입 시 '이전 박스 오른쪽'과 '다음 박스 왼쪽' 사이 간격을 재기 위해 씀.
    """
    if not box or len(box) < 4:
        return (0.0, 0.0)
    xs = [p[0] if len(p) > 0 else 0 for p in box]
    return (min(xs), max(xs))


def _box_height(box) -> float:
    """박스의 대략적인 세로 높이 (줄 구분 시 같은 줄 판단에 사용)."""
    if not box or len(box) < 4:
        return 0.0
    ys = [p[1] if len(p) > 1 else 0 for p in box]
    return max(ys) - min(ys)


# 공백 삽입: 이전 박스 오른쪽 ~ 다음 박스 왼쪽 간격이 이 비율 이상이면 공백으로 간주
SPACE_GAP_RATIO = 0.35


def _build_lines_with_spaces(texts: list[str], boxes: list) -> str | None:
    """
    박스 좌표로 줄을 구분하고, 같은 줄 내에서 박스 간 간격이 넓으면 공백을 삽입.
    박스가 하나도 없거나 유효하지 않으면 None.
    """
    if not texts or not boxes or len(texts) != len(boxes):
        return None
    valid = [(t, b) for t, b in zip(texts, boxes) if b is not None]
    if not valid:
        return None

    heights = [_box_height(b) for _, b in valid]
    median_h = float(np.median(heights)) if heights else 0.0
    line_threshold = max(median_h * 0.6, 1.0)

    y_centers = [_y_center(b) for _, b in valid]
    indices = sorted(range(len(valid)), key=lambda i: (y_centers[i], _box_x_bounds(valid[i][1])[0]))

    lines: list[list[tuple[str, float, float]]] = []
    current_line: list[tuple[str, float, float]] = []
    last_y = None

    for i in indices:
        t, b = valid[i]
        yc = y_centers[i]
        x_left, x_right = _box_x_bounds(b)
        if last_y is not None and abs(yc - last_y) > line_threshold:
            if current_line:
                lines.append(current_line)
            current_line = []
        current_line.append((t, x_left, x_right))
        last_y = yc

    if current_line:
        lines.append(current_line)

    if not lines:
        return None

    line_strings = []
    for line in lines:
        if not line:
            continue
        widths = [xr - xl for _, xl, xr in line]
        median_w = float(np.median(widths)) if widths else 0.0
        gap_threshold = max(median_w * SPACE_GAP_RATIO, 1.0)

        parts = []
        for j, (t, x_left, x_right) in enumerate(line):
            if j > 0:
                prev_right = line[j - 1][2]
                gap = x_left - prev_right
                if gap >= gap_threshold:
                    parts.append(" ")
            parts.append(t)
        line_strings.append("".join(parts))

    return "\n".join(line_strings)


def _single_char_lines_with_spaces(
    texts: list[str], boxes: list, y_centers: list[float]
) -> str | None:
    """
    한 글자씩 인식된 경우, y 기준으로 같은 줄을 묶고 줄 내에서 간격이 넓으면 공백 삽입.
    """
    if not texts or len(texts) != len(y_centers) or len(texts) != len(boxes):
        return None
    valid_indices = [i for i in range(len(texts)) if boxes[i] is not None]
    if not valid_indices:
        return None

    valid = [(texts[i], boxes[i], y_centers[i]) for i in valid_indices]
    heights = [_box_height(b) for _, b, _ in valid]
    median_h = float(np.median(heights)) if heights else 1.0
    line_threshold = max(median_h * 0.6, 1.0)

    ordered = sorted(valid_indices, key=lambda i: (y_centers[i], _box_x_bounds(boxes[i])[0]))

    lines: list[list[int]] = []
    current = []
    last_y = None
    for i in ordered:
        yc = y_centers[i]
        if last_y is not None and abs(yc - last_y) > line_threshold:
            if current:
                lines.append(current)
            current = []
        current.append(i)
        last_y = yc
    if current:
        lines.append(current)

    line_strings = []
    for line in lines:
        if not line:
            continue
        line_boxes = [boxes[i] for i in line]
        widths = [_box_x_bounds(b)[1] - _box_x_bounds(b)[0] for b in line_boxes]
        median_w = float(np.median(widths)) if widths else 0.0
        gap_threshold = max(median_w * SPACE_GAP_RATIO, 1.0)

        parts = []
        for k, idx in enumerate(line):
            if k > 0:
                prev_right = _box_x_bounds(boxes[line[k - 1]])[1]
                curr_left = _box_x_bounds(boxes[idx])[0]
                if curr_left - prev_right >= gap_threshold:
                    parts.append(" ")
            parts.append(texts[idx])
        line_strings.append("".join(parts))

    return "\n".join(line_strings)


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

    # 박스 좌표로 줄 구분 + 같은 줄 안에서 간격 넓으면 공백 삽입
    boxes = [_get_box_from_item(item) for item in items if item]
    if len(boxes) != len(texts):
        boxes = [None] * len(texts)
    line_built = _build_lines_with_spaces(texts, boxes)
    if line_built is not None:
        return line_built

    # 한 글자씩만 나오면 같은 줄(y)끼리 묶어서 한 줄로 합침 (기존 로직, 공백 보정 포함)
    if all(len(t) <= 1 for t in texts) and len(items) >= 2:
        try:
            y_centers = [_y_center(b) for b in boxes if b is not None]
            if len(y_centers) == len(texts):
                combined = _single_char_lines_with_spaces(texts, boxes, y_centers)
                if combined is not None:
                    return combined
        except Exception:
            pass
        return "".join(texts)

    return "\n".join(texts)
