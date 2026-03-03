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
import fitz  # pymupdf
from pathlib import Path


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
    return parser.parse_args()


def _collect_pdfs(path: Path) -> list[Path]:
    if path.is_file() and path.suffix.lower() == ".pdf":
        return [path]
    if path.is_dir():
        return sorted(path.glob("**/*.pdf"))
    return []


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
    pdf_path = Path(args.pdfs).resolve()
    out_dir = Path(args.output).resolve()
    imgs_dir = out_dir / "imgs"
    imgs_dir.mkdir(parents=True, exist_ok=True)

    pdfs = _collect_pdfs(pdf_path)
    if not pdfs:
        print(f"[오류] PDF 없음: {pdf_path}")
        return

    train_lines: list[str] = []
    idx = 0

    for pdf_file in pdfs:
        try:
            doc = fitz.open(pdf_file)
        except Exception as e:
            print(f"[경고] 열기 실패 {pdf_file}: {e}")
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
        doc.close()

    if not train_lines:
        print("[오류] 추출된 라인 없음. 텍스트 레이어가 있는 디지털 PDF인지 확인하세요.")
        return

    train_path = out_dir / "train_list.txt"
    with open(train_path, "w", encoding="utf-8") as f:
        f.write("\n".join(train_lines))
    print(f"train_list.txt 생성: {train_path} ({len(train_lines)}건)")
    print(f"  → train.txt 내 경로는 data_dir 기준 상대경로(imgs/xxx.png)")

    if args.val_ratio > 0:
        import random
        random.seed(42)
        shuffled = train_lines.copy()
        random.shuffle(shuffled)
        n_val = max(1, int(len(shuffled) * args.val_ratio))
        val_lines = shuffled[:n_val]
        val_path = out_dir / "val_list.txt"
        with open(val_path, "w", encoding="utf-8") as f:
            f.write("\n".join(val_lines))
        print(f"val_list.txt 생성: {val_path} ({len(val_lines)}건)")

    print(f"이미지 저장: {imgs_dir}")


if __name__ == "__main__":
    main()
