from pathlib import Path

from app.config.settings import settings
from app.schemas.validation import ValidatedFile
from fastapi import UploadFile

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".tiff",
    ".webp",
    ".docx",
}


SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
    "image/webp",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


EXTENSION_MIME_TYPES = {
    ".pdf": {
        "application/pdf",
    },
    ".png": {
        "image/png",
    },
    ".jpg": {
        "image/jpeg",
    },
    ".jpeg": {
        "image/jpeg",
    },
    ".tiff": {
        "image/tiff",
    },
    ".webp": {
        "image/webp",
    },
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    },
}


MAGIC_BYTES = {
    ".pdf": (
        b"%PDF-",
    ),
    ".png": (
        b"\x89PNG\r\n\x1a\n",
    ),
    ".jpg": (
        b"\xff\xd8\xff",
    ),
    ".jpeg": (
        b"\xff\xd8\xff",
    ),
    ".tiff": (
        b"II*\x00",
        b"MM\x00*",
    ),
    ".docx": (
        b"PK\x03\x04",
    ),
}


class FileValidationError(Exception):
    """Raised when an uploaded file fails validation."""


class ValidationService:

    def __init__(self):
        self.max_file_size = (
            settings.MAX_UPLOAD_SIZE_MB
            * 1024
            * 1024
        )

    def validate_filename(
        self,
        filename: str | None,
    ) -> None:

        if not filename:
            raise FileValidationError(
                "Filename is required."
            )

        if not filename.strip():
            raise FileValidationError(
                "Filename cannot be empty."
            )

    def validate_extension(
        self,
        filename: str,
    ) -> str:

        extension = Path(
            filename
        ).suffix.lower()

        if extension not in SUPPORTED_EXTENSIONS:
            raise FileValidationError(
                f"Unsupported file extension: {extension}"
            )

        return extension

    def validate_mime_type(
        self,
        mime_type: str | None,
        extension: str,
    ) -> None:

        if not mime_type:
            raise FileValidationError(
                "MIME type is required."
            )

        if mime_type not in SUPPORTED_MIME_TYPES:
            raise FileValidationError(
                f"Unsupported MIME type: {mime_type}"
            )

        if mime_type not in EXTENSION_MIME_TYPES[extension]:
            raise FileValidationError(
                "File extension and MIME type do "
                "not match."
            )

    async def validate_file_size(
        self,
        file: UploadFile,
    ) -> int:

        total_size = 0

        while True:

            chunk = await file.read(
                1024 * 1024
            )

            if not chunk:
                break

            total_size += len(chunk)

            if total_size > self.max_file_size:

                await file.seek(0)

                raise FileValidationError(
                    f"File exceeds the maximum "
                    f"allowed size of "
                    f"{settings.MAX_UPLOAD_SIZE_MB} MB."
                )

        await file.seek(0)

        if total_size == 0:
            raise FileValidationError(
                "Uploaded file is empty."
            )

        return total_size

    async def validate_magic_bytes(
        self,
        file: UploadFile,
        extension: str,
    ) -> None:

        header = await file.read(16)

        await file.seek(0)

        if extension == ".webp":

            if (
                len(header) < 12
                or not header.startswith(b"RIFF")
                or header[8:12] != b"WEBP"
            ):
                raise FileValidationError(
                    "Invalid WEBP file."
                )

            return

        signatures = MAGIC_BYTES.get(
            extension
        )

        if signatures is None:
            raise FileValidationError(
                f"No file signature validator "
                f"configured for {extension}."
            )

        valid = any(
            header.startswith(signature)
            for signature in signatures
        )

        if not valid:
            raise FileValidationError(
                "File content does not match "
                f"the declared extension {extension}."
            )

    async def validate(
        self,
        file: UploadFile,
    ) -> ValidatedFile:

        self.validate_filename(
            file.filename
        )

        extension = self.validate_extension(
            file.filename
        )

        self.validate_mime_type(
            file.content_type,
            extension,
        )

        file_size = (
            await self.validate_file_size(
                file
            )
        )

        await self.validate_magic_bytes(
            file,
            extension,
        )

        return ValidatedFile(
            extension=extension,
            file_size=file_size,
        )
