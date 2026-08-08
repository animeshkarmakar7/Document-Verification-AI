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

    STORAGE_ENDPOINT: str = "http://localhost:9000"
    STORAGE_ACCESS_KEY: str = "legal_admin"
    STORAGE_SECRET_KEY: str = "change-this-password"
    STORAGE_BUCKET: str = "legal-documents"
    STORAGE_REGION: str = "us-east-1"

    MAX_UPLOAD_SIZE_MB: int = 50
    LOG_LEVEL: str = "INFO"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.6-flash"
    GEMINI_CLASSIFICATION_BATCH_SIZE: int = 100

    model_config = SettingsConfigDict(
        env_file=(
            BACKEND_DIR / ".env",
            ".env",
        ),
        extra="ignore",
    )


settings = Settings()
