from fastapi import FastAPI, HTTPException

from app.api.classification import router as classification_router
from app.api.clauses import router as clauses_router
from app.api.ocr import router as ocr_router
from app.api.upload import router as upload_router
from app.config.settings import settings
from app.core.errors import http_exception_handler, unhandled_exception_handler
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
)

app.add_exception_handler(
    HTTPException,
    http_exception_handler,
)

app.add_exception_handler(
    Exception,
    unhandled_exception_handler,
)

app.include_router(
    upload_router,
    prefix="/api/v1",
)

app.include_router(
    ocr_router,
    prefix="/api/v1",
)

app.include_router(
    clauses_router,
    prefix="/api/v1",
)

app.include_router(
    classification_router,
    prefix="/api/v1",
)


@app.get("/")
def root():
    return {
        "application": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
    }
