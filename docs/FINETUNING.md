# PaddleOCR PP-OCRv4 인식(Recognition) 파인튜닝 가이드

Colab T4 4GB 환경에서 PP-OCRv4 한국어 인식 모델을 파인튜닝하는 방법입니다.

---

## 1. 데이터셋 준비

### 1.0 디지털 PDF만 있을 때 (자동 생성)

이미지·레이블이 없고 **디지털 PDF만** 있으면 아래 스크립트로 학습 데이터를 자동 생성합니다.

```bash
# PDF 폴더 또는 단일 PDF → train_data/ (imgs/ + train_list.txt + val_list.txt)
python finetuning/scripts/pdf_to_train_data.py \
  --pdfs ./my_pdfs \
  --output ./train_data \
  --min-chars 2 \
  --val-ratio 0.1
```

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--pdfs` | PDF 파일 또는 폴더 | (필수) |
| `--output` | 출력 폴더 | ./train_data |
| `--dpi` | 렌더링 DPI | 150 |
| `--min-chars` | 최소 글자 수 (짧은 라인 제외) | 2 |
| `--val-ratio` | 검증셋 비율 | 0.1 |

> 텍스트 레이어가 있는 디지털 PDF에서만 동작합니다. 스캔본 PDF는 OCR로 먼저 라벨링해야 합니다.

### 1.1 train.txt 포맷

PaddleOCR 인식 학습용 레이블 파일 형식:

```
이미지경로\t라벨
```

- **탭(`\t`)** 으로 이미지 경로와 라벨 구분
- 예: `./train_data/imgs/001.jpg	안녕하세요`

### 1.2 train.txt 자동 생성 스크립트

이미지 폴더와 레이블 정보가 있으면 `train.txt`를 자동 생성합니다.

**위치**: `finetuning/scripts/generate_train_txt.py`

**사용 예**:

```bash
# 기본: 이미지 폴더 + 레이블 파일 (형식: 파일명\t라벨)
python finetuning/scripts/generate_train_txt.py \
  --images ./my_dataset/images \
  --labels ./my_dataset/labels.txt \
  --output ./train_data/train.txt

# CSV 형식 (파일명,라벨)
python finetuning/scripts/generate_train_txt.py \
  --images ./dataset \
  --labels ./labels.csv \
  --output ./train_data/train.txt \
  --delimiter ","

# 검증셋 10% 자동 분리 (val_list.txt 생성)
python finetuning/scripts/generate_train_txt.py \
  --images ./dataset \
  --labels ./labels.txt \
  --output ./train_data/train.txt \
  --val-ratio 0.1
```

**레이블 파일 형식** (자동 감지):

| 형식 | 예시 |
|------|------|
| 파일명\t라벨 | `img001.jpg	텍스트` |
| 경로\t라벨 | `./imgs/a.jpg	텍스트` |
| CSV (헤더 있음) | `filename,label` 다음 줄부터 `img001.jpg,텍스트` |

**옵션**:

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--images` | 이미지 폴더 경로 | (필수) |
| `--labels` | 레이블 파일 경로 | (필수) |
| `--output` | 출력 train.txt 경로 | train.txt |
| `--delimiter` | 레이블 파일 구분자 | `\t` |
| `--encoding` | 레이블 파일 인코딩 | utf-8 |
| `--val-ratio` | 검증셋 비율 (0~1) | 0.1 |
| `--val-output` | 검증셋 파일 경로 | val_list.txt |

---

## 2. Colab 환경 설정

### 2.1 PaddleOCR 설치

```python
!pip install paddlepaddle-gpu paddleocr -q
# 또는 CPU: !pip install paddlepaddle paddleocr -q
```

### 2.2 PaddleOCR 클론 (학습용)

```python
!git clone https://github.com/PaddlePaddle/PaddleOCR.git
%cd PaddleOCR
```

### 2.3 구글 드라이브 마운트 (체크포인트 저장)

```python
from google.colab import drive
drive.mount('/content/drive')
```

---

## 3. ko_PP-OCRv4_rec.yml 설정 (T4 4GB 최적화)

**위치**: `finetuning/ko_PP-OCRv4_rec.yml`

### 3.1 T4 4GB 최적화 값

| 항목 | 기본(8GPU) | T4 4GB |
|------|------------|--------|
| `batch_size_per_card` | 192 | **16** |
| `learning_rate` | 0.001 | **5e-5** (0.00005) |
| `warmup_epoch` | 5 | 3 |
| `distributed` | true | false |

### 3.2 구글 드라이브 체크포인트 저장

`save_model_dir`을 구글 드라이브 경로로 설정하면 런타임이 끊겨도 체크포인트가 유지됩니다.

```yaml
Global:
  save_model_dir: /content/drive/MyDrive/paddleocr_finetune/output/rec_ppocr_v4
  save_epoch_step: 5  # 5 epoch마다 저장
```

**이어서 학습** 시 `checkpoints`에 마지막 체크포인트 경로 지정:

```yaml
Global:
  checkpoints: /content/drive/MyDrive/paddleocr_finetune/output/rec_ppocr_v4/latest
```

---

## 4. 학습 실행

### 4.1 사전학습 모델 다운로드

```python
# PP-OCRv4 mobile (한국어 dict 적용) 또는 PP-OCRv3 한국어
!mkdir -p pretrain
# 옵션 A: PP-OCRv4 multilingual (한국어 포함)
!wget -P pretrain https://paddleocr.bj.bcebos.com/PP-OCRv4/multilingual/korean_PP-OCRv4_rec_train.tar
!tar -xf pretrain/korean_PP-OCRv4_rec_train.tar -C pretrain
# 옵션 B: PP-OCRv3 한국어 (공식)
# !wget -P pretrain https://paddleocr.bj.bcebos.com/PP-OCRv3/korean/korean_PP-OCRv3_rec_train.tar
# !tar -xf pretrain/korean_PP-OCRv3_rec_train.tar -C pretrain
```

> 공식 모델 목록: [PaddleOCR Models](https://github.com/PaddlePaddle/PaddleOCR/blob/main/doc/doc_ch/models_list.md)

### 4.2 설정 파일 복사 및 수정

```python
# 프로젝트에서 설정 파일 복사
!cp /content/drive/MyDrive/paddleOcrProject/finetuning/ko_PP-OCRv4_rec.yml ./configs/rec/
# pretrained_model 경로 수정 (yml 내)
```

`ko_PP-OCRv4_rec.yml`에서 `pretrained_model` 수정:

```yaml
Global:
  pretrained_model: ./pretrain/korean_PP-OCRv4_rec_train/best_accuracy.pdparams
```

### 4.3 학습 실행

```python
!python tools/train.py -c configs/rec/ko_PP-OCRv4_rec.yml
```

### 4.4 이어서 학습 (런타임 끊김 후)

```python
# ko_PP-OCRv4_rec.yml 에서 checkpoints 설정 후
!python tools/train.py -c configs/rec/ko_PP-OCRv4_rec.yml
```

---

## 5. 디렉터리 구조 예시

```
train_data/
├── train_list.txt   # generate_train_txt.py 로 생성
├── val_list.txt     # --val-ratio 로 생성
└── imgs/            # 이미지 파일들 (경로는 train_list.txt 기준)

/content/drive/MyDrive/paddleocr_finetune/
└── output/
    └── rec_ppocr_v4/
        ├── latest.pdopt
        ├── latest.pdparams
        └── ...
```

---

## 6. 참고

- [PaddleOCR 파인튜닝 공식 문서](https://www.paddleocr.ai/v2.9/en/ppocr/model_train/finetune.html)
- 파인튜닝 시 데이터 5,000건 이상 권장 (사전 변경 시 더 많이)
- 학습률·배치 크기는 배치에 비례해 조정 (배치 1/2 → lr 1/2)
