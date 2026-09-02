from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    APP_NAME: str = "Legal Document Intelligence"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"

    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 5432
    DATABASE_NAME: str = "legal_ai"
    DATABASE_USER: str = "postgres"
    DATABASE_PASSWORD: str = "postgres"

    STORAGE_ENDPOINT: str = ""
    STORAGE_ACCESS_KEY: str = "legal_admin"
    STORAGE_SECRET_KEY: str = "change-this-password"
    STORAGE_BUCKET: str = "legal-documents"
    STORAGE_REGION: str = "us-east-1"
    LOCAL_STORAGE_DIR: str = "local_storage"
    PRESIGNED_UPLOAD_EXPIRY_SECONDS: int = 900

    MAX_UPLOAD_SIZE_MB: int = 50
    LOG_LEVEL: str = "INFO"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.6-flash"
    GEMINI_CLASSIFICATION_BATCH_SIZE: int = 100

    EMBEDDING_MODEL: str = "BAAI/bge-large-en-v1.5"
    VECTOR_STORE_DIRECTORY: str = str(BACKEND_DIR / ".chroma_db")

    DEDUP_CACHE_BACKEND: str = "memory"
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_DOCUMENT_INGEST_TOPIC: str = "doc.ingest.requested"
    KAFKA_PAGE_SHARDS_TOPIC: str = "pdf.page.shards"
    KAFKA_DLQ_TOPIC: str = "pdf.page.shards.dlq"
    PDF_TEXT_PAGE_BATCH_SIZE: int = 25
    SCANNED_PDF_OCR_PAGE_BATCH_SIZE: int = 5
    PDF_SHARD_SIZE_PAGES: int = 50

    model_config = SettingsConfigDict(
        env_file=(
            BACKEND_DIR / ".env",
            ".env",
        ),
        extra="ignore",
    )


settings = Settings()
