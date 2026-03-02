"""디지털 PDF에서 텍스트 레이어만 직접 추출 (테스트 모드용). 비교·정확도는 diff_service."""

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
        with fitz.open(path) as doc:
            pages = [
                doc[i].get_text("text", sort=True).strip()
                for i in range(len(doc))
            ]
        total_chars = sum(len(p) for p in pages)
        if total_chars < 10:
            return None
        return pages
    except Exception:
        return None
