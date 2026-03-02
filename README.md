# 의회문서 OCR (Paddle OCR)

스캔본 PDF 의회문서에서 Paddle OCR로 텍스트를 추출하는 테스트용 프로젝트입니다.

- **기술 스택**: Python 3.10, FastAPI (테스트용 HTML 포함)
- **세팅·진행 상황**: [GUIDE.md](./GUIDE.md) 참고
- **OCR 파이프라인**: [OCR_PIPELINE.md](./OCR_PIPELINE.md) 참고
- **OCR 운영(3GB GPU·추천 흐름)**: [OCR_OPERATION.md](./OCR_OPERATION.md) 참고
- **커밋 규칙**: [COMMIT_CONVENTION.md](./COMMIT_CONVENTION.md) (한글 제목 필수)

## 빠른 실행

### 백엔드

**Conda 사용 시** (아래 명령은 반드시 `backend` 폴더에서 실행)

```bash
cd backend
conda create -n paddle-ocr python=3.10
conda activate paddle-ocr
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8100
```

> `ModuleNotFoundError: No module named 'app'` 가 나오면 **현재 디렉터리가 `backend`인지** 확인하세요. 프로젝트 루트가 아니라 `cd backend` 후 위 명령을 실행해야 합니다.

**venv 사용 시**

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8100
```

- **테스트 화면**: http://localhost:8100 (PDF 업로드 → OCR 결과 확인)
- API 문서: http://localhost:8100/docs  
- OCR (PDF 업로드): `POST /api/ocr` 또는 `POST /api/ocr/from-pdf` (body: `file`에 PDF)

## 사전 요구사항

- Python 3.10
- **Poppler** (PDF → 이미지 변환에 필요, 없으면 `Unable to get page count` 오류 발생)
  - **Ubuntu / WSL**: 터미널에서 실행  
    ```bash
    sudo apt-get update && sudo apt-get install -y poppler-utils
    ```
  - **Windows**: [Poppler for Windows](https://github.com/osber/poppler-windows/releases) 다운로드 후 `bin` 폴더를 PATH에 추가
  - 설치 확인: `pdftoppm -h` 또는 `pdfinfo -v` 가 오류 없이 나오면 됨

## GPU 사용 (선택)

NVIDIA GPU가 있으면 **paddlepaddle-gpu**로 바꿔 설치하면 OCR 속도가 빨라집니다. 코드 수정 없이, GPU 버전 설치만 하면 PaddleOCR이 자동으로 GPU를 사용합니다.

**1060 3GB 등 소용량 VRAM**: 현재 기본값이 이미 3GB 안정권에 맞춰져 있음(긴 변 1280, angle_cls 끔, 페이지별 처리=배치 1). 자세한 규칙·추천 운영 흐름은 [OCR_OPERATION.md](./OCR_OPERATION.md) 참고.

1. **기존 CPU 버전 제거**
   ```bash
   pip uninstall paddlepaddle -y
   ```

2. **CUDA 버전 확인** (예: `nvidia-smi` 상단에 CUDA Version 표시)

3. **해당 CUDA에 맞는 paddlepaddle-gpu 설치** (아래 중 하나만 실행)
   ```bash
   # CUDA 11.8
   pip install paddlepaddle-gpu==3.2.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu118/

   # CUDA 12.6
   pip install paddlepaddle-gpu==3.2.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/

   # CUDA 12.9
   pip install paddlepaddle-gpu==3.2.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/
   ```

4. **나머지 의존성**: `pip install -r requirements-gpu.txt` (paddlepaddle 제외. paddlepaddle-gpu 설치 **후** 실행).

5. **동작 확인**
   ```bash
   python -c "import paddle; paddle.utils.run_check()"
   ```
   출력에 `PaddlePaddle is installed successfully!` 및 GPU 관련 메시지가 나오면 됨.

> CPU에서 OneDNN 오류가 났을 때는 `paddlepaddle<3.3.0`으로 맞췄습니다. GPU용 3.2.2는 해당 이슈가 없을 수 있어 위 예시는 3.2.2 기준입니다. [공식 설치 문서](https://www.paddlepaddle.org.cn/documentation/docs/en/install/pip/linux-pip_en.html)에서 최신 버전·인덱스 확인 가능합니다.
