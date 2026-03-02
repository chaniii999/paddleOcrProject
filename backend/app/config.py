"""OCR·PDF 관련 설정 상수. 변경 시 이 파일만 보면 됨."""

# PDF → 이미지 렌더링 (DPI 300 + 긴 변 960 리사이즈로 인식률·안정성 균형)
OCR_DPI = 300
OCR_MAX_SIDE_LEN = 960

# 업로드 PDF 크기 제한 (MB)
MAX_PDF_SIZE_MB = 50
