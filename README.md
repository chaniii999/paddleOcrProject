# 의회문서 OCR (Paddle OCR)

스캔본 PDF 의회문서에서 Paddle OCR로 텍스트를 추출하는 테스트용 프로젝트입니다.

- **기술 스택**: Python 3.10, FastAPI (테스트용 HTML 포함)
- **세팅·진행 상황**: [GUIDE.md](./GUIDE.md) 참고

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
