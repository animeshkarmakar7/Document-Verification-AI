import hashlib
from io import BytesIO

import pytest
from app.services.hash_service import HashService
from fastapi import UploadFile


@pytest.mark.anyio
async def test_calculate_sha256():

    content = b"Legal Document AI"

    expected_hash = hashlib.sha256(
        content
    ).hexdigest()

    file = UploadFile(
        file=BytesIO(content),
        filename="document.pdf",
    )

    service = HashService()

    actual_hash = await service.calculate_sha256(
        file
    )

    assert actual_hash == expected_hash
    
@pytest.mark.anyio
async def test_hash_resets_file_position():

    content = b"Legal Document AI"

    file = UploadFile(
        file=BytesIO(content),
        filename="document.pdf",
    )

    service = HashService()

    await service.calculate_sha256(file)

    remaining_content = await file.read()

    assert remaining_content == content
    

@pytest.mark.anyio
async def test_sha256_large_file():

    content = b"A" * (2 * 1024 * 1024)

    expected_hash = hashlib.sha256(
        content
    ).hexdigest()

    file = UploadFile(
        file=BytesIO(content),
        filename="large-document.pdf",
    )

    service = HashService()

    actual_hash = await service.calculate_sha256(
        file
    )

    assert actual_hash == expected_hash