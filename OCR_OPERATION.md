# OCR 운영 가이드

세팅 부담을 줄이고, 1060 3GB 같은 소용량 GPU에서도 안정적으로 쓰기 위한 최소 규칙과 추천 운영 흐름을 정리한 문서다.

---

## 1. GPU 설치 (GTX 1060 / Pascal 권장)

**GTX 1060 3GB (Pascal architecture)** 사용 시 **CUDA 11.8용 paddlepaddle-gpu**를 설치해야 한다. cu129(cuda 12.9)는 검출(dt_polys)이 비어 OCR이 실패할 수 있음.

```bash
# 1) 기존 paddlepaddle 제거
pip uninstall paddlepaddle paddlepaddle-gpu -y

# 2) cu118 설치 (GTX 1060 권장)
pip install paddlepaddle-gpu==3.2.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu118/

# 3) 나머지 의존성
pip install -r requirements-gpu.txt
```

- CUDA 13.0 드라이버여도 cu118 빌드는 하위 호환으로 동작함.
- Turing/Ampere 이상 GPU는 cu126, cu129 사용 가능.

---

## 2. 세팅 고생 줄이는 최소 GPU 세팅 (3GB 안정권)

아래 **3가지만** 지키면 1060 3GB에서도 실사용 가능성이 높다.

| 항목 | 권장값 | 비고 |
|------|--------|------|
| **긴 변 리사이즈 제한** | `long_side = 1280` 또는 `1600` | 300 DPI 원본 그대로 넣지 말 것 |
| **angle_cls 끄기** | `use_angle_cls=False` | 정방향 문서 위주면 꺼두는 것이 안정·속도 모두 유리 |
| **배치 크기** | `batch_size=1` | 3GB VRAM에서 OOM 방지 |

이 3개를 지키면 “일단 안 터지고” 돌아갈 확률이 올라간다.

**현재 이 프로젝트 기본값**

- `pdf_to_images(..., max_side_len=1280)` → 긴 변 제한 적용
- `get_ocr_engine(use_angle_cls=False)` → 각도 분류 비활성화
- 페이지별 순차 처리 → 실질적으로 배치 1

→ **이미 3GB 안정권 설정과 맞춰져 있다.** GPU로 전환해도 추가 튜닝 없이 사용 가능하다.

---

## 3. 성능/품질 관점 결론

- **GPU(1060 3GB) + 위 안정화**: 보통 더 빠르고, 표·레이아웃이 복잡한 페이지에서 성공률이 높다.
- **CPU Paddle**: 느리다. Tesseract CPU와 비교해도 애매할 때가 많다.
- **CPU만 쓸 거면**: “Paddle CPU”보다 **Tesseract CPU**가 더 실용적인 경우가 많다(가볍고 튜닝 여지가 있음).

---

## 4. 추천 운영안 (현실적으로 깔끔한 순서)

GPU 없이도 죽지 않고, GPU는 필요한 순간에만 써서 VRAM 3GB 제약을 피하는 흐름이다.

| 단계 | 내용 |
|------|------|
| **1차** | **텍스트 레이어 있으면 추출** (PDF 내장 텍스트 사용, OCR 생략) |
| **2차** | **Tesseract** — 가벼운 페이지, 단순 레이아웃 |
| **3차** | **Paddle GPU** — 표/레이아웃 복잡 페이지, 또는 Tesseract 실패 페이지 |

이렇게 하면:

- “GPU 없으면 못 돌린다” 구조가 아니고,
- GPU는 복잡한 페이지만 담당해서 3GB 한계를 피할 수 있다.

**이 프로젝트**는 현재 **3차(Paddle OCR)** 만 구현한 상태다. 1차(텍스트 레이어 추출), 2차(Tesseract)는 필요 시 별도 모듈·파이프라인으로 붙이면 된다.

---

## 5. 요약

- **GTX 1060 (Pascal)**: paddlepaddle-gpu **cu118** 버전 사용 권장 (cu129는 검출 실패 가능).
- **3GB GPU 쓸 때**: `max_side_len=1280`(또는 1600), `use_angle_cls=False`, 배치 1 유지 → 현재 코드가 이미 이에 맞춰져 있음.
- **운영 전략**: 텍스트 레이어 추출 → Tesseract(가벼운 페이지) → Paddle GPU(복잡/실패 페이지).
- **CPU만 쓸 때**: Paddle CPU보다 Tesseract가 더 나은 선택일 수 있음.
