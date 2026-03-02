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
    PIL Image → numpy.ndarray. PaddleOCR에 넘기기 전 RGB 통일·C-contiguous 복사.
    DPI 300 대형 이미지에서도 엔진이 안정적으로 처리하도록 함.
    """
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
# 같은 줄에서 가로 간격이 글자 너비의 이 배수 이상이면 열 구분(탭)으로 처리 (표·대비표 등)
COLUMN_GAP_RATIO = 2.8
# 같은 줄로 볼 y 차이 상한 (이하면 같은 줄). 크게 잡아 PDF 줄바꿈을 존중
SAME_LINE_Y_RATIO = 0.85
# 줄 사이 세로 간격: 이 배수 초과면 빈 줄 1개, 큰 간격이면 빈 줄 2개 (PDF 문단 배치 반영)
# 0.95: 보통 줄간격(~0.5h)과 문단 구분(~1h 이상)을 구분해 문단마다 빈 줄 삽입
PARAGRAPH_GAP_RATIO = 0.95
PARAGRAPH_GAP_LARGE_RATIO = 1.9
# 들여쓰기: 픽셀 오프셋을 공백 수로 환산. 작을수록 같은 오프셋에 공백 더 많이 (0.5 → 문단 들여쓰기 강화)
INDENT_CHAR_WIDTH_RATIO = 0.5


def _box_y_bounds(box) -> tuple[float, float]:
    """박스의 y 최소·최대 (줄 간격 계산용)."""
    if not box or len(box) < 4:
        return (0.0, 0.0)
    ys = [p[1] if len(p) > 1 else 0 for p in box]
    return (min(ys), max(ys))


# 빈 줄을 넣지 않는 최소 세로 간격 (이하면 같은 문단으로 간주)
MIN_PARAGRAPH_GAP_RATIO = 0.4


def _join_lines_with_paragraph_gaps(
    line_strings: list[str],
    line_y_ranges: list[tuple[float, float]],
    median_h: float,
) -> str:
    """줄 문자열과 y 범위를 받아 단락 간격(빈 줄)을 반영해 합침. PDF 문단 배치에 맞춤."""
    result_parts = []
    for i, s in enumerate(line_strings):
        if i > 0:
            gap = line_y_ranges[i][0] - line_y_ranges[i - 1][1]
            if gap <= median_h * MIN_PARAGRAPH_GAP_RATIO:
                pass
            elif gap > median_h * PARAGRAPH_GAP_LARGE_RATIO:
                result_parts.append("")
                result_parts.append("")
            elif gap > median_h * PARAGRAPH_GAP_RATIO:
                result_parts.append("")
        result_parts.append(s)
    return "\n".join(result_parts)


def _build_lines_with_spaces(texts: list[str], boxes: list) -> str | None:
    """
    박스 좌표로 줄을 구분하고, 같은 줄 내에서 박스 간 간격이 넓으면 공백 삽입.
    줄 사이 세로 간격이 크면 빈 줄을 넣어 PDF 단락/간격을 반영.
    """
    if not texts or not boxes or len(texts) != len(boxes):
        return None
    valid = [(t, b) for t, b in zip(texts, boxes) if b is not None]
    if not valid:
        return None

    # 박스 좌표·높이 일괄 계산 (중복 호출 제거)
    enhanced = []
    for t, b in valid:
        xl, xr = _box_x_bounds(b)
        y_lo, y_hi = _box_y_bounds(b)
        yc = (y_lo + y_hi) / 2.0
        enhanced.append((t, xl, xr, (y_lo, y_hi), yc))
    heights = [y_hi - y_lo for _, _, _, (y_lo, y_hi), _ in enhanced]
    median_h = float(np.median(heights)) if heights else 0.0
    line_threshold = max(median_h * SAME_LINE_Y_RATIO, 1.0)

    indices = sorted(range(len(enhanced)), key=lambda i: (enhanced[i][4], enhanced[i][1]))

    lines: list[list[tuple[str, float, float, tuple[float, float]]]] = []
    current_line: list[tuple[str, float, float, tuple[float, float]]] = []
    last_y = None

    for i in indices:
        t, x_left, x_right, y_bounds, yc = enhanced[i]
        if last_y is not None and abs(yc - last_y) > line_threshold:
            if current_line:
                lines.append(current_line)
            current_line = []
        current_line.append((t, x_left, x_right, y_bounds))
        last_y = yc

    if current_line:
        lines.append(current_line)

    if not lines:
        return None

    all_widths = [xr - xl for _, xl, xr, _ in (item for line in lines for item in line)]
    median_char_w = float(np.median(all_widths)) if all_widths else 10.0
    left_margin = min(item[1] for line in lines for item in line)
    indent_unit = max(median_char_w * INDENT_CHAR_WIDTH_RATIO, 1.0)

    line_strings = []
    line_y_ranges: list[tuple[float, float]] = []

    for line in lines:
        if not line:
            continue
        widths = [xr - xl for _, xl, xr, _ in line]
        median_w = float(np.median(widths)) if widths else 0.0
        gap_threshold = max(median_w * SPACE_GAP_RATIO, 1.0)
        column_gap_threshold = max(median_w * COLUMN_GAP_RATIO, gap_threshold * 2)

        first_x_left = line[0][1]

        parts = []
        y_mins, y_maxs = [], []
        for j, (t, x_left, x_right, (y_lo, y_hi)) in enumerate(line):
            y_mins.append(y_lo)
            y_maxs.append(y_hi)
            if j > 0:
                prev_right = line[j - 1][2]
                gap = x_left - prev_right
                if gap >= column_gap_threshold:
                    parts.append("\t")
                elif gap >= gap_threshold:
                    parts.append(" ")
            parts.append(t)
        line_content = "".join(parts)
        indent_spaces = max(0, int(round((first_x_left - left_margin) / indent_unit)))
        line_strings.append(" " * indent_spaces + line_content)
        line_y_ranges.append((min(y_mins), max(y_maxs)))

    return _join_lines_with_paragraph_gaps(line_strings, line_y_ranges, median_h)


def _single_char_lines_with_spaces(
    texts: list[str], boxes: list, y_centers: list[float]
) -> str | None:
    """
    한 글자씩 인식된 경우, y 기준으로 같은 줄을 묶고 줄 내에서 간격이 넓으면 공백 삽입.
    줄 사이 세로 간격이 크면 빈 줄로 PDF 간격 반영.
    """
    if not texts or len(texts) != len(y_centers) or len(texts) != len(boxes):
        return None
    valid_indices = [i for i in range(len(texts)) if boxes[i] is not None]
    if not valid_indices:
        return None

    # 박스 좌표 일괄 계산 (중복 호출 제거)
    box_bounds = {}
    for i in valid_indices:
        b = boxes[i]
        xl, xr = _box_x_bounds(b)
        y_lo, y_hi = _box_y_bounds(b)
        box_bounds[i] = (xl, xr, y_lo, y_hi)
    heights = [box_bounds[i][3] - box_bounds[i][2] for i in valid_indices]
    median_h = float(np.median(heights)) if heights else 1.0
    line_threshold = max(median_h * SAME_LINE_Y_RATIO, 1.0)
    y_centers_arr = [(box_bounds[i][2] + box_bounds[i][3]) / 2.0 for i in valid_indices]
    y_center_by_idx = dict(zip(valid_indices, y_centers_arr))

    ordered = sorted(valid_indices, key=lambda i: (y_center_by_idx[i], box_bounds[i][0]))

    lines: list[list[int]] = []
    current = []
    last_y = None
    for i in ordered:
        yc = y_center_by_idx[i]
        if last_y is not None and abs(yc - last_y) > line_threshold:
            if current:
                lines.append(current)
            current = []
        current.append(i)
        last_y = yc
    if current:
        lines.append(current)

    all_widths = [box_bounds[idx][1] - box_bounds[idx][0] for line in lines for idx in line]
    median_char_w = float(np.median(all_widths)) if all_widths else 10.0
    left_margin = min(box_bounds[line[0]][0] for line in lines if line)
    indent_unit = max(median_char_w * INDENT_CHAR_WIDTH_RATIO, 1.0)

    line_strings = []
    line_y_ranges: list[tuple[float, float]] = []
    for line in lines:
        if not line:
            continue
        widths = [box_bounds[idx][1] - box_bounds[idx][0] for idx in line]
        median_w = float(np.median(widths)) if widths else 0.0
        gap_threshold = max(median_w * SPACE_GAP_RATIO, 1.0)
        column_gap_threshold = max(median_w * COLUMN_GAP_RATIO, gap_threshold * 2)

        first_x_left = box_bounds[line[0]][0]
        parts = []
        y_mins, y_maxs = [], []
        for k, idx in enumerate(line):
            xl, xr, y_lo, y_hi = box_bounds[idx]
            y_mins.append(y_lo)
            y_maxs.append(y_hi)
            if k > 0:
                prev_right = box_bounds[line[k - 1]][1]
                gap = xl - prev_right
                if gap >= column_gap_threshold:
                    parts.append("\t")
                elif gap >= gap_threshold:
                    parts.append(" ")
            parts.append(texts[idx])
        line_content = "".join(parts)
        indent_spaces = max(0, int(round((first_x_left - left_margin) / indent_unit)))
        line_strings.append(" " * indent_spaces + line_content)
        line_y_ranges.append((min(y_mins), max(y_maxs)))

    return _join_lines_with_paragraph_gaps(line_strings, line_y_ranges, median_h)


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
