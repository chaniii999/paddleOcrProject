from fastapi import FastAPI

from app.routers import health, ocr

app = FastAPI()

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(ocr.router, prefix="/api/ocr", tags=["ocr"])
