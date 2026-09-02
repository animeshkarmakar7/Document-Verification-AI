from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.api.commands import router as commands_router
from app.api.queries import router as queries_router
from app.config.settings import settings
from app.core.errors import http_exception_handler, unhandled_exception_handler
from app.core.logging import configure_logging
from app.database.base import Base
from app.database.database import engine

# Import all models so Base.metadata contains all tables
import app.models.chat  # noqa: F401
import app.models.classification  # noqa: F401
import app.models.clause  # noqa: F401
import app.models.document  # noqa: F401
import app.models.explanation  # noqa: F401
import app.models.ingestion  # noqa: F401
import app.models.ocr_result  # noqa: F401
import app.models.risk  # noqa: F401

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-create any missing database tables on application startup
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"Warning: Base.metadata.create_all failed: {e}")

    # Ensure all ClauseCategory enum values exist in PostgreSQL database
    try:
        from app.models.enums import ClauseCategory
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execution_options(isolation_level="AUTOCOMMIT")
            for cat in ClauseCategory:
                conn.execute(text(f"ALTER TYPE clause_category ADD VALUE IF NOT EXISTS '{cat.value}'"))
    except Exception as e:
        print(f"Warning: ClauseCategory enum sync skipped/failed: {e}")

    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(commands_router, prefix="/api/v1")
app.include_router(queries_router, prefix="/api/v1")


@app.get("/")
def root():
    return {
        "application": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health")
def health():
    return {"status": "healthy"}
