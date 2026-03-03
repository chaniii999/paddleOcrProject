#!/usr/bin/env python3
"""
이미지 데이터셋에서 PaddleOCR 인식(rec) 학습용 train.txt를 생성합니다.
포맷: 이미지경로\t라벨 (탭 구분)

사용 예:
  python generate_train_txt.py --images ./my_dataset/images --labels ./my_dataset/labels.txt --output ./train_data/train.txt
  python generate_train_txt.py --images ./dataset --labels ./labels.csv --output train.txt --delimiter ","
"""

import argparse
import csv
import os
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="PaddleOCR rec 학습용 train.txt 생성 (포맷: 이미지경로\\t라벨)"
    )
    parser.add_argument(
        "--images",
        type=str,
        required=True,
        help="이미지 폴더 경로 (또는 이미지가 있는 루트)",
    )
    parser.add_argument(
        "--labels",
        type=str,
        required=True,
        help="레이블 파일 경로. 형식: (1) 이미지파일명,라벨 (2) 이미지경로\\t라벨 (3) filename,label 헤더 있는 CSV",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="train.txt",
        help="출력 train.txt 경로 (기본: train.txt)",
    )
    parser.add_argument(
        "--delimiter",
        type=str,
        default="\t",
        help="레이블 파일 구분자 (기본: 탭). CSV면 ','",
    )
    parser.add_argument(
        "--encoding",
        type=str,
        default="utf-8",
        help="레이블 파일 인코딩 (기본: utf-8)",
    )
    parser.add_argument(
        "--val-ratio",
        type=float,
        default=0.1,
        help="검증셋 비율 0~1 (기본: 0.1). 0이면 val_list.txt 미생성",
    )
    parser.add_argument(
        "--val-output",
        type=str,
        default=None,
        help="검증셋 파일 경로 (기본: output과 같은 폴더의 val_list.txt)",
    )
    return parser.parse_args()


def detect_label_format(labels_path: str, delimiter: str, encoding: str) -> str:
    """레이블 파일 형식 감지: 'filename_label' | 'path_label' | 'csv'"""
    with open(labels_path, encoding=encoding) as f:
        first = f.readline().strip()
    parts = first.split(delimiter) if delimiter != "\t" else first.split("\t")
    if len(parts) >= 2:
        p0 = parts[0].strip()
        if os.path.sep in p0 or "/" in p0:
            return "path_label"
        return "filename_label"
    if "," in first and "filename" in first.lower():
        return "csv"
    return "filename_label"


def load_labels(
    labels_path: str,
    delimiter: str,
    encoding: str,
    fmt: str,
) -> list[tuple[str, str]]:
    """(이미지 식별자, 라벨) 리스트 반환. 식별자는 파일명 또는 전체 경로."""
    rows: list[tuple[str, str]] = []
    with open(labels_path, encoding=encoding) as f:
        reader = csv.reader(f, delimiter=delimiter)
        for i, row in enumerate(reader):
            if not row:
                continue
            if fmt == "csv" and i == 0 and "filename" in str(row[0]).lower():
                continue
            if len(row) >= 2:
                ident, label = row[0].strip(), row[1].strip()
            elif len(row) == 1:
                ident, label = row[0].strip(), ""
            else:
                continue
            if ident and label is not None:
                rows.append((ident, label))
    return rows


def resolve_image_path(ident: str, images_dir: str) -> str | None:
    """식별자로 실제 이미지 경로 찾기."""
    path = Path(ident)
    if path.is_absolute() and path.exists():
        return str(path.resolve())
    rel = Path(images_dir) / ident
    if rel.exists():
        return str(rel.resolve())
    name_only = Path(ident).name
    for ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"):
        p = Path(images_dir) / (name_only if "." in name_only else name_only + ext)
        if p.exists():
            return str(p.resolve())
    for root, _, files in os.walk(images_dir):
        for f in files:
            if f == name_only or Path(f).stem == Path(name_only).stem:
                return str(Path(root) / f)
    return None


def main():
    args = parse_args()
    images_dir = Path(args.images).resolve()
    if not images_dir.exists():
        raise FileNotFoundError(f"이미지 폴더 없음: {images_dir}")

    labels_path = Path(args.labels).resolve()
    if not labels_path.exists():
        raise FileNotFoundError(f"레이블 파일 없음: {labels_path}")

    fmt = detect_label_format(args.labels, args.delimiter, args.encoding)
    rows = load_labels(args.labels, args.delimiter, args.encoding, fmt)

    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    train_lines: list[str] = []
    for ident, label in rows:
        label_escaped = label.replace("\t", " ")  # 라벨 내 탭 제거
        if fmt == "path_label" and Path(ident).is_absolute() and Path(ident).exists():
            img_path = str(Path(ident).resolve())
        else:
            img_path = resolve_image_path(ident, images_dir)
        if img_path is None:
            print(f"[경고] 이미지 없음: {ident}")
            continue
        train_lines.append(f"{img_path}\t{label_escaped}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(train_lines))

    print(f"train.txt 생성 완료: {out_path} ({len(train_lines)}건)")

    if args.val_ratio > 0 and train_lines:
        import random
        random.seed(42)
        shuffled = train_lines.copy()
        random.shuffle(shuffled)
        n_val = max(1, int(len(shuffled) * args.val_ratio))
        val_lines = shuffled[:n_val]
        val_path = Path(args.val_output) if args.val_output else out_path.with_name("val_list.txt")
        val_path = val_path.resolve()
        val_path.parent.mkdir(parents=True, exist_ok=True)
        with open(val_path, "w", encoding="utf-8") as f:
            f.write("\n".join(val_lines))
        print(f"val_list.txt 생성 완료: {val_path} ({len(val_lines)}건)")


if __name__ == "__main__":
    main()
