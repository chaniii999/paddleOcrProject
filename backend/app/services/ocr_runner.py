"""
PDF 경로 기준으로 OCR 실행·테스트 모드(direct+OCR+diff) 오케스트레이션.
파일 역할: "PDF 파일 → 페이지별 결과" 흐름만. HTTP·검증은 router, 엔진·레이아웃은 각 서비스.
"""

from app.config import OCR_DPI, OCR_MAX_SIDE_LEN
from app.services.diff_service import compute_diff_accuracy
from app.services.ocr_service import extract_text_from_image
from app.services.pdf_direct_service import extract_text_direct
from app.services.pdf_service import pdf_to_images, preprocess_for_ocr


# PDF 파일 경로를 받아 페이지마다 OCR 돌리고, 페이지 번호·텍스트·source를 담은 리스트 반환 (블로킹).
def run_ocr_sync(engine, tmp_path: str) -> list[dict]:
    images = pdf_to_images(tmp_path, dpi=OCR_DPI, max_side_len=OCR_MAX_SIDE_LEN)
    pages = []
    for i, img in enumerate(images):
        img = preprocess_for_ocr(img)
        text = extract_text_from_image(engine, img)
        pages.append({"page": i + 1, "text": text, "source": "ocr"})
    return pages


# 테스트 모드: direct 추출 + OCR 실행 후 페이지 수가 같으면 정답(direct) vs OCR 비교·정확도·diff를 넣어 반환.
def run_ocr_with_test_mode(engine, tmp_path: str) -> dict:
    direct_pages = extract_text_direct(tmp_path)
    ocr_pages = run_ocr_sync(engine, tmp_path)

    direct_available = direct_pages is not None and len(direct_pages) == len(ocr_pages)

    if direct_available and direct_pages:
        pages = [
            {"page": i + 1, "text": (direct_pages[i] or "").strip(), "source": "direct"}
            for i in range(len(direct_pages))
        ]
    else:
        pages = ocr_pages

    result = {
        "pages": pages,
        "test_mode": True,
        "direct_available": direct_available,
        "page_results": [],
    }

    if not direct_available or not direct_pages:
        return result

    sum_total = {"hangul": 0, "digit": 0, "alpha": 0}
    sum_correct = {"hangul": 0, "digit": 0, "alpha": 0}

    for i, (direct_text, ocr_page) in enumerate(zip(direct_pages, ocr_pages)):
        ocr_text = ocr_page.get("text", "") or ""
        diff_accuracy = compute_diff_accuracy(direct_text, ocr_text)
        for k in ("hangul", "digit", "alpha"):
            sum_total[k] += diff_accuracy["total"].get(k, 0)
            sum_correct[k] += diff_accuracy["correct"].get(k, 0)
        result["page_results"].append({
            "page": i + 1,
            "direct_text": direct_text,
            "ocr_text": ocr_text,
            "diff_summary": diff_accuracy["diff_summary"],
            "diff_segments": diff_accuracy["diff_segments"],
            "accuracy": diff_accuracy["accuracy"],
            "total": diff_accuracy["total"],
            "correct": diff_accuracy["correct"],
        })

    overall_accuracy = {}
    for k in ("hangul", "digit", "alpha"):
        if sum_total[k] > 0:
            overall_accuracy[k] = round(100.0 * sum_correct[k] / sum_total[k], 1)
        else:
            overall_accuracy[k] = None
    total_chars = sum(sum_total.values())
    if total_chars > 0:
        overall_accuracy["overall"] = round(
            100.0 * sum(sum_correct.values()) / total_chars, 1
        )
    else:
        overall_accuracy["overall"] = None
    result["overall_accuracy"] = overall_accuracy

    return result
