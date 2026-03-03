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

- **테스트 화면**: http://localhost:8100 (PDF 업로드 → OCR 결과 확인)
- API 문서: http://localhost:8100/docs  
- OCR (PDF 업로드): `POST /api/ocr` 또는 `POST /api/ocr/from-pdf` (body: `file`에 PDF)

## 사전 요구사항

- Python 3.10
- PDF → 이미지 변환은 **PyMuPDF** 사용으로 별도 시스템 설치(Poppler 등) 불필요

## GPU 사용 (선택)

NVIDIA GPU가 있으면 **paddlepaddle-gpu**로 바꿔 설치하면 OCR 속도가 빨라집니다. 코드는 `device="gpu:0"`로 고정되어 있어 GPU 버전 설치 시 자동으로 GPU를 사용합니다.

**★ GTX 1060 3GB (Pascal)**: **cu118** 버전 사용 권장. cu129는 검출(dt_polys) 실패로 OCR이 동작하지 않을 수 있음. 자세한 규칙·추천 운영 흐름은 [OCR_OPERATION.md](./OCR_OPERATION.md) 참고.

1. **기존 paddlepaddle 제거**
   ```bash
   pip uninstall paddlepaddle paddlepaddle-gpu -y
   ```

2. **paddlepaddle-gpu 설치** (아래 중 하나만 실행)
   ```bash
   # GTX 1060 (Pascal) 권장 — cu118
   pip install paddlepaddle-gpu==3.2.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu118/

   # Turing/Ampere 이상 — cu126 또는 cu129
   # pip install paddlepaddle-gpu==3.2.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
   # pip install paddlepaddle-gpu==3.2.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/
   ```

3. **나머지 의존성**: `pip install -r requirements-gpu.txt` (paddlepaddle-gpu 설치 **후** 실행)

4. **동작 확인**
   ```bash
   python -c "import paddle; paddle.utils.run_check()"
   ```
   출력에 `PaddlePaddle is installed successfully!` 및 GPU 관련 메시지가 나오면 됨.

> CUDA 13.0 드라이버여도 cu118 빌드는 하위 호환으로 동작함. [공식 설치 문서](https://www.paddlepaddle.org.cn/documentation/docs/en/install/pip/linux-pip_en.html)에서 최신 버전·인덱스 확인 가능.
