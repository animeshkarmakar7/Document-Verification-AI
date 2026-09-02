"""
StorageService — S3/MinIO adapter with local filesystem fallback.

When STORAGE_ENDPOINT is empty or set to 'local', files are stored in the
LOCAL_STORAGE_DIR directory (default: backend/local_storage).  This allows
the application to run during local development without a running MinIO or S3
instance.  Set STORAGE_ENDPOINT to the real MinIO/S3 URL in production.
"""

import logging
import os
import shutil
from pathlib import Path

from app.config.settings import settings

logger = logging.getLogger(__name__)

try:
    from botocore.exceptions import ClientError
except ImportError:
    ClientError = Exception  # type: ignore[misc,assignment]


def _is_local_mode() -> bool:
    """Return True when the endpoint is absent or explicitly set to 'local'."""
    ep = (settings.STORAGE_ENDPOINT or "").strip().lower()
    return ep in ("", "local", "none")


# ──────────────────────────────────────────────────────────────────────────────
# Local filesystem backend
# ──────────────────────────────────────────────────────────────────────────────

class _LocalStorageBackend:
    """Stores files on the local filesystem under <LOCAL_STORAGE_DIR>/<bucket>/."""

    def __init__(self) -> None:
        base = Path(getattr(settings, "LOCAL_STORAGE_DIR", "local_storage"))
        self.root = base / settings.STORAGE_BUCKET
        self.root.mkdir(parents=True, exist_ok=True)
        logger.info(
            "StorageService running in LOCAL mode — files stored at %s", self.root.resolve()
        )

    # --------------------------------------------------------------------------
    def upload_file(self, file_object, object_key: str, content_type: str) -> str:
        dest = self._path(object_key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as fh:
            shutil.copyfileobj(file_object, fh)
        return f"local://{settings.STORAGE_BUCKET}/{object_key}"

    def create_presigned_put_url(self, object_key: str, content_type: str, expires_in: int | None = None) -> str:
        # In local mode there is no real presigned URL — return a placeholder.
        return f"local://presigned/{object_key}"

    def download_file(self, object_key: str) -> bytes:
        return self._path(object_key).read_bytes()

    def download_file_to_path(self, object_key: str, destination_path: str) -> None:
        shutil.copy2(self._path(object_key), destination_path)

    def delete_file(self, object_key: str) -> None:
        p = self._path(object_key)
        if p.exists():
            p.unlink()

    def file_exists(self, object_key: str) -> bool:
        return self._path(object_key).exists()

    # --------------------------------------------------------------------------
    def _path(self, object_key: str) -> Path:
        # Sanitise the key so it is safe as a filesystem path.
        safe = object_key.lstrip("/").replace("\\", "/")
        return self.root / safe


# ──────────────────────────────────────────────────────────────────────────────
# S3 / MinIO backend
# ──────────────────────────────────────────────────────────────────────────────

class _S3StorageBackend:
    """Thin wrapper around boto3 for S3-compatible storage (MinIO, AWS S3, …)."""

    def __init__(self) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("boto3 is required for S3/MinIO storage operations.") from exc

        self.client = boto3.client(
            "s3",
            endpoint_url=settings.STORAGE_ENDPOINT,
            aws_access_key_id=settings.STORAGE_ACCESS_KEY,
            aws_secret_access_key=settings.STORAGE_SECRET_KEY,
            region_name=settings.STORAGE_REGION,
        )
        self.bucket = settings.STORAGE_BUCKET
        self._ensure_bucket_exists()

    # --------------------------------------------------------------------------
    def _ensure_bucket_exists(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            self.client.create_bucket(Bucket=self.bucket)

    def upload_file(self, file_object, object_key: str, content_type: str) -> str:
        self.client.upload_fileobj(
            file_object,
            self.bucket,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )
        return f"s3://{self.bucket}/{object_key}"

    def create_presigned_put_url(self, object_key: str, content_type: str, expires_in: int | None = None) -> str:
        return self.client.generate_presigned_url(
            ClientMethod="put_object",
            Params={"Bucket": self.bucket, "Key": object_key, "ContentType": content_type},
            ExpiresIn=expires_in or settings.PRESIGNED_UPLOAD_EXPIRY_SECONDS,
            HttpMethod="PUT",
        )

    def download_file(self, object_key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=object_key)["Body"].read()

    def download_file_to_path(self, object_key: str, destination_path: str) -> None:
        with open(destination_path, "wb") as fh:
            self.client.download_fileobj(self.bucket, object_key, fh)

    def delete_file(self, object_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=object_key)

    def file_exists(self, object_key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=object_key)
            return True
        except ClientError:
            return False


# ──────────────────────────────────────────────────────────────────────────────
# Public facade
# ──────────────────────────────────────────────────────────────────────────────

class StorageService:
    """
    Public StorageService.  Delegates to the appropriate backend:
      • _LocalStorageBackend  — when STORAGE_ENDPOINT is empty / 'local'
      • _S3StorageBackend     — when STORAGE_ENDPOINT points to MinIO / AWS S3
    """

    def __init__(self) -> None:
        if _is_local_mode():
            self._backend: _LocalStorageBackend | _S3StorageBackend = _LocalStorageBackend()
        else:
            self._backend = _S3StorageBackend()

    # --------------------------------------------------------------------------
    # Delegates — same public interface as before

    def upload_file(self, file_object, object_key: str, content_type: str) -> str:
        return self._backend.upload_file(file_object, object_key, content_type)

    def create_presigned_put_url(self, object_key: str, content_type: str, expires_in: int | None = None) -> str:
        return self._backend.create_presigned_put_url(object_key, content_type, expires_in)

    def download_file(self, object_key: str) -> bytes:
        return self._backend.download_file(object_key)

    def download_file_to_path(self, object_key: str, destination_path: str) -> None:
        self._backend.download_file_to_path(object_key, destination_path)

    def delete_file(self, object_key: str) -> None:
        self._backend.delete_file(object_key)

    def file_exists(self, object_key: str) -> bool:
        return self._backend.file_exists(object_key)

    # Legacy alias used by some older code paths
    def ensure_bucket_exists(self) -> None:
        if isinstance(self._backend, _S3StorageBackend):
            self._backend._ensure_bucket_exists()
