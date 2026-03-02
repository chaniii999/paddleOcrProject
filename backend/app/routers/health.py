from fastapi import APIRouter

router = APIRouter()


# 서비스 살아 있음 여부 확인용. status·service 이름만 반환.
@router.get("/health")
def health_check():
    return {"status": "ok", "service": "parliament-ocr"}
