"""
OCR 검출 결과(박스+텍스트)를 줄·공백·문단·들여쓰기가 반영된 텍스트로 변환.
파일 역할: 레이아웃 후처리만. 엔진 호출은 ocr_service.
"""

import numpy as np

# 공백 삽입: 이전 박스 오른쪽 ~ 다음 박스 왼쪽 간격이 이 비율 이상이면 공백으로 간주
SPACE_GAP_RATIO = 0.35
# 같은 줄에서 가로 간격이 글자 너비의 이 배수 이상이면 열 구분(탭)으로 처리 (표·대비표 등)
COLUMN_GAP_RATIO = 2.8
# 같은 줄로 볼 y 차이 상한 (이하면 같은 줄). 크게 잡아 PDF 줄바꿈을 존중
SAME_LINE_Y_RATIO = 0.85
# 줄 사이 세로 간격: 이 배수 초과면 빈 줄 1개, 큰 간격이면 빈 줄 2개 (PDF 문단 배치 반영)
PARAGRAPH_GAP_RATIO = 0.95
PARAGRAPH_GAP_LARGE_RATIO = 1.9
# 들여쓰기: 픽셀 오프셋을 공백 수로 환산
INDENT_CHAR_WIDTH_RATIO = 0.5
# 빈 줄을 넣지 않는 최소 세로 간격 (이하면 같은 문단으로 간주)
MIN_PARAGRAPH_GAP_RATIO = 0.4


# 박스 좌표에서 왼쪽·오른쪽 x 범위를 구함 (공백/탭 삽입 시 간격 계산용).
def _box_x_bounds(box) -> tuple[float, float]:
    if not box or len(box) < 4:
        return (0.0, 0.0)
    xs = [p[0] if len(p) > 0 else 0 for p in box]
    return (min(xs), max(xs))


# 박스의 y 최소·최대를 구함 (줄 간격·문단 빈 줄 판단용).
def _box_y_bounds(box) -> tuple[float, float]:
    if not box or len(box) < 4:
        return (0.0, 0.0)
    ys = [p[1] if len(p) > 1 else 0 for p in box]
    return (min(ys), max(ys))


# 박스의 세로 높이를 구함 (같은 줄인지 판단할 때 쓰는 기준값).
def _box_height(box) -> float:
    if not box or len(box) < 4:
        return 0.0
    ys = [p[1] if len(p) > 1 else 0 for p in box]
    return max(ys) - min(ys)


# 박스의 y 중앙값을 구함 (ocr_service에서 한 글자씩 나올 때 줄 묶기용).
def box_y_center(box) -> float:
    if not box or len(box) < 4:
        return 0.0
    ys = [p[1] if len(p) > 1 else 0 for p in box]
    return sum(ys) / len(ys)


# 이미 만든 줄 문자열들 사이에, 세로 간격이 크면 빈 줄을 넣어서 하나의 문자열로 합침.
def _join_lines_with_paragraph_gaps(
    line_strings: list[str],
    line_y_ranges: list[tuple[float, float]],
    median_h: float,
) -> str:
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


# 박스·텍스트 리스트를 받아 줄 구분·공백/탭/들여쓰기/문단 빈 줄을 넣은 최종 텍스트 한 덩어리로 만듦.
def build_lines_with_spaces(texts: list[str], boxes: list) -> str | None:
    if not texts or not boxes or len(texts) != len(boxes):
        return None
    valid = [(t, b) for t, b in zip(texts, boxes) if b is not None]
    if not valid:
        return None

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


# 한 글자씩만 나온 경우, y 기준으로 같은 줄끼리 묶고 공백/탭/문단 빈 줄을 넣어 한 텍스트로 만듦.
def single_char_lines_with_spaces(
    texts: list[str], boxes: list, y_centers: list[float]
) -> str | None:
    if not texts or len(texts) != len(y_centers) or len(texts) != len(boxes):
        return None
    valid_indices = [i for i in range(len(texts)) if boxes[i] is not None]
    if not valid_indices:
        return None

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
