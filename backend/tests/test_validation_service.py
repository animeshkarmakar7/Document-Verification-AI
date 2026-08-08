from io import BytesIO

import pytest
from app.services.validation_service import (
    FileValidationError,
    ValidationService,
)
from fastapi import UploadFile


def test_pdf_signature():

    validator = ValidationService()

    assert (
        validator.validate_extension(
            "contract.pdf"
        )
        == ".pdf"
    )


def test_unsupported_extension():

    validator = ValidationService()

    with pytest.raises(FileValidationError):

        validator.validate_extension(
            "contract.exe"
        )


def test_rejects_mismatched_extension_and_mime_type():

    validator = ValidationService()

    with pytest.raises(FileValidationError):

        validator.validate_mime_type(
            "image/jpeg",
            ".pdf",
        )


@pytest.mark.anyio
async def test_rejects_invalid_magic_bytes():

    validator = ValidationService()

    file = UploadFile(
        file=BytesIO(b"not a pdf"),
        filename="contract.pdf",
    )

    with pytest.raises(FileValidationError):

        await validator.validate_magic_bytes(
            file,
            ".pdf",
        )


@pytest.mark.anyio
async def test_validates_pdf_upload_and_resets_stream():

    validator = ValidationService()

    content = b"%PDF-1.7\nlegal document"

    file = UploadFile(
        file=BytesIO(content),
        filename="contract.pdf",
        headers={
            "content-type": "application/pdf",
        },
    )

    validated_file = await validator.validate(file)

    assert validated_file.extension == ".pdf"
    assert validated_file.file_size == len(content)
    assert await file.read() == content
