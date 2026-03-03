# 의회문서 OCR 프로젝트 가이드

스캔본 PDF 의회문서에서 Paddle OCR로 텍스트를 추출하는 테스트용 프로젝트입니다.

## 기술 스택

| 구분 | 기술 |
|------|------|
| 언어 | Python 3.10 |
| 백엔드 | FastAPI (테스트용 HTML 포함) |
| OCR 엔진 | PaddleOCR |

---

## 1. 프로젝트 구조 (초기 세팅)

```
paddleOcrProject/
├── .cursor/rules/   # Cursor 규칙 (commit-convention.mdc 등)
├── .gitignore       # Git 제외 (가상환경, __pycache__, .env 등)
├── GUIDE.md        # 이 가이드 (세팅 기록)
├── backend/         # FastAPI + Paddle OCR + 테스트용 HTML
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── static/  # 테스트용 index.html
│   │   ├── routers/
│   │   └── services/
│   ├── requirements.txt
│   └── .env.example # 환경 변수 예시(커밋). 실제 값은 .env 에 두고 제외
└── README.md
```

**Git**: `.env` 는 커밋하지 않고, `.env.example` 만 버전 관리. 가상환경·캐시는 `.gitignore` 로 제외. 커밋 메시지 규칙은 `.cursor/rules/commit-convention.mdc` (Cursor에서만 적용).

---

## 2. 백엔드 세팅 기록

### 2.1 환경 요구사항

- Python 3.10
- **GPU 사용 시** (NVIDIA): paddlepaddle-gpu 설치
  - **GTX 1060 (Pascal)**: **cu118** 버전 권장. cu129는 검출 실패로 OCR 미동작 가능.
  - Turing/Ampere 이상: cu126 또는 cu129 사용 가능.
  - CUDA 13.0 드라이버여도 cu118 빌드는 하위 호환으로 동작.

### 2.2 의존성 (requirements.txt)

- `fastapi` - API 서버
- `uvicorn[standard]` - ASGI 서버
- `paddlepaddle` - Paddle OCR 기반 (CPU 버전)
- `paddleocr` - OCR 엔진
- `pymupdf` - PDF → 이미지 변환, 디지털 PDF 텍스트 추출
- `python-multipart` - 파일 업로드
- `pillow` - 이미지 처리 (PaddleOCR 의존)

### 2.3 실행 방법

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8100
```

- 테스트 화면: http://localhost:8100 (PDF 업로드 폼)
- API 문서: http://localhost:8100/docs

### 2.4 Windows PowerShell에서 가상환경 + GPU 세팅 (처음부터)

Ubuntu/conda 대신 **Windows PowerShell**에서 GPU로 돌리려면 **Miniconda부터** 설치한 뒤 아래 순서대로 진행하면 됩니다.

#### 1) Miniconda 설치 (가장 먼저) — 명령어로 설치

**방법 A — winget (권장)**  
PowerShell에서 한 줄로 설치. 설치 후 **새 터미널**을 열어야 `conda` 인식됨.

```powershell
winget install Anaconda.Miniconda3 --source winget --accept-package-agreements --accept-source-agreements
```

> `msstore` 원본 오류나 인증서 오류가 나면 `--source winget` 을 넣어 winget 저장소만 사용하면 됨.

**방법 B — 무인 설치 (설치 파일 다운로드 후)**  
PATH에 자동 추가까지 하려면 `AddToPath=1` 사용. 설치 경로는 마지막에 한 번만.

```powershell
# 다운로드 (예: 사용자 폴더)
$out = "$env:USERPROFILE\Miniconda3-latest-Windows-x86_64.exe"
Invoke-WebRequest -Uri "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe" -OutFile $out -UseBasicParsing

# 무인 설치 (본인만 사용, PATH 추가, Python 기본 등록 안 함)
Start-Process -FilePath $out -ArgumentList "/InstallationType=JustMe", "/AddToPath=1", "/RegisterPython=0", "/S", "/D=$env:USERPROFILE\Miniconda3" -Wait
```

설치가 끝나면 **PowerShell을 새로 연 뒤** 확인:

```powershell
conda --version
```

**PATH가 안 됐을 때** (winget 설치 후 `conda`를 찾을 수 없는 경우):

1. **경로로 한 번 실행해서 conda init**  
   Miniconda가 보통 `%USERPROFILE%\miniconda3` 또는 `%USERPROFILE%\Miniconda3` 에 설치됨. 아래 중 경로가 있는 쪽으로 실행한 뒤 **PowerShell을 새로 열기**.

   ```powershell
   # 경로 확인 (있으면 그쪽 사용)
   & "$env:USERPROFILE\miniconda3\Scripts\conda.exe" init powershell
   # 또는
   & "$env:USERPROFILE\Miniconda3\Scripts\conda.exe" init powershell
   ```

2. **수동으로 PATH에 추가** (현재 사용자, 영구 적용)

   ```powershell
   $condaPath = "$env:USERPROFILE\miniconda3"
   if (-not (Test-Path $condaPath)) { $condaPath = "$env:USERPROFILE\Miniconda3" }
   [Environment]::SetEnvironmentVariable("Path", $env:Path + ";$condaPath;$condaPath\Scripts", "User")
   ```
   적용 후 **PowerShell을 새로 열고** `conda --version` 으로 확인.

#### 2) 사전 확인 (GPU)

- **NVIDIA 드라이버 + CUDA**  
  ```powershell
  nvidia-smi
  ```
  상단에 **CUDA Version**이 보이면 됨. **GTX 1060 (Pascal)** 사용 시 cu118 빌드 권장 (드라이버가 13.0이어도 cu118은 하위 호환). 없으면 [NVIDIA 드라이버](https://www.nvidia.com/Download/index.aspx) 및 필요 시 [CUDA Toolkit](https://developer.nvidia.com/cuda-downloads) 설치.

> PDF → 이미지 변환은 **PyMuPDF** 사용으로 시스템 Poppler 설치 불필요.

#### 3) Conda 가상환경 생성·활성화

**처음 한 번만** — Conda 이용약관(TOS) 수락이 필요하면 아래 세 줄 실행 후 진행:

```powershell
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/msys2
```

이후 환경 생성·활성화:

```powershell
cd D:\home\paddleOcrProject\backend
conda create -n paddle-ocr python=3.10 -y
conda activate paddle-ocr
```

프롬프트 앞에 `(paddle-ocr)` 가 붙으면 활성화된 상태입니다. (Python 3.10은 이 환경 안에만 설치됨.)

#### 4) PaddlePaddle GPU 설치 (CUDA 버전에 맞게 하나만)

**먼저** CPU용 paddlepaddle은 설치하지 않습니다. 아래 중 **GTX 1060 (Pascal)은 cu118 권장** (cu129는 검출 실패 가능).

```powershell
# GTX 1060 (Pascal) 권장 — cu118
pip install paddlepaddle-gpu==3.2.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu118/

# Turing/Ampere 이상 — cu126 또는 cu129
# pip install paddlepaddle-gpu==3.2.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
# pip install paddlepaddle-gpu==3.2.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/
```

#### 5) 나머지 의존성 설치

```powershell
pip install -r requirements-gpu.txt
```

#### 6) GPU 동작 확인

```powershell
python -c "import paddle; paddle.utils.run_check()"
```

`PaddlePaddle is installed successfully!` 및 GPU 관련 메시지가 나오면 정상입니다.

#### 7) 서버 실행

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8100
```

- 테스트 화면: http://localhost:8100  
- API 문서: http://localhost:8100/docs  

**PowerShell 시작 시 py310 자동 활성화**  
프로필에 한 줄 추가하면 PowerShell을 열 때마다 `py310` 환경이 자동으로 활성화됨.

```powershell
# 프로필이 없으면 빈 파일 생성 후, 맨 아래에 추가
if (!(Test-Path $PROFILE)) { New-Item -Path $PROFILE -ItemType File -Force }
Add-Content -Path $PROFILE -Value "`n# conda py310 자동 활성화`nconda activate py310"
```

적용 후 **PowerShell을 새로 열면** 프롬프트에 `(py310)` 이 붙음. 다른 환경을 쓰려면 `conda activate base` 등으로 전환하면 됨.

> **PowerShell 실행 정책 오류**가 나면:  
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` 실행 후 터미널을 다시 열고 `conda activate py310` 재시도.

---

## 3. OCR 로직 개요

1. 클라이언트에서 스캔본 PDF 업로드
2. 백엔드에서 PDF → 이미지(페이지별) 변환 (`pdf_service`: dpi 150, 긴 변 1280px 제한)
3. 각 페이지 이미지에 Paddle OCR 적용 (엔진 1회 생성 후 재사용)
4. 추출 텍스트를 페이지별/전체로 반환

### 3.1 OCR 속도 (평문서 1페이지 기준)

- **원인**: (1) 200 DPI로 큰 이미지 → detection/recognition 부담 (2) `use_angle_cls=True`로 매번 각도 분류 (3) CPU만 사용.
- **조치**: DPI 150, `max_side_len=1280` 리사이즈, `use_angle_cls=False`(정방향 문서). 스캔본·회전본이 필요하면 `pdf_to_images(..., dpi=200)`, `get_ocr_engine(use_angle_cls=True)`로 조정 가능.
- **리팩터**: OCR 블로킹 구간을 `asyncio.to_thread`로 실행해 이벤트 루프 비차단. PDF 다중 페이지 변환에 `thread_count=2` 사용.

---

## 4. 세팅 이력 (체크리스트)

- [x] GUIDE.md 생성 및 프로젝트 구조 정의
- [x] backend 폴더 및 FastAPI 앱 초기화 (`app/main.py`, CORS, 라우터)
- [x] backend requirements.txt 및 가상환경 안내
- [x] Paddle OCR 연동 및 PDF → 이미지 변환 서비스 (`services/ocr_service.py`, `pdf_service.py`)
- [x] OCR API 엔드포인트: `POST /api/ocr/from-pdf` (파일 업로드 → 페이지별 텍스트 반환)
- [x] 테스트용 HTML (backend/app/static/index.html) — 루트(/)에서 PDF 업로드·OCR 결과 표시

---

## 5. 백엔드 디렉터리 상세

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI 앱, CORS, 라우터 등록, 루트(/) → static/index.html
│   ├── static/
│   │   └── index.html    # 테스트용 PDF 업로드 폼
│   ├── routers/
│   │   ├── health.py     # GET /api/health
│   │   └── ocr.py        # POST /api/ocr/from-pdf
│   └── services/
│       ├── pdf_service.py   # pdf_to_images() — PyMuPDF 사용
│       └── ocr_service.py  # get_ocr_engine(), extract_text_from_image()
├── requirements.txt
└── .env.example
```

---

*이 파일은 세팅을 진행하면서 계속 업데이트됩니다.*
