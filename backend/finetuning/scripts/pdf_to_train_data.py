#!/usr/bin/env python3
"""
디지털 PDF에서 PaddleOCR 인식(rec) 학습용 데이터를 자동 생성합니다.
PDF 텍스트 레이어의 라인별 bbox를 이용해 이미지 크롭 + train.txt 생성.

포맷: 이미지경로\t라벨 (탭 구분)

사용 예:
  python pdf_to_train_data.py --pdfs ./my_pdfs --output ./train_data
  python pdf_to_train_data.py --pdfs ./doc.pdf --output ./train_data --min-chars 2
"""

import argparse
import random
import sys
import time
import fitz  # pymupdf
from pathlib import Path

# PowerShell 등에서 출력 즉시 표시
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)


def parse_args():
    parser = argparse.ArgumentParser(
        description="디지털 PDF → PaddleOCR rec 학습 데이터 (이미지 + train.txt) 자동 생성"
    )
    parser.add_argument(
        "--pdfs",
        type=str,
        required=True,
        help="PDF 파일 또는 PDF가 있는 폴더 경로",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./train_data",
        help="출력 폴더 (train_data/, imgs/ 생성)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=150,
        help="페이지 렌더링 DPI (기본: 150)",
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=2,
        help="최소 글자 수 (이보다 짧은 라인 제외)",
    )
    parser.add_argument(
        "--val-ratio",
        type=float,
        default=0.1,
        help="검증셋 비율 0~1 (기본: 0.1)",
    )
    parser.add_argument(
        "--padding",
        type=int,
        default=2,
        help="크롭 시 bbox 주변 패딩 픽셀",
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="최대 샘플 수 (초과 시 랜덤 샘플링). 예: 10000",
    )
    return parser.parse_args()


def _collect_pdfs(path: Path) -> list[Path]:
    if path.is_file() and path.suffix.lower() == ".pdf":
        return [path]
    if path.is_dir():
        return sorted(path.glob("**/*.pdf"))
    return []


def _count_total_pages(pdfs: list[Path]) -> int:
    total = 0
    for i, p in enumerate(pdfs):
        try:
            doc = fitz.open(p)
            total += len(doc)
            doc.close()
        except Exception:
            pass
        _progress(f"페이지 수 계산 중... {i + 1}/{len(pdfs)} PDF")
    return total


def _log(msg: str, flush: bool = True) -> None:
    print(msg, flush=flush)


def _progress(msg: str) -> None:
    """한 줄에서 실시간 갱신 (\\r 사용)."""
    sys.stdout.write(f"\r{msg:<80}")
    sys.stdout.flush()


def _extract_lines_with_bbox(page: fitz.Page) -> list[tuple[fitz.Rect, str]]:
    """페이지에서 라인별 (bbox, text) 추출."""
    lines: list[tuple[fitz.Rect, str]] = []
    try:
        d = page.get_text("dict")
    except Exception:
        return []
    blocks = d.get("blocks") or []
    for block in blocks:
        for line in block.get("lines") or []:
            spans = line.get("spans") or []
            if not spans:
                continue
            texts = [s.get("text", "") for s in spans]
            text = "".join(texts).strip()
            if not text:
                continue
            bboxes = [s.get("bbox") for s in spans if s.get("bbox")]
            if not bboxes:
                continue
            x0 = min(b[0] for b in bboxes)
            y0 = min(b[1] for b in bboxes)
            x1 = max(b[2] for b in bboxes)
            y1 = max(b[3] for b in bboxes)
            rect = fitz.Rect(x0, y0, x1, y1)
            if rect.is_empty or rect.is_infinite:
                continue
            lines.append((rect, text))
    return lines


def main():
    args = parse_args()
    _log("시작...")
    pdf_path = Path(args.pdfs).resolve()
    out_dir = Path(args.output).resolve()
    imgs_dir = out_dir / "imgs"
    imgs_dir.mkdir(parents=True, exist_ok=True)

    _log(f"PDF 검색: {pdf_path}")
    pdfs = _collect_pdfs(pdf_path)
    if not pdfs:
        _log(f"[오류] PDF 없음: {pdf_path}")
        return
    _log(f"PDF {len(pdfs)}개 발견")

    _log("총 페이지 수 계산 중...")
    total_pages = _count_total_pages(pdfs)
    _log(f"총 {total_pages}페이지. 처리 시작\n")

    train_lines: list[str] = []
    idx = 0
    pages_done = 0
    start_time = time.perf_counter()

    for pdf_idx, pdf_file in enumerate(pdfs):
        try:
            doc = fitz.open(pdf_file)
        except Exception as e:
            _log(f"[경고] 열기 실패 {pdf_file}: {e}")
            continue
        for page_no in range(len(doc)):
            page = doc[page_no]
            pix = page.get_pixmap(dpi=args.dpi, alpha=False)
            img = pix.pil_image()
            lines = _extract_lines_with_bbox(page)
            mat = fitz.Matrix(args.dpi / 72, args.dpi / 72)
            for rect, text in lines:
                if len(text.strip()) < args.min_chars:
                    continue
                text_clean = text.replace("\t", " ").replace("\n", " ")
                if not text_clean:
                    continue
                rect_scaled = rect * mat
                x0 = max(0, int(rect_scaled.x0) - args.padding)
                y0 = max(0, int(rect_scaled.y0) - args.padding)
                x1 = min(pix.width, int(rect_scaled.x1) + args.padding)
                y1 = min(pix.height, int(rect_scaled.y1) + args.padding)
                if x1 <= x0 or y1 <= y0:
                    continue
                try:
                    crop = img.crop((x0, y0, x1, y1))
                except Exception:
                    continue
                if crop.size[0] < 8 or crop.size[1] < 8:
                    continue
                img_name = f"line_{idx:06d}.png"
                img_path = imgs_dir / img_name
                crop.save(img_path)
                rel_path = f"imgs/{img_name}"  # data_dir 기준 상대 경로
                train_lines.append(f"{rel_path}\t{text_clean}")
                idx += 1
            pages_done += 1
            elapsed = time.perf_counter() - start_time
            pct = 100 * pages_done / total_pages if total_pages else 0
            eta = (elapsed / pages_done * (total_pages - pages_done)) if pages_done else 0
            line = (
                f"[진행] PDF {pdf_idx + 1}/{len(pdfs)} | "
                f"페이지 {pages_done}/{total_pages} ({pct:.1f}%) | "
                f"라인 {idx}건 | "
                f"경과 {elapsed:.0f}초"
            )
            if pages_done > 0 and total_pages > pages_done:
                line += f" | 남은 시간 약 {eta:.0f}초"
            _progress(line)
        doc.close()

    _progress("")  # 진행 줄 비우기
    if not train_lines:
        _log("[오류] 추출된 라인 없음. 텍스트 레이어가 있는 디지털 PDF인지 확인하세요.")
        return

    if args.max_samples is not None and len(train_lines) > args.max_samples:
        random.seed(42)
        train_lines = random.sample(train_lines, args.max_samples)
        _log(f"[샘플링] {args.max_samples}건으로 제한")
        # 샘플에 포함되지 않은 이미지 삭제
        sampled_rel = {line.split("\t")[0] for line in train_lines}
        removed = 0
        for f in imgs_dir.iterdir():
            if f.is_file():
                rel = str(f.relative_to(out_dir)).replace("\\", "/")
                if rel not in sampled_rel:
                    f.unlink(missing_ok=True)
                    removed += 1
        if removed:
            _log(f"미사용 이미지 {removed}개 삭제")

    elapsed_total = time.perf_counter() - start_time
    train_path = out_dir / "train_list.txt"
    with open(train_path, "w", encoding="utf-8") as f:
        f.write("\n".join(train_lines))
    _log(f"train_list.txt 생성: {train_path} ({len(train_lines)}건)")
    _log(f"총 소요 시간: {elapsed_total:.0f}초 ({elapsed_total / 60:.1f}분)")

    if args.val_ratio > 0:
        random.seed(42)
        shuffled = train_lines.copy()
        random.shuffle(shuffled)
        n_val = max(1, int(len(shuffled) * args.val_ratio))
        val_lines = shuffled[:n_val]
        val_path = out_dir / "val_list.txt"
        with open(val_path, "w", encoding="utf-8") as f:
            f.write("\n".join(val_lines))
        _log(f"val_list.txt 생성: {val_path} ({len(val_lines)}건)")

    _log(f"이미지 저장: {imgs_dir}")


if __name__ == "__main__":
    main()
