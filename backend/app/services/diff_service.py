"""
두 텍스트(정답 vs OCR 등)를 비교해 정확도·diff 세그먼트를 계산.
파일 역할: 비교·정확도만. PDF 직접 추출은 pdf_direct_service.
"""

import difflib


# 한 글자가 한글/숫자/영문 중 무엇인지 구분해 'hangul'|'digit'|'alpha'|None 반환.
def _char_type(ch: str) -> str | None:
    if not ch:
        return None
    if "\uac00" <= ch <= "\ud7a3":
        return "hangul"
    if ch.isdigit():
        return "digit"
    if ch.isalpha() and ord(ch) < 128:
        return "alpha"
    return None


# 문자열에서 한글/숫자/영문 각각의 글자 수를 세어 딕셔너리로 반환.
def _count_by_type(text: str) -> dict[str, int]:
    counts = {"hangul": 0, "digit": 0, "alpha": 0}
    for ch in text:
        t = _char_type(ch)
        if t and t in counts:
            counts[t] += 1
    return counts


# 모든 공백·줄바꿈을 제거한 문자열로 만들어 정확도 계산 시 공백 차이를 무시함.
def _normalize_spaces(text: str) -> str:
    return "".join(text.split())


# 두 텍스트를 비교해 equal/replace/insert/delete 구간별로 잘라 세그먼트 리스트로 반환 (UI 색칠용).
def _build_diff_segments(direct_text: str, ocr_text: str) -> list[dict]:
    matcher = difflib.SequenceMatcher(None, direct_text, ocr_text)
    segments = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            segments.append({"type": "equal", "text": direct_text[i1:i2]})
        elif tag == "replace":
            segments.append({
                "type": "replace",
                "direct": direct_text[i1:i2],
                "ocr": ocr_text[j1:j2],
            })
        elif tag == "insert":
            segments.append({"type": "insert", "ocr": ocr_text[j1:j2]})
        elif tag == "delete":
            segments.append({"type": "delete", "direct": direct_text[i1:i2]})
    return segments


# 정답(direct)과 OCR 결과를 비교해 한글/숫자/영문별 정확도·diff 세그먼트·요약을 담은 딕셔너리 반환 (공백 무시).
def compute_diff_accuracy(direct_text: str, ocr_text: str) -> dict:
    norm_direct = _normalize_spaces(direct_text)
    norm_ocr = _normalize_spaces(ocr_text)
    matcher = difflib.SequenceMatcher(None, norm_direct, norm_ocr)
    matching_blocks = matcher.get_matching_blocks()

    correct_counts = {"hangul": 0, "digit": 0, "alpha": 0}
    for a_start, _b_start, size in matching_blocks:
        if size <= 0:
            continue
        segment = norm_direct[a_start : a_start + size]
        for ch in segment:
            t = _char_type(ch)
            if t and t in correct_counts:
                correct_counts[t] += 1

    total_counts = _count_by_type(norm_direct)
    accuracy = {}
    for key in ("hangul", "digit", "alpha"):
        total = total_counts[key]
        correct = correct_counts[key]
        if total > 0:
            accuracy[key] = round(100.0 * correct / total, 1)
        else:
            accuracy[key] = None

    diff_segments = _build_diff_segments(norm_direct, norm_ocr)

    diff_lines = list(
        difflib.unified_diff(
            direct_text.splitlines(keepends=True),
            ocr_text.splitlines(keepends=True),
            fromfile="direct",
            tofile="ocr",
            lineterm="",
        )
    )
    diff_summary = "".join(diff_lines[:80]) if diff_lines else "(차이 없음)"
    if len(diff_lines) > 80:
        diff_summary += "\n... (이하 생략)"

    return {
        "accuracy": accuracy,
        "total": total_counts,
        "correct": correct_counts,
        "diff_summary": diff_summary,
        "diff_lines": diff_lines,
        "diff_segments": diff_segments,
    }
