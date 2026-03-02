"""디지털 PDF에서 텍스트 레이어만 직접 추출 (테스트 모드용). 비교·정확도는 diff_service."""

from pathlib import Path

import fitz  # pymupdf


# 디지털 PDF의 텍스트 레이어를 페이지 순서대로 추출해 문자열 리스트로 반환 (실패/텍스트 거의 없으면 None).
def extract_text_direct(pdf_path: str | Path) -> list[str] | None:
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
