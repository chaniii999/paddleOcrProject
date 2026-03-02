"""디지털 PDF에서 텍스트 직접 추출 (테스트 모드용)."""

from pathlib import Path

import fitz  # pymupdf


def extract_text_direct(pdf_path: str | Path) -> list[str] | None:
    """
    PDF에 내장된 텍스트 레이어를 페이지별로 추출.
    sort=True 로 위→아래·왼쪽→오른쪽 읽기 순서로 정렬 후 추출 (문단 순서 꼬임 완화).
    추출 가능하면 페이지당 문자열 리스트, 실패 또는 텍스트 없으면 None.
    """
    path = Path(pdf_path)
    if not path.exists() or path.suffix.lower() != ".pdf":
        return None
    try:
        doc = fitz.open(path)
        pages = []
        for i in range(len(doc)):
            page = doc[i]
            # sort=True: y(세로) → x(가로) 기준 정렬로 읽기 순서에 가깝게
            text = page.get_text("text", sort=True).strip()
            pages.append(text)
        doc.close()
        # 텍스트가 거의 없는 PDF면 direct 추출 불가로 간주
        total_chars = sum(len(p) for p in pages)
        if total_chars < 10:
            return None
        return pages
    except Exception:
        return None


def _char_type(ch: str) -> str | None:
    """한 글자에 대해 'hangul' | 'digit' | 'alpha' | None(기타) 반환."""
    if not ch:
        return None
    if "\uac00" <= ch <= "\ud7a3":  # 한글 음절
        return "hangul"
    if ch.isdigit():
        return "digit"
    if ch.isalpha() and ord(ch) < 128:  # ASCII 영문
        return "alpha"
    return None


def _count_by_type(text: str) -> dict[str, int]:
    counts = {"hangul": 0, "digit": 0, "alpha": 0}
    for ch in text:
        t = _char_type(ch)
        if t and t in counts:
            counts[t] += 1
    return counts


def _normalize_spaces(text: str) -> str:
    """공백·줄바꿈 등 모든 공백 문자 제거. 정확도 계산 시 공백만 다른 경우 맞는 것으로 처리하기 위함."""
    return "".join(text.split())


def _build_diff_segments(direct_text: str, ocr_text: str) -> list[dict]:
    """
    글자 단위로 맞음/틀림 표시용 세그먼트 리스트 생성.
    equal: 일치, replace: direct→ocr 치환, insert: OCR만 있음, delete: direct만 있음.
    """
    import difflib

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


def compute_diff_accuracy(direct_text: str, ocr_text: str) -> dict:
    """
    direct(정답) vs ocr(예측) 비교.
    정확도는 공백을 무시하고 계산 (공백만 다르면 맞는 것으로 처리).
    반환: accuracy(한글/숫자/영어), total, correct, diff_summary, diff_segments(글자별 표시용).
    """
    import difflib

    norm_direct = _normalize_spaces(direct_text)
    norm_ocr = _normalize_spaces(ocr_text)
    matcher = difflib.SequenceMatcher(None, norm_direct, norm_ocr)
    matching_blocks = matcher.get_matching_blocks()

    # 공백 제거한 기준으로 correct 문자 수 (타입별)
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
            accuracy[key] = None  # 해당 타입 없음

    # 글자 단위 diff 세그먼트도 공백 무시: 공백만 다르면 일치로 표시 (서부지원 vs " 서부지원 " 등)
    diff_segments = _build_diff_segments(norm_direct, norm_ocr)

    # 기존 요약용 unified diff (선택)
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
